import * as Switch from "@radix-ui/react-switch";
import {
  ArrowLeft,
  ArrowRight,
  Check,
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
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { BookCover } from "@/shared/BookCover";
import { Button, Segmented, Tooltip, Vu } from "@/shared/ui";
import type { ScanResult, Voice } from "@/studio/api";
import { useSource } from "@/listen/source";
import { cn } from "@/shared/cn";
import { pickFiles, pickFolder, useAppInfo, useCreateBook, useScan, useVoices } from "@/studio/data";
import { formatLength, formatNumber } from "@/shared/format";
import { useClip } from "@/listen/clip";

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
    points: ["Model phân tích nhỏ, đọc từng khối lớn", "Tự kiểm tra ở mức cơ bản", "Thu lại tối đa 1 lần khi đọc lệch"],
  },
  {
    value: "balanced",
    title: "Cân bằng",
    pace: "Vừa phải",
    summary: "Nghe hằng ngày, chấp nhận vài câu chưa hoàn hảo.",
    points: ["Model phân tích đầy đủ", "Tự kiểm tra ở mức cơ bản", "Thu lại tối đa 2 lần khi đọc lệch"],
  },
  {
    value: "high_quality",
    title: "Chất lượng cao",
    pace: "Chậm nhất, kỹ nhất",
    summary: "Sách nghe lại nhiều lần hoặc để chia sẻ.",
    points: [
      "Đạo diễn AI rà lại cảm xúc từng câu",
      "Nghe lại mọi câu bằng nhận dạng giọng nói, ngưỡng chặt",
      "Thu lại tới 5 lần cho câu đọc lệch",
    ],
  },
];

function StepRail({ step, reached, onGo }: { step: number; reached: number; onGo: (index: number) => void }) {
  return (
    <ol className="space-y-1">
      {STEPS.map((item, index) => {
        const done = index < step;
        const current = index === step;
        const enabled = index <= reached;
        return (
          <li key={item.title}>
            <button
              type="button"
              disabled={!enabled}
              onClick={() => onGo(index)}
              className={cn(
                "flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-left transition-colors disabled:opacity-50",
                current ? "bg-hover" : enabled && "hover:bg-hover",
              )}
            >
              <span
                className={cn(
                  "grid size-7 shrink-0 place-items-center rounded-full text-xs font-bold",
                  done ? "bg-success text-white" : current ? "bg-accent text-accent-ink" : "bg-hover text-fg-3",
                )}
              >
                {done ? <Check className="size-4" strokeWidth={3} /> : index + 1}
              </span>
              <span>
                <span className={cn("block text-sm font-medium", !current && !done && "text-fg-2")}>{item.title}</span>
                <span className="block text-xs text-fg-3">{item.hint}</span>
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
  paths,
  setPaths,
  scan,
  title,
  setTitle,
  scanning,
}: {
  paths: string[];
  setPaths: (paths: string[]) => void;
  scan: ScanResult | null;
  title: string;
  setTitle: (title: string) => void;
  scanning: boolean;
}) {
  const { data: info } = useAppInfo();
  const [typed, setTyped] = useState("");
  const chooseFolder = async () => {
    const path = await pickFolder("Chọn thư mục chứa các chương TXT").catch((error: Error) => {
      toast.error(error.message);
      return null;
    });
    if (path) setPaths([path]);
  };
  const chooseFiles = async () => {
    const chosen = await pickFiles("Chọn các chương TXT").catch((error: Error) => {
      toast.error(error.message);
      return [];
    });
    if (chosen.length) setPaths([...paths, ...chosen]);
  };
  const removeFile = (path: string) => {
    const files = scan?.files.map((file) => file.path).filter((item) => item !== path) ?? [];
    setPaths(files);
  };
  return (
    <div>
      <h2 className="text-xl font-semibold">Chọn các chương của truyện</h2>
      <p className="mt-1 text-sm text-fg-2">
        Mỗi file TXT là một chương. Chương được xếp theo tên file như người đọc mong đợi: 2 đứng trước 10.
      </p>
      {!scan?.files.length ? (
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
              <Button icon={FileText} onClick={() => void chooseFiles()}>
                Chọn từng file
              </Button>
            </div>
          )}
          <form
            className="mx-auto mt-5 flex max-w-lg gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (typed.trim()) setPaths([typed.trim()]);
            }}
          >
            <input
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
              placeholder={info?.dialogs ? "…hoặc dán đường dẫn thư mục" : "Dán đường dẫn thư mục, ví dụ D:\\Truyện\\Tên truyện"}
              className="h-9 flex-1 rounded-lg border border-line bg-bg px-3 text-sm outline-none placeholder:text-fg-3 focus:border-accent"
            />
            <Button type="submit" disabled={!typed.trim()}>
              Mở
            </Button>
          </form>
        </div>
      ) : (
        <>
          <label className="mt-6 block">
            <span className="text-sm font-medium">Tên sách</span>
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              className="mt-1.5 h-11 w-full rounded-xl border border-line bg-panel px-3.5 text-[15px] font-medium outline-none focus:border-accent"
              placeholder="Tên hiển thị trong thư viện"
            />
          </label>
          <div className="mt-5 flex items-center justify-between">
            <div className="tabular text-sm text-fg-2">
              <span className="font-semibold text-fg">{scan.totals.chapters} chương</span> ·{" "}
              {formatNumber(scan.totals.words)} chữ · khoảng {formatLength(scan.totals.audioSeconds)} audio
            </div>
            <div className="flex gap-1">
              {info?.dialogs && (
                <Button size="sm" variant="ghost" icon={FileText} onClick={() => void chooseFiles()}>
                  Thêm file
                </Button>
              )}
              <Button size="sm" variant="ghost" onClick={() => setPaths([])}>
                Chọn lại
              </Button>
            </div>
          </div>
          <div className="mt-3 max-h-[340px] overflow-y-auto rounded-xl border border-line bg-panel">
            {scan.files.map((file, index) => (
              <div key={file.path} className="group grid grid-cols-[40px_minmax(0,1fr)_90px_36px] items-center gap-2 border-b border-line px-3 py-2 last:border-b-0">
                <span className="tabular text-xs text-fg-3">{index + 1}</span>
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{file.firstLine || file.title}</div>
                  <div className="truncate text-xs text-fg-3">{file.name}</div>
                </div>
                <span className="tabular text-right text-xs text-fg-2">{formatNumber(file.words)} chữ</span>
                <Tooltip label="Bỏ chương này">
                  <button
                    type="button"
                    aria-label={`Bỏ ${file.name}`}
                    onClick={() => removeFile(file.path)}
                    className="grid size-8 place-items-center rounded-md text-fg-3 opacity-0 hover:bg-hover hover:text-danger group-hover:opacity-100 focus-visible:opacity-100"
                  >
                    <Trash2 className="size-4" />
                  </button>
                </Tooltip>
              </div>
            ))}
          </div>
          {scan.skipped.length > 0 && (
            <p className="mt-2 text-xs text-fg-3">Bỏ qua {scan.skipped.length} file không phải .txt.</p>
          )}
        </>
      )}
    </div>
  );
}

// ---- Bước 2 ---------------------------------------------------------------------------------------------------

function VoiceCard({ voice, selected, onSelect }: { voice: Voice; selected: boolean; onSelect: () => void }) {
  const clip = useClip();
  const source = useSource();
  const id = `voice-${voice.name}`;
  const playing = clip.current === id;
  return (
    <div
      role="radio"
      aria-checked={selected}
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect();
        }
      }}
      className={cn(
        "relative flex items-center gap-3 rounded-xl border bg-panel p-3.5 transition-colors",
        selected ? "border-accent ring-1 ring-accent" : "border-line hover:border-line-strong",
      )}
    >
      <button
        type="button"
        aria-label={playing ? `Dừng nghe ${voice.name}` : `Nghe thử ${voice.name}`}
        onClick={(event) => {
          event.stopPropagation();
          clip.toggle(id, source.voiceUrl(voice.name));
        }}
        className={cn(
          "grid size-10 shrink-0 place-items-center rounded-full transition-colors",
          playing ? "bg-accent text-accent-ink" : "bg-hover text-fg hover:bg-line",
        )}
      >
        {playing ? <Vu className="h-3" /> : <Play className="size-4 translate-x-[1px]" fill="currentColor" strokeWidth={0} />}
      </button>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate font-semibold">{voice.name}</span>
          {voice.recommended && (
            <span className="rounded-md bg-accent-soft px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide text-accent-text">
              Đề xuất
            </span>
          )}
        </div>
        <div className="mt-0.5 text-xs text-fg-2">
          {voice.gender} · Miền {voice.region} · {voice.style}
        </div>
      </div>
      {selected && (
        <span className="grid size-6 place-items-center rounded-full bg-accent text-accent-ink">
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
  const shown = (voices ?? []).filter(
    (voice) => (gender === "all" || voice.gender === gender) && (region === "all" || voice.region === region),
  );
  return (
    <div>
      <h2 className="text-xl font-semibold">Chọn giọng kể chuyện</h2>
      <p className="mt-1 max-w-2xl text-sm text-fg-2">
        Giọng này đọc toàn bộ lời dẫn truyện. Mỗi nhân vật sẽ được tự động trao một giọng riêng sau bước phân tích -
        bạn không cần chọn trước.
      </p>
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <Segmented label="Giới tính" value={gender} onChange={setGender} options={[
          { value: "all", label: "Tất cả" },
          { value: "Nam", label: "Nam" },
          { value: "Nữ", label: "Nữ" },
        ]} />
        <Segmented label="Miền" value={region} onChange={setRegion} options={[
          { value: "all", label: "Mọi miền" },
          { value: "Bắc", label: "Bắc" },
          { value: "Nam", label: "Nam" },
          { value: "Trung", label: "Trung" },
        ]} />
      </div>
      <div role="radiogroup" aria-label="Giọng kể chuyện" className="mt-4 grid grid-cols-2 gap-3 xl:grid-cols-3">
        {shown.map((voice) => (
          <VoiceCard key={voice.name} voice={voice} selected={voice.name === narrator} onSelect={() => setNarrator(voice.name)} />
        ))}
      </div>
    </div>
  );
}

// ---- Bước 3 ---------------------------------------------------------------------------------------------------

function QualityStep({ profile, setProfile }: { profile: Profile; setProfile: (profile: Profile) => void }) {
  return (
    <div>
      <h2 className="text-xl font-semibold">Chọn mức chất lượng</h2>
      <p className="mt-1 text-sm text-fg-2">Mức này được khoá cùng sách để mọi chương đọc giống nhau từ đầu tới cuối.</p>
      <div role="radiogroup" aria-label="Chất lượng" className="mt-6 grid grid-cols-3 gap-4">
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
  const rows: [string, string][] = [
    ["Chương", `${scan.totals.chapters} chương · ${formatNumber(scan.totals.words)} chữ`],
    ["Độ dài ước tính", `khoảng ${formatLength(scan.totals.audioSeconds)}`],
    ["Giọng kể", narrator],
    ["Nhân vật", "Tự động phân vai sau khi phân tích"],
    ["Chất lượng", option.title],
  ];
  return (
    <div>
      <h2 className="text-xl font-semibold">Xem lại trước khi tạo</h2>
      <div className="mt-6 flex gap-6 rounded-2xl border border-line bg-panel p-6">
        <BookCover title={title} size="lg" className="w-40" />
        <div className="min-w-0 flex-1">
          <h3 className="text-lg font-semibold">{title}</h3>
          <dl className="mt-3 divide-y divide-line text-sm">
            {rows.map(([label, value]) => (
              <div key={label} className="flex justify-between gap-4 py-2">
                <dt className="text-fg-2">{label}</dt>
                <dd className="text-right font-medium">{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
      <label className="mt-5 flex cursor-default items-start gap-3 rounded-xl border border-line bg-panel p-4">
        <Switch.Root
          checked={startNow}
          onCheckedChange={setStartNow}
          className="relative mt-0.5 h-6 w-10 shrink-0 rounded-full bg-line-strong transition-colors data-[state=checked]:bg-accent"
        >
          <Switch.Thumb className="block size-5 translate-x-0.5 rounded-full bg-white shadow transition-transform data-[state=checked]:translate-x-[18px]" />
        </Switch.Root>
        <span>
          <span className="block text-sm font-medium">Bắt đầu tạo ngay</span>
          <span className="mt-0.5 block text-xs leading-relaxed text-fg-2">
            Sách chạy nền: đóng cửa sổ vẫn tiếp tục, Windows báo khi xong. Chương nào xong là nghe được chương đó, không
            phải chờ cả cuốn.
          </span>
        </span>
      </label>
    </div>
  );
}

// ---- Trang ------------------------------------------------------------------------------------------------------

export function NewProjectScreen() {
  const navigate = useNavigate();
  const scanMutation = useScan();
  const create = useCreateBook();
  const { data: voices } = useVoices();
  const [step, setStep] = useState(0);
  const [reached, setReached] = useState(0);
  const [paths, setPaths] = useState<string[]>([]);
  const [scan, setScan] = useState<ScanResult | null>(null);
  const [title, setTitle] = useState("");
  const [narrator, setNarrator] = useState("");
  const [profile, setProfile] = useState<Profile>("high_quality");
  const [startNow, setStartNow] = useState(true);

  useEffect(() => {
    if (!narrator && voices?.length) setNarrator(voices.find((voice) => voice.recommended)?.name ?? voices[0].name);
  }, [voices, narrator]);

  useEffect(() => {
    if (!paths.length) {
      setScan(null);
      return;
    }
    scanMutation.mutate(paths, {
      onSuccess: (result) => {
        setScan(result);
        setTitle((current) => current || result.suggestedTitle);
        if (!result.files.length) toast.error("Không thấy file .txt nào ở đó");
      },
      onError: (error: Error) => toast.error("Không đọc được", { description: error.message }),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paths]);

  const canNext = useMemo(() => {
    if (step === 0) return Boolean(scan?.files.length && title.trim());
    if (step === 1) return Boolean(narrator);
    return true;
  }, [step, scan, title, narrator]);

  const go = (index: number) => {
    setStep(index);
    setReached((value) => Math.max(value, index));
  };

  const submit = () => {
    if (!scan) return;
    create.mutate(
      { paths: scan.files.map((file) => file.path), title: title.trim(), profile, narrator, start: startNow },
      {
        onSuccess: (result) => {
          toast.success("Đã tạo sách", { description: startNow ? "Đang khởi động - theo dõi tiến trình ngay trên trang sách." : undefined });
          navigate(`/studio/${result.id}`);
        },
        onError: (error: Error) => toast.error("Không tạo được sách", { description: error.message }),
      },
    );
  };

  return (
    <div className="mx-auto flex max-w-[1180px] gap-10 px-10 pb-16 pt-7">
      <aside className="w-56 shrink-0">
        <button type="button" onClick={() => navigate("/studio")} className="inline-flex items-center gap-1.5 text-sm text-fg-2 hover:text-fg">
          <ArrowLeft className="size-4" /> Studio
        </button>
        <h1 className="mb-5 mt-5 text-lg font-bold">Tạo sách nói</h1>
        <StepRail step={step} reached={reached} onGo={go} />
      </aside>
      <section className="min-w-0 flex-1 pt-11">
        {step === 0 && (
          <SourceStep paths={paths} setPaths={setPaths} scan={scan} title={title} setTitle={setTitle} scanning={scanMutation.isPending} />
        )}
        {step === 1 && <VoiceStep narrator={narrator} setNarrator={setNarrator} />}
        {step === 2 && <QualityStep profile={profile} setProfile={setProfile} />}
        {step === 3 && scan && (
          <ConfirmStep title={title.trim()} scan={scan} narrator={narrator} profile={profile} startNow={startNow} setStartNow={setStartNow} />
        )}
        <div className="mt-8 flex items-center justify-between border-t border-line pt-5">
          <Button variant="ghost" icon={ArrowLeft} disabled={step === 0} onClick={() => go(step - 1)}>
            Quay lại
          </Button>
          {step < STEPS.length - 1 ? (
            <Button variant="primary" disabled={!canNext} onClick={() => go(step + 1)}>
              Tiếp tục <ArrowRight className="size-4" />
            </Button>
          ) : (
            <Button variant="primary" size="lg" icon={startNow ? Wand2 : Mic} loading={create.isPending} onClick={submit}>
              {startNow ? "Tạo và bắt đầu" : "Tạo sách"}
            </Button>
          )}
        </div>
      </section>
    </div>
  );
}
