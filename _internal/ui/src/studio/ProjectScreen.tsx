import {
  AlertTriangle,
  ArrowLeft,
  BookOpenText,
  Headphones,
  Check,
  CircleAlert,
  FolderOpen,
  Mic2,
  Pause,
  Play,
  Square,
  Users,
  Wand2,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { BookCover } from "@/shared/BookCover";
import {
  Button,
  Dialog,
  EmptyState,
  IconButton,
  Progress,
  Segmented,
  Skeleton,
  StatusPill,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Vu,
} from "@/shared/ui";
import type { BookSummary, Chapter } from "@/studio/api";
import { cn } from "@/shared/cn";
import { phaseTone, useActivity, useBook, useReveal, useStart, useStop } from "@/studio/data";
import {
  formatClock,
  formatDate,
  formatEta,
  formatLength,
  formatNumber,
  formatPercent,
  formatRelative,
  formatTime,
} from "@/shared/format";
import { CastList } from "@/listen/BookScreen";
import { usePlayer } from "@/listen/player";
import { useSource } from "@/listen/source";

/** Phát một chương ngay trong Studio (nghe kiểm tra) bằng chính trình phát của phía Nghe. */
function usePlayChapter() {
  const source = useSource();
  const player = usePlayer();
  return async (bookId: string, chapterId: number) => {
    const book = await source.book(bookId);
    player.play(book, book.chapters ?? [], chapterId, 0);
  };
}

// ---- Sản xuất -------------------------------------------------------------------------------------------

type StepState = "done" | "active" | "paused" | "pending";

function stepStates(book: BookSummary): [StepState, StepState, StepState] {
  const live = book.running || book.starting;
  const now: StepState = live ? "active" : "paused";
  if (book.phase === "done") return ["done", "done", "done"];
  if (book.phase === "idle") return ["pending", "pending", "pending"];
  if (book.phase === "analysis") return [now, "pending", "pending"];
  if (book.phase === "casting") return ["done", now, "pending"];
  if (book.phase === "synthesis") return ["done", "done", now];
  // Đã dừng / lỗi: suy từ tiến độ.
  if (book.progress.analysis < 1) return [now, "pending", "pending"];
  if (book.progress.synthesis <= 0) return ["done", now, "pending"];
  return ["done", "done", now];
}

function Step({
  index,
  state,
  title,
  detail,
  progress,
  icon: Icon,
}: {
  index: number;
  state: StepState;
  title: string;
  detail: string;
  progress?: number;
  icon: typeof Wand2;
}) {
  return (
    <div className={cn("relative flex-1 rounded-xl border p-4", state === "active" ? "border-accent/40 bg-accent-soft" : "border-line bg-panel")}>
      <div className="flex items-center gap-2.5">
        <div
          className={cn(
            "grid size-7 place-items-center rounded-full text-xs font-bold",
            state === "done" && "bg-success text-white",
            state === "active" && "bg-accent text-accent-ink",
            state === "paused" && "bg-fg-3 text-bg",
            state === "pending" && "bg-hover text-fg-3",
          )}
        >
          {state === "done" ? <Check className="size-4" strokeWidth={3} /> : state === "active" ? <Icon className="size-3.5" /> : index}
        </div>
        <div className={cn("text-sm font-semibold", state === "pending" && "text-fg-3")}>{title}</div>
        {state === "active" && <Vu className="ml-auto h-3 text-accent" />}
        {state === "paused" && <Pause className="ml-auto size-3.5 text-fg-3" />}
      </div>
      <p className={cn("mt-2 text-xs leading-relaxed", state === "pending" ? "text-fg-3" : "text-fg-2")}>{detail}</p>
      {progress !== undefined && state !== "pending" && (
        <div className="mt-3 flex items-center gap-2">
          <Progress value={progress} running={state === "active"} tone={state === "done" ? "success" : state === "paused" ? "muted" : "accent"} size="sm" />
          <span className="tabular w-9 text-right text-xs font-semibold">{formatPercent(progress)}</span>
        </div>
      )}
    </div>
  );
}

function ProductionPanel({ book }: { book: BookSummary }) {
  const [analysis, casting, synthesis] = stepStates(book);
  const live = book.running || book.starting;
  const eta = book.eta ? formatEta(book.eta.seconds) : live ? "đang ước tính thời gian…" : "";
  return (
    <section className="mt-8">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-base font-semibold">Tiến trình sản xuất</h2>
        <div className="tabular text-sm text-fg-2">
          {formatPercent(book.progress.overall)} tổng
          {eta && <span className="text-fg-3"> · {eta}</span>}
        </div>
      </div>
      <div className="flex gap-3">
        <Step
          index={1}
          state={analysis}
          icon={BookOpenText}
          title="Phân tích truyện"
          detail="Đọc cả truyện để nhận ra lời thoại, ai đang nói và cảm xúc từng câu."
          progress={book.progress.analysis}
        />
        <Step
          index={2}
          state={casting}
          icon={Users}
          title="Phân vai"
          detail="Trao cho mỗi nhân vật một giọng riêng và khoá cách đọc tên."
        />
        <Step
          index={3}
          state={synthesis}
          icon={Mic2}
          title="Thu âm và kiểm tra"
          detail="Đọc từng câu, nghe lại bằng nhận dạng giọng nói, thu lại câu lệch."
          progress={book.progress.synthesis}
        />
      </div>
      {book.startError && (
        <div className="mt-3 flex gap-2 rounded-xl bg-danger-soft px-4 py-3 text-sm text-danger">
          <CircleAlert className="mt-0.5 size-4 shrink-0" />
          <span>Không khởi động được: {book.startError}</span>
        </div>
      )}
      {book.lastError && book.phase === "error" && (
        <div className="mt-3 flex gap-2 rounded-xl bg-danger-soft px-4 py-3 text-sm text-danger">
          <CircleAlert className="mt-0.5 size-4 shrink-0" />
          <span>{book.lastError}</span>
        </div>
      )}
    </section>
  );
}

// ---- Nút hành động ---------------------------------------------------------------------------------------

function StopDialog({ book, open, onOpenChange }: { book: BookSummary; open: boolean; onOpenChange: (open: boolean) => void }) {
  const stop = useStop();
  const inAnalysis = book.phase === "analysis";
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Dừng tạo sách nói?"
      description="Mọi chương và câu đã xong được giữ nguyên. Bấm “Tiếp tục” lúc nào cũng được."
    >
      {inAnalysis && (
        <div className="mb-5 flex gap-3 rounded-xl bg-warning-soft p-4 text-sm leading-relaxed text-fg">
          <AlertTriangle className="mt-0.5 size-5 shrink-0 text-warning" />
          <div>
            <div className="font-semibold">Đang ở giữa bước phân tích truyện</div>
            <p className="mt-1 text-fg-2">
              Dừng lúc này rồi chạy tiếp, phần phân tích sau chỗ dừng có thể nhận ra người nói khác một chút so với
              chạy liền một mạch - và kéo theo cách phân vai. Nên để chạy hết bước này
              {book.eta ? ` (${formatEta(book.eta.seconds)})` : ""}.
            </p>
          </div>
        </div>
      )}
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={() => onOpenChange(false)}>
          Để chạy tiếp
        </Button>
        <Button
          variant="danger"
          icon={Square}
          loading={stop.isPending}
          onClick={() => stop.mutate(book.id, { onSettled: () => onOpenChange(false) })}
        >
          Dừng
        </Button>
      </div>
    </Dialog>
  );
}

function Actions({ book }: { book: BookSummary }) {
  const start = useStart();
  const reveal = useReveal();
  const navigate = useNavigate();
  const [confirmStop, setConfirmStop] = useState(false);
  const live = book.running;
  return (
    <div className="mt-5 flex flex-wrap items-center gap-2">
      {book.chapters.completed > 0 && (
        <Button variant={book.phase === "done" ? "primary" : "secondary"} size="lg" icon={Headphones} onClick={() => navigate(`/book/${book.id}`)}>
          Nghe trong Thư viện
        </Button>
      )}
      {book.starting ? (
        <Button variant="primary" size="lg" loading>
          Đang khởi động
        </Button>
      ) : live ? (
        <Button variant="outline" size="lg" icon={Square} onClick={() => setConfirmStop(true)}>
          Dừng
        </Button>
      ) : book.phase === "idle" ? (
        <Button variant="primary" size="lg" icon={Wand2} loading={start.isPending} onClick={() => start.mutate(book.id)}>
          Bắt đầu tạo sách nói
        </Button>
      ) : book.phase !== "done" ? (
        <Button variant="primary" size="lg" icon={Play} loading={start.isPending} onClick={() => start.mutate(book.id)}>
          Tiếp tục tạo
        </Button>
      ) : null}
      <IconButton label="Mở thư mục sách" icon={FolderOpen} onClick={() => reveal.mutate(book.id)} />
      <StopDialog book={book} open={confirmStop} onOpenChange={setConfirmStop} />
    </div>
  );
}

// ---- Chương ------------------------------------------------------------------------------------------------

function chapterTone(chapter: Chapter) {
  if (chapter.status === "completed") return "success" as const;
  if (chapter.status === "failed") return "danger" as const;
  if (chapter.status === "synthesizing" || chapter.status === "verifying") return "accent" as const;
  return "muted" as const;
}

function ChapterRow({ book, chapter }: { book: BookSummary; chapter: Chapter }) {
  const player = usePlayer();
  const playChapter = usePlayChapter();
  const current = player.track?.bookId === book.id && player.track.chapterId === chapter.id;
  const working = chapter.status === "synthesizing" || chapter.status === "verifying";
  const recorded = chapter.segments.total ? chapter.segments.finished / chapter.segments.total : 0;
  const onPlay = () => {
    if (!chapter.playable) return;
    if (current) player.toggle();
    else void playChapter(book.id, chapter.id);
  };
  return (
    <div
      role="row"
      onDoubleClick={onPlay}
      className={cn(
        "group grid h-14 grid-cols-[48px_minmax(0,1fr)_150px_110px_72px] items-center gap-3 rounded-lg px-2 text-sm",
        current ? "bg-accent-soft" : "hover:bg-hover",
      )}
    >
      <div className="flex justify-center">
        {chapter.playable ? (
          <button
            type="button"
            onClick={onPlay}
            aria-label={current && player.playing ? `Tạm dừng ${chapter.displayTitle}` : `Nghe ${chapter.displayTitle}`}
            className="grid size-8 place-items-center rounded-full text-fg-2 hover:bg-panel hover:text-fg"
          >
            {current && player.playing ? (
              <>
                <Vu className="h-3 text-accent group-hover:hidden" />
                <Pause className="hidden size-4 group-hover:block" fill="currentColor" strokeWidth={0} />
              </>
            ) : (
              <>
                <span className="tabular text-xs text-fg-3 group-hover:hidden">{chapter.index}</span>
                <Play className="hidden size-4 translate-x-[1px] group-hover:block" fill="currentColor" strokeWidth={0} />
              </>
            )}
          </button>
        ) : (
          <span className="tabular text-xs text-fg-3">{chapter.index}</span>
        )}
      </div>
      <div className="min-w-0">
        <div className={cn("truncate font-medium", current && "text-accent-text")}>{chapter.displayTitle}</div>
        {chapter.lastError ? (
          <div className="truncate text-xs text-danger">{chapter.lastError}</div>
        ) : chapter.subtitle ? (
          <div className="truncate text-xs text-fg-2">{chapter.subtitle}</div>
        ) : null}
      </div>
      <div>
        {working ? (
          <div className="flex items-center gap-2">
            <Progress value={recorded} running size="xs" />
            <span className="tabular text-[11px] text-fg-3">
              {chapter.segments.finished}/{chapter.segments.total}
            </span>
          </div>
        ) : (
          <StatusPill label={chapter.statusLabel} tone={chapterTone(chapter)} />
        )}
      </div>
      <div className="tabular text-right text-xs text-fg-2">
        {chapter.status === "completed" ? formatLength(chapter.seconds) : chapter.segments.total ? `${formatNumber(chapter.segments.total)} câu` : ""}
      </div>
      <div className="tabular text-right text-xs text-fg-3">
        {chapter.completedAt ? formatRelative(chapter.completedAt) : ""}
      </div>
    </div>
  );
}

function ChapterList({ book, chapters }: { book: BookSummary; chapters: Chapter[] }) {
  return (
    <div role="table" aria-label="Danh sách chương" className="mt-2">
      <div className="grid h-9 grid-cols-[48px_minmax(0,1fr)_150px_110px_72px] items-center gap-3 border-b border-line px-2 text-[11px] font-semibold uppercase tracking-wider text-fg-3">
        <span className="text-center">#</span>
        <span>Chương</span>
        <span>Trạng thái</span>
        <span className="text-right">Độ dài</span>
        <span className="text-right">Xong lúc</span>
      </div>
      <div className="mt-1 space-y-px">
        {chapters.map((chapter) => (
          <ChapterRow key={chapter.id} book={book} chapter={chapter} />
        ))}
      </div>
    </div>
  );
}

// ---- Nhật ký ---------------------------------------------------------------------------------------------------

const LEVEL_DOT: Record<string, string> = {
  success: "bg-success",
  warning: "bg-warning",
  error: "bg-danger",
  info: "bg-fg-3",
};

function ActivityView({ book }: { book: BookSummary }) {
  const [mode, setMode] = useState<"story" | "technical">("story");
  const { data, isLoading } = useActivity(book.id, mode === "technical", book.running);
  const groups = useMemo(() => {
    const result: { day: string; items: NonNullable<typeof data> }[] = [];
    for (const item of data ?? []) {
      const day = formatDate(item.at);
      const last = result[result.length - 1];
      if (last && last.day === day) last.items.push(item);
      else result.push({ day, items: [item] });
    }
    return result;
  }, [data]);
  return (
    <div className="mt-5">
      <div className="flex items-center justify-between">
        <Segmented
          label="Kiểu nhật ký"
          value={mode}
          onChange={setMode}
          options={[
            { value: "story", label: "Diễn biến" },
            { value: "technical", label: "Chi tiết kỹ thuật" },
          ]}
        />
        <span className="text-xs text-fg-3">{data ? `${data.length} mục gần nhất` : ""}</span>
      </div>
      {isLoading ? (
        <div className="mt-6 space-y-3">
          {Array.from({ length: 6 }, (_, index) => (
            <Skeleton key={index} className="h-5 w-2/3" />
          ))}
        </div>
      ) : !groups.length ? (
        <EmptyState icon={BookOpenText} title="Chưa có gì" className="mt-4">
          Diễn biến sẽ hiện ở đây khi sách bắt đầu chạy.
        </EmptyState>
      ) : mode === "technical" ? (
        <div className="mt-4 max-h-[560px] overflow-auto rounded-xl border border-line bg-sunken p-3 font-mono text-[12px] leading-relaxed">
          {(data ?? []).map((item) => (
            <div key={item.id} className="flex gap-3 whitespace-pre-wrap break-words">
              <span className="shrink-0 text-fg-3">{formatTime(item.at)}</span>
              <span className={cn("shrink-0", item.level === "error" ? "text-danger" : item.level === "warning" ? "text-warning" : "text-fg-3")}>
                {item.code}
              </span>
              <span className="text-fg-2">{item.text}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-4 space-y-6">
          {groups.map((group) => (
            <section key={group.day}>
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-fg-3">{group.day}</h4>
              <ol className="relative space-y-1 border-l border-line pl-5">
                {group.items.map((item) => (
                  <li key={item.id} className="relative py-1.5 text-sm">
                    <span className={cn("absolute -left-[25px] top-[13px] size-2 rounded-full ring-4 ring-bg", LEVEL_DOT[item.level] ?? "bg-fg-3")} />
                    <span className="tabular mr-3 text-xs text-fg-3">{formatTime(item.at).split(" · ")[0]}</span>
                    <span className={cn(item.level === "warning" && "text-fg", item.level === "info" && "text-fg-2")}>{item.text}</span>
                  </li>
                ))}
              </ol>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

// ---- Trang -----------------------------------------------------------------------------------------------------------

export function ProjectScreen() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "chapters";
  const { data, isLoading, error } = useBook(id);

  if (isLoading) {
    return (
      <div className="mx-auto max-w-[1180px] px-10 pt-9">
        <Skeleton className="h-5 w-24" />
        <div className="mt-6 flex gap-7">
          <Skeleton className="size-44 rounded-lg" />
          <div className="flex-1 space-y-3 pt-4">
            <Skeleton className="h-8 w-2/3" />
            <Skeleton className="h-4 w-1/3" />
          </div>
        </div>
      </div>
    );
  }
  if (error || !data) {
    return (
      <EmptyState
        icon={CircleAlert}
        title="Không mở được sách"
        className="mt-20"
        action={<Button onClick={() => navigate("/studio")}>Về Studio</Button>}
      >
        {(error as Error | null)?.message ?? "Sách có thể đã bị chuyển hoặc xoá."}
      </EmptyState>
    );
  }

  const { book, chapters } = data;
  const live = book.running || book.starting;
  const meta = [
    `${book.chapters.total} chương`,
    book.settings.narrator && `Giọng kể ${book.settings.narrator}`,
    book.settings.profileLabel,
    book.createdAt && `Tạo ${formatDate(book.createdAt)}`,
  ].filter(Boolean);

  return (
    <div className="mx-auto max-w-[1180px] px-10 pb-16 pt-7">
      <button type="button" onClick={() => navigate("/studio")} className="inline-flex items-center gap-1.5 text-sm text-fg-2 hover:text-fg">
        <ArrowLeft className="size-4" /> Studio
      </button>
      <header className="mt-5 flex gap-7">
        <BookCover title={book.title} size="lg" className="w-44" />
        <div className="min-w-0 flex-1 pt-1">
          <StatusPill label={book.starting ? "Đang khởi động" : book.statusLabel} tone={phaseTone(book.phase, live)} live={live} />
          <h1 className="mt-3 text-[30px] font-bold leading-tight tracking-tight">{book.title}</h1>
          <p className="mt-2 text-sm text-fg-2">{meta.join(" · ")}</p>
          {book.phase === "done" || book.audioSeconds > 0 ? (
            <p className="tabular mt-1 text-sm text-fg-2">
              {formatLength(book.audioSeconds)} audio · {book.chapters.completed}/{book.chapters.total} chương nghe được
              {book.position && (
                <span className="text-fg-3"> · lần nghe cuối {formatRelative(book.position.at)} ở {formatClock(book.position.seconds)}</span>
              )}
            </p>
          ) : null}
          <Actions book={book} />
        </div>
      </header>

      {book.phase !== "done" && <ProductionPanel book={book} />}

      <Tabs value={tab} onValueChange={(value) => setParams({ tab: value }, { replace: true })} className="mt-9">
        <TabsList>
          <TabsTrigger value="chapters" count={chapters.length}>
            Chương
          </TabsTrigger>
          <TabsTrigger value="cast">Nhân vật</TabsTrigger>
          <TabsTrigger value="activity">Nhật ký</TabsTrigger>
        </TabsList>
        <TabsContent value="chapters">
          <ChapterList book={book} chapters={chapters} />
        </TabsContent>
        <TabsContent value="cast">
          <CastList bookId={book.id} />
        </TabsContent>
        <TabsContent value="activity">
          <ActivityView book={book} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
