import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Check,
  Clock3,
  FileText,
  Folder,
  FolderInput,
  Gauge,
  Loader2,
  Mic,
  Play,
  Sparkles,
  Trash2,
  Wand2,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { toast } from "sonner";
import { Switch } from "@/desktop/PhoneSync";
import { useClip } from "@/listen/clip";
import { useSource } from "@/listen/source";
import { BookCover } from "@/shared/BookCover";
import { cn } from "@/shared/cn";
import { formatLength, formatNumber } from "@/shared/format";
import { Button, Segmented, Vu } from "@/shared/ui";
import type { ScanResult, Voice } from "@/studio/api";
import { pickFiles, pickFolder, useAppInfo, useCreateBook, useScan, useVoices } from "@/studio/data";

type Profile = "fast" | "balanced" | "high_quality";

const STEPS = [
  { title: "Nội dung", hint: "Các chương TXT" },
  { title: "Giọng kể", hint: "Người dẫn truyện" },
  { title: "Chất lượng", hint: "Nhanh hay kỹ" },
  { title: "Xác nhận", hint: "Xem lại và tạo" },
];

const PROFILES: { value: Profile; title: string; pace: string; summary: string; points: string[] }[] = [
  {
    value: "fast",
    title: "Nhanh",
    pace: "Nhanh nhất",
    summary: "Nghe thử một truyện mới, hoặc cần gấp.",
    points: ["Phân tích truyện từng đoạn dài một lượt", "Soát cơ bản sau khi đọc", "Đọc lại tối đa 1 lần nếu câu bị đọc sai"],
  },
  {
    value: "balanced",
    title: "Cân bằng",
    pace: "Vừa phải",
    summary: "Nghe hằng ngày, chấp nhận vài câu chưa hoàn hảo.",
    points: ["Phân tích truyện đầy đủ", "Soát cơ bản sau khi đọc", "Đọc lại tối đa 2 lần nếu câu bị đọc sai"],
  },
  {
    value: "high_quality",
    title: "Chất lượng cao",
    pace: "Chậm nhất, kỹ nhất",
    summary: "Sách nghe lại nhiều lần hoặc để chia sẻ.",
    points: ["Rà lại cảm xúc từng câu một lần nữa", "Nghe lại mọi câu, soát kỹ từng chữ", "Đọc lại tới 5 lần nếu câu bị đọc sai"],
  },
];

// Ước lượng thời gian làm trên máy này, đo từ hai lô gần nhất của cuốn 2 (26-09, mức Chất lượng cao): lô 18 có
// 113 nghìn chữ, phân tích ~4 giờ, thu âm 4,6-7,1 giờ. Hai mức kia chưa đo trên máy này nên không đoán con số.
const MEASURED = { analysisPerKiloword: 2.1 * 60, synthesisPerKiloword: [2.5 * 60, 3.8 * 60] as const };

function estimate(words: number, chapters: number) {
  const kilo = words / 1000;
  const analysis = kilo * MEASURED.analysisPerKiloword;
  const [low, high] = MEASURED.synthesisPerKiloword.map((seconds) => kilo * seconds);
  return {
    analysis,
    totalLow: analysis + low,
    totalHigh: analysis + high,
    firstChapter: analysis + high / Math.max(1, chapters),
  };
}

function lengthRange(low: number, high: number): string {
  const a = formatLength(low);
  const b = formatLength(high);
  return a === b ? `khoảng ${a}` : `${a} - ${b}`;
}

// ---- Nháp: rời trang rồi quay lại không mất gì ----------------------------------------------------------------

interface Draft {
  paths: string[];
  excluded: string[];
  title: string;
  titleEdited: boolean;
  narrator: string;
  profile: Profile;
  startNow: boolean;
}

const DRAFT_KEY = "ebook-reader-new-book-draft";
const EMPTY_DRAFT: Draft = { paths: [], excluded: [], title: "", titleEdited: false, narrator: "", profile: "high_quality", startNow: true };

function loadDraft(): Draft {
  try {
    return { ...EMPTY_DRAFT, ...JSON.parse(sessionStorage.getItem(DRAFT_KEY) ?? "{}") };
  } catch {
    return EMPTY_DRAFT;
  }
}

function saveDraft(draft: Draft | null): void {
  try {
    if (draft) sessionStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
    else sessionStorage.removeItem(DRAFT_KEY);
  } catch {
    /* không lưu được nháp thì thôi */
  }
}

function cleanPath(value: string): string {
  return value.trim().replace(/^["']+|["']+$/g, "").trim();
}

// ---- Thanh bước --------------------------------------------------------------------------------------------------

function StepRail({ step, allowed, onGo }: { step: number; allowed: number; onGo: (index: number) => void }) {
  return (
    <ol className="space-y-1">
      {STEPS.map((item, index) => {
        const done = index < step;
        const current = index === step;
        const enabled = index <= allowed;
        return (
          <li key={item.title}>
            <button
              type="button"
              disabled={!enabled}
              aria-current={current ? "step" : undefined}
              onClick={() => onGo(index)}
              className={cn(
                "flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-left transition-colors disabled:cursor-not-allowed",
                current ? "bg-hover" : enabled && "hover:bg-hover",
              )}
            >
              <span
                className={cn(
                  "grid size-7 shrink-0 place-items-center rounded-full text-xs font-bold",
                  done ? "bg-success text-white" : current ? "bg-accent text-accent-ink" : "bg-hover text-fg-2",
                )}
              >
                {done ? <Check className="size-4" strokeWidth={3} /> : index + 1}
              </span>
              <span>
                <span className={cn("block text-sm font-medium", !current && !done && "text-fg-2")}>{item.title}</span>
                <span className="block text-xs text-fg-2">{item.hint}</span>
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

// ---- Bước 1 ---------------------------------------------------------------------------------------------------

function SourceStep({
  scan,
  title,
  onTitle,
  scanning,
  onPaths,
  onAddFiles,
  onRemove,
  problem,
}: {
  scan: ScanResult | null;
  title: string;
  onTitle: (title: string) => void;
  scanning: boolean;
  onPaths: (paths: string[]) => void;
  onAddFiles: (paths: string[]) => void;
  onRemove: (path: string) => void;
  problem: { text: string; subfolders: string[] } | null;
}) {
  const { data: info } = useAppInfo();
  const [typed, setTyped] = useState("");
  const chooseFolder = async () => {
    const path = await pickFolder("Chọn thư mục chứa các chương TXT").catch((error: Error) => {
      toast.error(error.message);
      return null;
    });
    if (path) onPaths([path]);
  };
  const chooseFiles = async (append: boolean) => {
    const chosen = await pickFiles("Chọn các chương TXT").catch((error: Error) => {
      toast.error(error.message);
      return [];
    });
    if (chosen.length) (append ? onAddFiles : onPaths)(chosen);
  };
  const files = scan?.files ?? [];
  return (
    <div>
      <h2 className="text-xl font-semibold">Chọn các chương của truyện</h2>
      <p className="mt-1 text-sm text-fg-2 text-pretty">
        Mỗi file TXT là một chương. Chương được xếp theo tên file như người đọc mong đợi: 2 đứng trước 10.
      </p>
      {!files.length ? (
        <div className="mt-6 rounded-2xl border-2 border-dashed border-line-strong bg-panel px-8 py-10 text-center">
          <div className="mx-auto grid size-14 place-items-center rounded-2xl bg-accent-soft text-accent-text">
            {scanning ? <Loader2 className="size-7 animate-spin" /> : <FolderInput className="size-7" strokeWidth={1.75} />}
          </div>
          <p className="mt-4 font-medium">{scanning ? "Đang đọc các chương…" : "Chọn thư mục chứa truyện"}</p>
          <p className="mt-1 text-sm text-fg-2">Chỉ lấy file .txt nằm ngay trong thư mục, không quét thư mục con.</p>
          {info?.dialogs && (
            <div className="mt-6 flex justify-center gap-2">
              <Button variant="primary" icon={Folder} onClick={() => void chooseFolder()}>
                Chọn thư mục
              </Button>
              <Button icon={FileText} onClick={() => void chooseFiles(false)}>
                Chọn từng file
              </Button>
            </div>
          )}
          <form
            className="mx-auto mt-5 flex max-w-lg gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              const path = cleanPath(typed);
              if (path) onPaths([path]);
            }}
          >
            <input
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
              aria-label="Đường dẫn thư mục"
              aria-invalid={Boolean(problem)}
              aria-describedby={problem ? "source-problem" : undefined}
              placeholder={info?.dialogs ? "…hoặc dán đường dẫn thư mục" : "Dán đường dẫn thư mục, ví dụ D:\\Truyện\\Tên truyện"}
              className={cn(
                "h-10 flex-1 rounded-lg border bg-bg px-3 text-sm outline-none placeholder:text-fg-3 focus:border-accent",
                problem ? "border-danger" : "border-line",
              )}
            />
            <Button type="submit" disabled={!cleanPath(typed) || scanning}>
              Mở
            </Button>
          </form>
          {problem && (
            <div id="source-problem" role="alert" className="mx-auto mt-3 max-w-lg text-left text-sm text-danger">
              {problem.text}
              {problem.subfolders.length > 0 && (
                <div className="mt-2 space-y-1">
                  <div className="text-fg-2">Có thể bạn muốn chọn thư mục con:</div>
                  {problem.subfolders.map((folder) => (
                    <button
                      key={folder}
                      type="button"
                      onClick={() => onPaths([folder])}
                      className="flex w-full items-center gap-2 truncate rounded-lg border border-line bg-panel px-3 py-2 text-left text-fg hover:border-accent"
                    >
                      <Folder className="size-4 shrink-0 text-fg-2" />
                      <span className="truncate">{folder}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      ) : (
        <>
          <label className="mt-6 block">
            <span className="text-sm font-medium">Tên sách</span>
            <input
              value={title}
              onChange={(event) => onTitle(event.target.value)}
              aria-invalid={!title.trim()}
              className={cn(
                "mt-1.5 h-11 w-full rounded-xl border bg-panel px-3.5 text-[15px] font-medium outline-none focus:border-accent",
                title.trim() ? "border-line" : "border-danger",
              )}
              placeholder="Tên hiển thị trong thư viện"
            />
            {!title.trim() && <span className="mt-1 block text-[13px] text-danger">Sách cần có tên để hiện trong thư viện.</span>}
          </label>
          <div className="mt-5 flex flex-wrap items-center justify-between gap-2">
            <div className="tabular text-sm text-fg-2">
              <span className="font-semibold text-fg">{files.length} chương</span> · {formatNumber(scan!.totals.words)} chữ · khoảng{" "}
              {formatLength(scan!.totals.audioSeconds)} audio
            </div>
            <div className="flex gap-1">
              {info?.dialogs && (
                <Button size="sm" variant="ghost" icon={FileText} onClick={() => void chooseFiles(true)}>
                  Thêm file
                </Button>
              )}
              <Button size="sm" variant="ghost" onClick={() => onPaths([])}>
                Chọn lại
              </Button>
            </div>
          </div>
          <div className="mt-3 max-h-[340px] overflow-y-auto rounded-xl border border-line bg-panel">
            {files.map((file, index) => (
              <div
                key={file.path}
                className="group grid grid-cols-[40px_minmax(0,1fr)_90px_36px] items-center gap-2 border-b border-line px-3 py-2 [contain-intrinsic-size:auto_48px] [content-visibility:auto] last:border-b-0"
              >
                <span className="tabular text-xs text-fg-2">{index + 1}</span>
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{file.firstLine || file.title}</div>
                  <div className="truncate text-xs text-fg-2">{file.name}</div>
                </div>
                <span className="tabular text-right text-xs text-fg-2">{formatNumber(file.words)} chữ</span>
                <button
                  type="button"
                  aria-label={`Bỏ chương ${file.name}`}
                  title="Bỏ chương này"
                  onClick={() => onRemove(file.path)}
                  className="grid size-8 place-items-center rounded-md text-fg-2 opacity-0 hover:bg-hover hover:text-danger group-hover:opacity-100 focus-visible:opacity-100"
                >
                  <Trash2 className="size-4" />
                </button>
              </div>
            ))}
          </div>
          {scan!.skipped.length > 0 && <p className="mt-2 text-xs text-fg-2">Bỏ qua {scan!.skipped.length} file không phải .txt.</p>}
        </>
      )}
    </div>
  );
}

// ---- Bước 2 ---------------------------------------------------------------------------------------------------

function VoiceCard({
  voice,
  selected,
  focusable,
  onSelect,
}: {
  voice: Voice;
  selected: boolean;
  focusable: boolean;
  onSelect: () => void;
}) {
  const clip = useClip();
  const source = useSource();
  const id = `voice-${voice.name}`;
  const playing = clip.current === id;
  return (
    <div
      className={cn(
        "relative flex items-center gap-3 rounded-xl border bg-panel p-3.5 transition-colors",
        selected ? "border-accent ring-1 ring-accent" : "border-line hover:border-line-strong",
      )}
    >
      <button
        type="button"
        tabIndex={-1}
        aria-label={playing ? `Dừng nghe ${voice.name}` : `Nghe thử giọng ${voice.name}`}
        onClick={() => clip.toggle(id, source.voiceUrl(voice.name))}
        className={cn(
          "grid size-10 shrink-0 place-items-center rounded-full transition-colors",
          playing ? "bg-accent text-accent-ink" : "bg-hover text-fg hover:bg-line",
        )}
      >
        {playing ? <Vu className="h-3" /> : <Play className="size-4 translate-x-[1px]" fill="currentColor" strokeWidth={0} />}
      </button>
      <button
        type="button"
        role="radio"
        aria-checked={selected}
        tabIndex={focusable ? 0 : -1}
        data-voice={voice.name}
        onClick={onSelect}
        className="min-w-0 flex-1 text-left outline-none after:absolute after:inset-0 after:rounded-xl focus-visible:after:outline-2 focus-visible:after:outline-offset-2 focus-visible:after:outline-accent"
      >
        <span className="block font-semibold leading-snug">{voice.name}</span>
        <span className="mt-0.5 block text-xs text-fg-2">
          {voice.gender} · Miền {voice.region} · {voice.style}
        </span>
        {voice.recommended && (
          <span className="mt-1.5 inline-block rounded-md bg-accent-soft px-1.5 py-px text-[11px] font-semibold uppercase tracking-wide text-accent-text">
            Đề xuất
          </span>
        )}
      </button>
      {selected && (
        <span className="grid size-6 shrink-0 place-items-center rounded-full bg-accent text-accent-ink" aria-hidden>
          <Check className="size-3.5" strokeWidth={3} />
        </span>
      )}
    </div>
  );
}

function VoiceStep({ narrator, setNarrator }: { narrator: string; setNarrator: (name: string) => void }) {
  const { data: voices } = useVoices();
  const [gender, setGender] = useState("all");
  const [region, setRegion] = useState("all");
  const group = useRef<HTMLDivElement | null>(null);
  const shown = (voices ?? []).filter(
    (voice) => (gender === "all" || voice.gender === gender) && (region === "all" || voice.region === region),
  );
  const hiddenSelection = Boolean(narrator) && !shown.some((voice) => voice.name === narrator);
  const focusName = shown.some((voice) => voice.name === narrator) ? narrator : shown[0]?.name;
  // Một điểm dừng Tab cho cả nhóm; mũi tên chuyển giọng (chuẩn radiogroup).
  const onKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    const keys: Record<string, number> = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
    const step = keys[event.key];
    if (!step || !shown.length) return;
    event.preventDefault();
    const index = shown.findIndex((voice) => voice.name === focusName);
    const next = shown[(index + step + shown.length) % shown.length];
    setNarrator(next.name);
    window.requestAnimationFrame(() => group.current?.querySelector<HTMLElement>(`[data-voice="${CSS.escape(next.name)}"]`)?.focus());
  };
  return (
    <div>
      <h2 className="text-xl font-semibold">Chọn giọng kể chuyện</h2>
      <p className="mt-1 max-w-2xl text-sm text-fg-2 text-pretty">
        Giọng này đọc toàn bộ lời dẫn truyện. Mỗi nhân vật sẽ được tự động trao một giọng riêng sau bước phân tích - bạn
        không cần chọn trước.
      </p>
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <Segmented label="Giới tính" value={gender} onChange={setGender} options={[
          { value: "all", label: "Mọi giọng" },
          { value: "Nam", label: "Giọng nam" },
          { value: "Nữ", label: "Giọng nữ" },
        ]} />
        <Segmented label="Miền" value={region} onChange={setRegion} options={[
          { value: "all", label: "Mọi miền" },
          { value: "Bắc", label: "Miền Bắc" },
          { value: "Nam", label: "Miền Nam" },
          { value: "Trung", label: "Miền Trung" },
        ]} />
      </div>
      {hiddenSelection && (
        <p className="mt-3 text-sm text-fg-2">
          Đang chọn: <span className="font-semibold text-fg">{narrator}</span> (bộ lọc đang ẩn giọng này).{" "}
          <button type="button" className="font-medium text-accent-text underline underline-offset-2" onClick={() => { setGender("all"); setRegion("all"); }}>
            Bỏ lọc
          </button>
        </p>
      )}
      <div ref={group} role="radiogroup" aria-label="Giọng kể chuyện" onKeyDown={onKeyDown} className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 2xl:grid-cols-3">
        {shown.map((voice) => (
          <VoiceCard
            key={voice.name}
            voice={voice}
            selected={voice.name === narrator}
            focusable={voice.name === focusName}
            onSelect={() => setNarrator(voice.name)}
          />
        ))}
      </div>
    </div>
  );
}

// ---- Bước 3 ---------------------------------------------------------------------------------------------------

function QualityStep({ profile, setProfile, words, chapters }: { profile: Profile; setProfile: (profile: Profile) => void; words: number; chapters: number }) {
  const guess = estimate(words, chapters);
  return (
    <div>
      <h2 className="text-xl font-semibold">Chọn mức chất lượng</h2>
      <p className="mt-1 text-sm text-fg-2 text-pretty">
        Mức này đi cùng sách tới chương cuối, để mọi chương đọc giống nhau - không đổi được sau khi tạo.
      </p>
      <div role="radiogroup" aria-label="Chất lượng" className="mt-6 grid gap-4 lg:grid-cols-3">
        {PROFILES.map((option) => {
          const selected = option.value === profile;
          return (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => setProfile(option.value)}
              className={cn(
                "relative flex flex-col rounded-2xl border bg-panel p-5 text-left transition-colors",
                selected ? "border-accent ring-1 ring-accent" : "border-line hover:border-line-strong",
              )}
            >
              {option.value === "high_quality" && (
                <span className="absolute -top-2.5 left-4 inline-flex items-center gap-1 rounded-full bg-accent px-2 py-0.5 text-[11px] font-semibold text-accent-ink">
                  <Sparkles className="size-3" /> Nên dùng
                </span>
              )}
              <div className="flex items-center justify-between">
                <span className="text-base font-semibold">{option.title}</span>
                {selected && (
                  <span className="grid size-6 place-items-center rounded-full bg-accent text-accent-ink">
                    <Check className="size-3.5" strokeWidth={3} />
                  </span>
                )}
              </div>
              <div className="mt-1 flex items-center gap-1.5 text-xs font-medium text-fg-2">
                <Gauge className="size-3.5" /> {option.pace}
              </div>
              <p className="mt-3 text-sm text-fg-2">{option.summary}</p>
              <ul className="mt-4 space-y-2 text-[13px]">
                {option.points.map((point) => (
                  <li key={point} className="flex gap-2">
                    <Check className="mt-0.5 size-3.5 shrink-0 text-success" strokeWidth={3} />
                    <span>{point}</span>
                  </li>
                ))}
              </ul>
              <div className="mt-4 flex items-start gap-1.5 border-t border-line pt-3 text-[13px] text-fg-2">
                <Clock3 className="mt-0.5 size-3.5 shrink-0" />
                {option.value === "high_quality" ? (
                  <span>
                    Trên máy này: <span className="font-semibold text-fg">{lengthRange(guess.totalLow, guess.totalHigh)}</span> cho{" "}
                    {chapters} chương
                  </span>
                ) : (
                  <span>Nhanh hơn Chất lượng cao; chưa đo trên máy này.</span>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ---- Bước 4 ---------------------------------------------------------------------------------------------------

function ConfirmStep({
  title,
  scan,
  narrator,
  profile,
  startNow,
  setStartNow,
}: {
  title: string;
  scan: ScanResult;
  narrator: string;
  profile: Profile;
  startNow: boolean;
  setStartNow: (value: boolean) => void;
}) {
  const option = PROFILES.find((item) => item.value === profile)!;
  const guess = estimate(scan.totals.words, scan.files.length);
  const measured = profile === "high_quality";
  const rows: [string, string][] = [
    ["Chương", `${scan.files.length} chương · ${formatNumber(scan.totals.words)} chữ`],
    ["Độ dài audio", `khoảng ${formatLength(scan.totals.audioSeconds)}`],
    ["Giọng kể", narrator],
    ["Nhân vật", "Tự động phân vai sau khi phân tích"],
    ["Chất lượng", option.title],
    ...(measured
      ? ([
          ["Thời gian làm", lengthRange(guess.totalLow, guess.totalHigh)],
          ["Chương đầu nghe được sau", `khoảng ${formatLength(guess.firstChapter)}`],
        ] as [string, string][])
      : []),
  ];
  return (
    <div>
      <h2 className="text-xl font-semibold">Xem lại trước khi tạo</h2>
      <div className="mt-6 flex flex-col gap-6 rounded-2xl border border-line bg-panel p-6 sm:flex-row">
        <BookCover title={title} size="lg" className="w-40 max-sm:mx-auto" />
        <div className="min-w-0 flex-1">
          <h3 className="text-lg font-semibold text-balance">{title}</h3>
          <dl className="mt-3 divide-y divide-line text-sm">
            {rows.map(([label, value]) => (
              <div key={label} className="grid grid-cols-[170px_minmax(0,1fr)] gap-4 py-2">
                <dt className="text-fg-2">{label}</dt>
                <dd className="font-medium">{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
      <div className="mt-5 flex gap-3 rounded-xl border border-warning/40 bg-warning-soft p-4 text-sm">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" />
        <p className="text-pretty">
          <span className="font-semibold">Giai đoạn đầu là phân tích cả truyện</span>
          {measured ? ` (khoảng ${formatLength(guess.analysis)})` : ""}: trong lúc đó đừng tắt máy, đừng cho máy ngủ và đừng bấm
          Dừng. Dừng giữa chừng rồi chạy tiếp sẽ ra cách phân vai khác với chạy liền một mạch. Qua giai đoạn này thì dừng lúc nào
          cũng được.
        </p>
      </div>
      <label className="mt-4 flex items-start gap-3 rounded-xl border border-line bg-panel p-4" htmlFor="start-now">
        <Switch id="start-now" checked={startNow} onCheckedChange={setStartNow} />
        <span>
          <span className="block text-sm font-medium">Bắt đầu tạo ngay</span>
          <span className="mt-0.5 block text-[13px] leading-relaxed text-fg-2">
            Sách chạy nền: đóng cửa sổ vẫn tiếp tục, Windows báo khi xong. Chương nào xong là nghe được chương đó, không phải chờ
            cả cuốn.
          </span>
        </span>
      </label>
    </div>
  );
}

// ---- Trang ------------------------------------------------------------------------------------------------------

export function NewProjectScreen() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const scanMutation = useScan();
  const create = useCreateBook();
  const { data: voices } = useVoices();
  const [draft, setDraft] = useState<Draft>(loadDraft);
  const [rawScan, setRawScan] = useState<ScanResult | null>(null);
  const [problem, setProblem] = useState<{ text: string; subfolders: string[] } | null>(null);
  const submitting = useRef(false);
  const update = (changes: Partial<Draft>) => setDraft((current) => ({ ...current, ...changes }));

  useEffect(() => saveDraft(draft), [draft]);

  useEffect(() => {
    if (!draft.narrator && voices?.length) update({ narrator: voices.find((voice) => voice.recommended)?.name ?? voices[0].name });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [voices, draft.narrator]);

  // Quét lại chỉ khi danh sách nguồn đổi; bỏ một chương là lọc ngay ở đây, không đọc lại cả thư mục.
  useEffect(() => {
    if (!draft.paths.length) {
      setRawScan(null);
      setProblem(null);
      return;
    }
    scanMutation.mutate(draft.paths, {
      onSuccess: (result) => {
        setRawScan(result);
        if (!result.files.length) {
          setProblem(
            result.missing.length
              ? { text: `Không tìm thấy thư mục “${result.missing[0]}”. Kiểm tra lại đường dẫn.`, subfolders: [] }
              : { text: "Thư mục này không có file .txt nằm ngay bên trong.", subfolders: result.subfolders },
          );
          return;
        }
        setProblem(null);
        setDraft((current) => (current.titleEdited || !result.suggestedTitle ? current : { ...current, title: result.suggestedTitle }));
      },
      onError: (error: Error) => setProblem({ text: `Không đọc được: ${error.message}`, subfolders: [] }),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft.paths.join("\n")]);

  const scan = useMemo<ScanResult | null>(() => {
    if (!rawScan) return null;
    const excluded = new Set(draft.excluded);
    const files = rawScan.files.filter((file) => !excluded.has(file.path));
    const words = files.reduce((sum, file) => sum + file.words, 0);
    return { ...rawScan, files, totals: { chapters: files.length, words, audioSeconds: Math.round(words / 4.3) } };
  }, [rawScan, draft.excluded]);

  const title = draft.title;
  const allowed = !scan?.files.length || !title.trim() ? 0 : !draft.narrator ? 1 : STEPS.length - 1;
  const requested = Number(params.get("step") ?? 0);
  const step = Number.isInteger(requested) ? Math.max(0, Math.min(requested, allowed)) : 0;

  // Bước nằm trong URL: nút Back của trình duyệt/chuột lùi đúng một bước.
  const go = (index: number) => {
    const target = Math.max(0, Math.min(index, allowed));
    setParams(target ? { step: String(target) } : {});
  };

  const submit = () => {
    if (!scan?.files.length || !title.trim() || submitting.current) {
      if (!title.trim()) go(0);
      return;
    }
    submitting.current = true;
    create.mutate(
      { paths: scan.files.map((file) => file.path), title: title.trim(), profile: draft.profile, narrator: draft.narrator, start: draft.startNow },
      {
        onSuccess: (result) => {
          saveDraft(null);
          toast.success("Đã tạo sách", { description: draft.startNow ? "Đang khởi động - theo dõi tiến trình ngay trên trang sách." : undefined });
          navigate(`/studio/${result.id}`, { replace: true });
        },
        onError: (error: Error) => toast.error("Không tạo được sách", { description: error.message }),
        onSettled: () => {
          submitting.current = false;
        },
      },
    );
  };

  return (
    <div className="mx-auto max-w-[1180px] px-4 pb-16 pt-6 sm:px-10 sm:pt-9">
      <button type="button" onClick={() => navigate("/studio")} className="inline-flex items-center gap-1.5 text-sm text-fg-2 hover:text-fg">
        <ArrowLeft className="size-4" /> Studio
      </button>
      <h1 className="mt-4 text-2xl font-bold tracking-tight sm:text-[28px]">Tạo sách nói</h1>
      <div className="mt-6 flex flex-col gap-8 lg:flex-row lg:gap-10">
        <aside className="shrink-0 lg:w-56">
          <StepRail step={step} allowed={allowed} onGo={go} />
          {(draft.paths.length > 0 || draft.title) && (
            <button
              type="button"
              onClick={() => {
                saveDraft(null);
                setDraft(EMPTY_DRAFT);
                setRawScan(null);
                go(0);
              }}
              className="mt-4 px-2.5 text-[13px] text-fg-2 hover:text-fg"
            >
              Bắt đầu lại từ đầu
            </button>
          )}
        </aside>
        <section className="min-w-0 flex-1">
          {step === 0 && (
            <SourceStep
              scan={scan}
              title={title}
              onTitle={(value) => update({ title: value, titleEdited: true })}
              scanning={scanMutation.isPending}
              onPaths={(paths) => update({ paths, excluded: [], titleEdited: paths.length ? draft.titleEdited : false })}
              onAddFiles={(paths) => update({ paths: [...draft.paths, ...paths] })}
              onRemove={(path) => update({ excluded: [...draft.excluded, path] })}
              problem={problem}
            />
          )}
          {step === 1 && <VoiceStep narrator={draft.narrator} setNarrator={(narrator) => update({ narrator })} />}
          {step === 2 && scan && (
            <QualityStep profile={draft.profile} setProfile={(profile) => update({ profile })} words={scan.totals.words} chapters={scan.files.length} />
          )}
          {step === 3 && scan && (
            <ConfirmStep
              title={title.trim()}
              scan={scan}
              narrator={draft.narrator}
              profile={draft.profile}
              startNow={draft.startNow}
              setStartNow={(startNow) => update({ startNow })}
            />
          )}
          <div className="mt-8 flex items-center justify-between border-t border-line pt-5">
            <Button variant="ghost" icon={ArrowLeft} disabled={step === 0} onClick={() => go(step - 1)}>
              Quay lại
            </Button>
            {step < STEPS.length - 1 ? (
              <Button variant="primary" disabled={step >= allowed} onClick={() => go(step + 1)}>
                Tiếp tục <ArrowRight className="size-4" />
              </Button>
            ) : (
              <Button variant="primary" icon={draft.startNow ? Wand2 : Mic} loading={create.isPending} disabled={!title.trim()} onClick={submit}>
                {draft.startNow ? "Tạo và bắt đầu" : "Tạo sách"}
              </Button>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
