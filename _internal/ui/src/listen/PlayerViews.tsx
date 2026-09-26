import * as Popover from "@radix-ui/react-popover";
import * as Slider from "@radix-ui/react-slider";
import { AnimatePresence, motion } from "motion/react";
import {
  Bookmark as BookmarkIcon,
  BookmarkPlus,
  ChevronDown,
  Gauge,
  ListOrdered,
  Loader2,
  Maximize2,
  Moon,
  Pause,
  Pencil,
  Play,
  RotateCcw,
  RotateCw,
  SkipBack,
  SkipForward,
  Text,
  Trash2,
  Volume1,
  Volume2,
  VolumeX,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { BookCover } from "@/shared/BookCover";
import { cn } from "@/shared/cn";
import { formatClock, formatLength, formatRelative } from "@/shared/format";
import { IconButton, Tooltip, Vu } from "@/shared/ui";
import type { Bookmark } from "./model";
import { SKIP_SECONDS, SPEEDS, usePlayer, type SleepMode } from "./player";
import { useListenBook, useListenMutations, useScript } from "./source";

export function speedLabel(rate: number): string {
  return `${rate.toLocaleString("vi-VN", { maximumFractionDigits: 2 })}×`;
}

// ---- Thanh tua -------------------------------------------------------------------------------------------

function SeekBar({ large = false }: { large?: boolean }) {
  const { time, duration, seek } = usePlayer();
  const [dragging, setDragging] = useState<number | null>(null);
  const shown = dragging ?? time;
  const max = duration > 0 ? duration : 1;
  return (
    <div className={cn("w-full", large ? "space-y-1.5" : "flex items-center gap-3")}>
      {!large && <span className="tabular w-11 text-right text-[11px] text-fg-2">{formatClock(shown)}</span>}
      <Slider.Root
        className={cn("group relative flex touch-none select-none items-center", large ? "h-5 w-full" : "h-4 flex-1")}
        min={0}
        max={max}
        step={1}
        value={[Math.min(shown, max)]}
        onValueChange={([value]) => setDragging(value)}
        onValueCommit={([value]) => {
          seek(value);
          setDragging(null);
        }}
        aria-label="Vị trí trong chương"
        disabled={!duration}
      >
        <Slider.Track className={cn("relative grow overflow-hidden rounded-full bg-line", large ? "h-1.5" : "h-1")}>
          <Slider.Range className="absolute h-full rounded-full bg-fg group-hover:bg-accent" />
        </Slider.Track>
        <Slider.Thumb
          className={cn(
            "block rounded-full bg-fg shadow transition-opacity focus:outline-none",
            large ? "size-4 opacity-100" : "size-3 opacity-0 group-hover:opacity-100 focus:opacity-100",
          )}
        />
      </Slider.Root>
      {large ? (
        <div className="tabular flex justify-between text-xs text-fg-2">
          <span>{formatClock(shown)}</span>
          <span>-{formatClock(Math.max(0, duration - shown))}</span>
        </div>
      ) : (
        <span className="tabular w-11 text-[11px] text-fg-3">-{formatClock(Math.max(0, duration - shown))}</span>
      )}
    </div>
  );
}

// ---- Nút điều khiển ------------------------------------------------------------------------------------

function Transport({ large = false }: { large?: boolean }) {
  const { playing, buffering, toggle, skip, next, previous } = usePlayer();
  return (
    <div className={cn("flex items-center", large ? "gap-4 sm:gap-6" : "gap-1")}>
      <IconButton label="Chương trước (Shift+←)" icon={SkipBack} size={large ? "lg" : "sm"} onClick={previous} />
      <IconButton label={`Lùi ${SKIP_SECONDS} giây (←)`} icon={RotateCcw} size={large ? "lg" : "sm"} onClick={() => skip(-SKIP_SECONDS)} />
      <button
        type="button"
        onClick={toggle}
        aria-label={playing ? "Tạm dừng (Space)" : "Phát (Space)"}
        className={cn(
          "grid place-items-center rounded-full bg-fg text-bg shadow-card transition-transform hover:scale-105 active:scale-95",
          large ? "size-16" : "size-10",
        )}
      >
        {buffering && playing ? (
          <Loader2 className={cn("animate-spin", large ? "size-7" : "size-5")} />
        ) : playing ? (
          <Pause className={large ? "size-7" : "size-5"} fill="currentColor" strokeWidth={0} />
        ) : (
          <Play className={cn(large ? "size-7" : "size-5", "translate-x-[1px]")} fill="currentColor" strokeWidth={0} />
        )}
      </button>
      <IconButton label={`Tới ${SKIP_SECONDS} giây (→)`} icon={RotateCw} size={large ? "lg" : "sm"} onClick={() => skip(SKIP_SECONDS)} />
      <IconButton label="Chương sau (Shift+→)" icon={SkipForward} size={large ? "lg" : "sm"} onClick={next} />
    </div>
  );
}

function MenuShell({ trigger, label, children, active }: { trigger: ReactNode; label: string; children: ReactNode; active?: boolean }) {
  return (
    <Popover.Root>
      <Tooltip label={label}>
        <Popover.Trigger asChild>
          <button
            type="button"
            aria-label={label}
            className={cn(
              "tabular inline-flex h-9 min-w-9 items-center justify-center gap-1 rounded-lg px-2 text-[13px] font-semibold transition-colors hover:bg-hover",
              active ? "text-accent-text" : "text-fg-2",
            )}
          >
            {trigger}
          </button>
        </Popover.Trigger>
      </Tooltip>
      <Popover.Portal>
        <Popover.Content sideOffset={8} collisionPadding={12} className="z-50 w-52 rounded-xl border border-line bg-panel p-1.5 shadow-float">
          {children}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

export function SpeedMenu() {
  const { rate, setRate } = usePlayer();
  return (
    <MenuShell label="Tốc độ đọc" active={rate !== 1} trigger={<><Gauge className="size-4" />{speedLabel(rate)}</>}>
      <div className="px-2 pb-1 pt-1 text-xs font-medium text-fg-3">Tốc độ đọc · nhớ riêng cho cuốn này</div>
      <div className="grid grid-cols-3 gap-1 p-1">
        {SPEEDS.map((speed) => (
          <Popover.Close asChild key={speed}>
            <button
              type="button"
              onClick={() => setRate(speed)}
              className={cn(
                "tabular h-9 rounded-lg text-sm hover:bg-hover",
                speed === rate ? "bg-accent-soft font-semibold text-accent-text" : "text-fg",
              )}
            >
              {speedLabel(speed)}
            </button>
          </Popover.Close>
        ))}
      </div>
    </MenuShell>
  );
}

function sleepLabel(mode: SleepMode, now: number): string {
  if (mode.kind === "minutes") return `${Math.max(1, Math.ceil((mode.endsAt - now) / 60000))}′`;
  if (mode.kind === "chapter") return "hết chương";
  return "";
}

export function SleepMenu() {
  const { sleep, setSleep } = usePlayer();
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (sleep.kind !== "minutes") return;
    const timer = window.setInterval(() => setNow(Date.now()), 10000);
    return () => window.clearInterval(timer);
  }, [sleep]);
  return (
    <MenuShell
      label="Hẹn giờ tắt"
      active={sleep.kind !== "off"}
      trigger={<><Moon className="size-4" />{sleep.kind !== "off" && <span>{sleepLabel(sleep, now)}</span>}</>}
    >
      <div className="px-2 pb-1 pt-1 text-xs font-medium text-fg-3">Dừng phát sau</div>
      {[5, 15, 30, 45, 60].map((minutes) => (
        <Popover.Close asChild key={minutes}>
          <button
            type="button"
            onClick={() => setSleep({ kind: "minutes", minutes, endsAt: Date.now() + minutes * 60000 })}
            className="flex h-8 w-full items-center rounded-lg px-2 text-sm hover:bg-hover"
          >
            {minutes} phút
          </button>
        </Popover.Close>
      ))}
      <Popover.Close asChild>
        <button type="button" onClick={() => setSleep({ kind: "chapter" })} className="flex h-8 w-full items-center rounded-lg px-2 text-sm hover:bg-hover">
          Hết chương này
        </button>
      </Popover.Close>
      {sleep.kind !== "off" && (
        <Popover.Close asChild>
          <button type="button" onClick={() => setSleep({ kind: "off" })} className="flex h-8 w-full items-center rounded-lg px-2 text-sm text-danger hover:bg-hover">
            Tắt hẹn giờ
          </button>
        </Popover.Close>
      )}
      <p className="px-2 pb-1 pt-2 text-[11px] leading-snug text-fg-3">Tiếng nhỏ dần 10 giây trước khi dừng.</p>
    </MenuShell>
  );
}

function VolumeControl() {
  const { volume, setVolume } = usePlayer();
  const Icon = volume === 0 ? VolumeX : volume < 0.5 ? Volume1 : Volume2;
  const remembered = useRef(volume || 0.9);
  return (
    <div className="hidden items-center gap-1 md:flex">
      <IconButton
        label={volume === 0 ? "Bật tiếng" : "Tắt tiếng"}
        icon={Icon}
        size="sm"
        onClick={() => {
          if (volume === 0) setVolume(remembered.current);
          else {
            remembered.current = volume;
            setVolume(0);
          }
        }}
      />
      <Slider.Root
        className="group relative flex h-4 w-20 touch-none select-none items-center"
        min={0}
        max={1}
        step={0.01}
        value={[volume]}
        onValueChange={([value]) => setVolume(value)}
        aria-label="Âm lượng"
      >
        <Slider.Track className="relative h-1 grow overflow-hidden rounded-full bg-line">
          <Slider.Range className="absolute h-full rounded-full bg-fg-2 group-hover:bg-accent" />
        </Slider.Track>
        <Slider.Thumb className="block size-3 rounded-full bg-fg opacity-0 shadow group-hover:opacity-100 focus:opacity-100 focus:outline-none" />
      </Slider.Root>
    </div>
  );
}

function BookmarkButton() {
  const { addBookmark, time } = usePlayer();
  return (
    <IconButton
      label="Thêm dấu trang ở chỗ này"
      icon={BookmarkPlus}
      size="sm"
      onClick={async () => {
        const mark = await addBookmark().catch(() => null);
        if (mark) toast.success("Đã thêm dấu trang", { description: `Ở ${formatClock(time)}` });
      }}
    />
  );
}

// ---- Thanh phát nhỏ ------------------------------------------------------------------------------------

export function PlayerBar({ compact = false }: { compact?: boolean }) {
  const { track, error, setExpanded, close, playing, toggle, time, duration } = usePlayer();
  if (!track) return null;
  if (compact) {
    return (
      <div className="relative z-20 shrink-0 border-t border-line bg-panel">
        <div className="absolute inset-x-0 top-0 h-[2px] bg-line">
          <div className="h-full bg-accent" style={{ width: `${duration ? (time / duration) * 100 : 0}%` }} />
        </div>
        <div className="flex h-16 items-center gap-3 px-3">
          <button type="button" onClick={() => setExpanded(true)} className="flex min-w-0 flex-1 items-center gap-3 text-left" aria-label="Mở màn hình đang nghe">
            <BookCover title={track.bookTitle} size="sm" className="size-11" />
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold">{track.chapterTitle}</div>
              <div className={cn("truncate text-xs", error ? "text-danger" : "text-fg-2")}>{error || track.bookTitle}</div>
            </div>
          </button>
          <button
            type="button"
            onClick={toggle}
            aria-label={playing ? "Tạm dừng" : "Phát"}
            className="grid size-11 shrink-0 place-items-center rounded-full bg-fg text-bg"
          >
            {playing ? <Pause className="size-5" fill="currentColor" strokeWidth={0} /> : <Play className="size-5 translate-x-[1px]" fill="currentColor" strokeWidth={0} />}
          </button>
        </div>
      </div>
    );
  }
  return (
    <div className="relative z-20 flex h-[76px] shrink-0 items-center gap-4 border-t border-line bg-panel px-4">
      <button
        type="button"
        onClick={() => setExpanded(true)}
        className="flex w-[28%] min-w-0 items-center gap-3 rounded-lg p-1 text-left hover:bg-hover"
        aria-label="Mở màn hình đang nghe"
      >
        <BookCover title={track.bookTitle} size="sm" className="size-12" />
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold">{track.chapterTitle}</div>
          <div className={cn("truncate text-xs", error ? "text-danger" : "text-fg-2")}>{error || track.bookTitle}</div>
        </div>
      </button>
      <div className="flex flex-1 flex-col items-center gap-0.5">
        <Transport />
        <div className="w-full max-w-xl">
          <SeekBar />
        </div>
      </div>
      <div className="flex w-[28%] items-center justify-end gap-0.5">
        <SpeedMenu />
        <SleepMenu />
        <BookmarkButton />
        <VolumeControl />
        <IconButton label="Mở màn hình đang nghe" icon={Maximize2} size="sm" onClick={() => setExpanded(true)} />
        <IconButton label="Đóng trình phát" icon={X} size="sm" onClick={close} />
      </div>
    </div>
  );
}

// ---- Bảng bên của màn hình đang nghe ---------------------------------------------------------------------

function ReadAlong() {
  const { track, time, seek, playing } = usePlayer();
  const { data: script, isLoading } = useScript(track?.bookId, track?.chapterId);
  const container = useRef<HTMLDivElement | null>(null);
  const userScrolledAt = useRef(0);
  const active = useMemo(() => {
    if (!script?.timed) return -1;
    let found = -1;
    for (let index = 0; index < script.segments.length; index += 1) {
      if ((script.segments[index].start ?? 0) <= time + 0.05) found = index;
      else break;
    }
    return found;
  }, [script, time]);

  useEffect(() => {
    if (active < 0 || !container.current || Date.now() - userScrolledAt.current < 6000) return;
    const element = container.current.querySelector<HTMLElement>(`[data-index="${active}"]`);
    element?.scrollIntoView({ block: "center", behavior: playing ? "smooth" : "auto" });
  }, [active, playing]);

  if (isLoading) return <div className="p-10 text-fg-3">Đang mở văn bản chương…</div>;
  if (!script) return null;
  const paragraphs: { key: number; items: { index: number; segment: (typeof script.segments)[number] }[] }[] = [];
  script.segments.forEach((segment, index) => {
    const last = paragraphs[paragraphs.length - 1];
    if (last && last.key === segment.paragraph) last.items.push({ index, segment });
    else paragraphs.push({ key: segment.paragraph, items: [{ index, segment }] });
  });
  const jump = (start: number | null) => {
    if (script.timed && start !== null) seek(start);
  };
  return (
    <div
      ref={container}
      onWheel={() => (userScrolledAt.current = Date.now())}
      onTouchMove={() => (userScrolledAt.current = Date.now())}
      className="h-full overflow-y-auto px-6 py-8 sm:px-10"
    >
      <div className="mx-auto max-w-[62ch] space-y-5 text-[17px] leading-[1.75]">
        {!script.timed && (
          <p className="rounded-lg bg-hover px-4 py-3 text-sm text-fg-2">Chương này chưa có audio hoàn chỉnh - đang hiện văn bản, chưa đọc theo được.</p>
        )}
        {paragraphs.map((paragraph) => {
          const first = paragraph.items[0];
          if (first.segment.kind === "heading") {
            return (
              <h2
                key={paragraph.key}
                data-index={first.index}
                onClick={() => jump(first.segment.start)}
                className={cn("pb-2 text-2xl font-bold leading-snug tracking-tight", first.index === active && "text-accent-text")}
              >
                {first.segment.text}
              </h2>
            );
          }
          return (
            <p key={paragraph.key}>
              {paragraph.items.map(({ index, segment }) => (
                <span key={segment.id}>
                  {segment.speaker && (segment.kind === "dialogue" || segment.kind === "thought") && (
                    <span className="mr-1.5 inline-block -translate-y-px rounded bg-accent-soft px-1.5 text-[11px] font-semibold uppercase tracking-wide text-accent-text">
                      {segment.speaker}
                    </span>
                  )}
                  <span
                    data-index={index}
                    onClick={() => jump(segment.start)}
                    className={cn(
                      "rounded-[4px] transition-colors duration-300",
                      script.timed && "cursor-pointer hover:bg-hover",
                      segment.kind === "thought" && "italic",
                      index === active && "bg-accent-soft",
                      active >= 0 && index < active && "text-fg-2",
                    )}
                  >
                    {segment.text}
                  </span>{" "}
                </span>
              ))}
            </p>
          );
        })}
      </div>
    </div>
  );
}

function ChapterPanel() {
  const { track, queue, jumpTo, playing } = usePlayer();
  const container = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    container.current?.querySelector<HTMLElement>("[data-current=true]")?.scrollIntoView({ block: "center" });
  }, []);
  return (
    <div ref={container} className="h-full overflow-y-auto px-3 py-4 sm:px-6">
      {queue.map((chapter) => {
        const current = chapter.id === track?.chapterId;
        return (
          <button
            key={chapter.id}
            type="button"
            data-current={current}
            disabled={!chapter.available}
            onClick={() => jumpTo(chapter.id)}
            className={cn(
              "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left disabled:opacity-45",
              current ? "bg-accent-soft" : "hover:bg-hover",
            )}
          >
            <span className="grid w-7 shrink-0 place-items-center">
              {current && playing ? <Vu className="h-3 text-accent" /> : <span className="tabular text-xs text-fg-3">{chapter.index}</span>}
            </span>
            <span className="min-w-0 flex-1">
              <span className={cn("block truncate text-sm font-medium", current && "text-accent-text")}>{chapter.title}</span>
              {chapter.subtitle && <span className="block truncate text-xs text-fg-2">{chapter.subtitle}</span>}
            </span>
            <span className="tabular shrink-0 text-xs text-fg-3">{chapter.available ? formatLength(chapter.duration) : "chưa có"}</span>
          </button>
        );
      })}
    </div>
  );
}

function BookmarkRow({ bookId, mark, title }: { bookId: string; mark: Bookmark; title: string }) {
  const { jumpTo } = usePlayer();
  const mutations = useListenMutations(bookId);
  const [editing, setEditing] = useState(false);
  const [note, setNote] = useState(mark.note);
  return (
    <div className="group rounded-lg px-3 py-2.5 hover:bg-hover">
      <div className="flex items-center gap-2">
        <button type="button" onClick={() => jumpTo(mark.chapterId, mark.seconds)} className="min-w-0 flex-1 text-left">
          <span className="block truncate text-sm font-medium">{title}</span>
          <span className="tabular block text-xs text-fg-2">
            {formatClock(mark.seconds)} · {formatRelative(mark.at)}
          </span>
        </button>
        <IconButton label="Sửa ghi chú" icon={Pencil} size="sm" onClick={() => setEditing((value) => !value)} />
        <IconButton label="Xoá dấu trang" icon={Trash2} size="sm" onClick={() => mutations.deleteBookmark.mutate(mark.id)} />
      </div>
      {editing ? (
        <form
          className="mt-2 flex gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            mutations.updateBookmark.mutate({ id: mark.id, note });
            setEditing(false);
          }}
        >
          <input
            autoFocus
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Ghi chú cho dấu trang này"
            className="h-8 flex-1 rounded-md border border-line bg-bg px-2 text-sm outline-none focus:border-accent"
          />
          <button type="submit" className="rounded-md bg-accent px-3 text-sm font-medium text-accent-ink">
            Lưu
          </button>
        </form>
      ) : mark.note ? (
        <p className="mt-1 text-sm text-fg-2">{mark.note}</p>
      ) : null}
    </div>
  );
}

function BookmarkPanel() {
  const { track, queue } = usePlayer();
  const { data: book } = useListenBook(track?.bookId);
  const marks = [...(book?.state.bookmarks ?? [])].sort((a, b) => b.at - a.at);
  const titleOf = (chapterId: number) => queue.find((chapter) => chapter.id === chapterId)?.fullTitle ?? "";
  if (!track || !marks.length) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-8 text-center">
        <BookmarkIcon className="size-8 text-fg-3" />
        <p className="mt-3 font-medium">Chưa có dấu trang</p>
        <p className="mt-1 text-sm text-fg-2">Bấm biểu tượng dấu trang khi nghe tới đoạn muốn quay lại.</p>
      </div>
    );
  }
  return (
    <div className="h-full overflow-y-auto px-3 py-4 sm:px-6">
      {marks.map((mark) => (
        <BookmarkRow key={mark.id} bookId={track.bookId} mark={mark} title={titleOf(mark.chapterId)} />
      ))}
    </div>
  );
}

type Panel = "text" | "chapters" | "bookmarks";
const PANELS: { value: Panel; label: string; icon: typeof Text }[] = [
  { value: "text", label: "Đọc theo", icon: Text },
  { value: "chapters", label: "Chương", icon: ListOrdered },
  { value: "bookmarks", label: "Dấu trang", icon: BookmarkIcon },
];

// ---- Màn hình đang nghe ------------------------------------------------------------------------------------

export function NowPlaying({ mobile = false }: { mobile?: boolean }) {
  const { track, expanded, setExpanded, sleep } = usePlayer();
  const [panel, setPanel] = useState<Panel>("text");
  const [showPanel, setShowPanel] = useState(!mobile);
  useEffect(() => {
    if (!expanded) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setExpanded(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded, setExpanded]);

  const panelTabs = (
    <div role="tablist" aria-label="Bảng" className="flex gap-1">
      {PANELS.map((item) => (
        <button
          key={item.value}
          type="button"
          role="tab"
          aria-selected={panel === item.value && showPanel}
          onClick={() => {
            if (mobile && panel === item.value && showPanel) setShowPanel(false);
            else {
              setPanel(item.value);
              setShowPanel(true);
            }
          }}
          className={cn(
            "inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-sm font-medium transition-colors",
            panel === item.value && showPanel ? "bg-hover text-fg" : "text-fg-2 hover:text-fg",
          )}
        >
          <item.icon className="size-4" />
          {item.label}
        </button>
      ))}
    </div>
  );

  const panelBody = panel === "text" ? <ReadAlong /> : panel === "chapters" ? <ChapterPanel /> : <BookmarkPanel />;

  return (
    <AnimatePresence>
      {expanded && track && (
        <motion.section
          key="now-playing"
          initial={{ opacity: 0, y: 28 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 28 }}
          transition={{ duration: 0.22, ease: [0.2, 0.8, 0.2, 1] }}
          className={cn("absolute inset-0 z-30 flex bg-bg", mobile && "flex-col")}
          aria-label="Đang nghe"
        >
          <aside className={cn("flex shrink-0 flex-col bg-panel", mobile ? "min-h-0 flex-1 px-6 pb-6 pt-3" : "w-[400px] border-r border-line px-8 pb-8 pt-5")}>
            <div className="flex items-center justify-between">
              <IconButton label="Thu nhỏ (Esc)" icon={ChevronDown} onClick={() => setExpanded(false)} />
              <span className="text-xs font-medium uppercase tracking-wider text-fg-3">Đang nghe</span>
              <span className="size-9" />
            </div>
            {mobile && showPanel ? (
              <div className="-mx-6 mt-2 min-h-0 flex-1 border-y border-line">{panelBody}</div>
            ) : (
              <div className="mt-4 flex min-h-0 flex-1 flex-col items-center justify-center">
                <BookCover title={track.bookTitle} size="xl" className="w-full max-w-[300px]" />
              </div>
            )}
            <div className="mt-5 w-full text-center">
              <h2 className="truncate text-lg font-semibold">{track.chapterTitle}</h2>
              <p className="mt-0.5 truncate text-sm text-fg-2">{track.bookTitle}</p>
            </div>
            <div className="mt-5 w-full">
              <SeekBar large />
            </div>
            <div className="mt-3 flex justify-center">
              <Transport large />
            </div>
            <div className="mt-4 flex items-center justify-center gap-1">
              <SpeedMenu />
              <SleepMenu />
              <BookmarkButton />
              <VolumeControl />
            </div>
            {sleep.kind === "chapter" && <p className="mt-2 text-center text-xs text-fg-3">Sẽ dừng khi hết chương này.</p>}
            {mobile && <div className="mt-4 flex justify-center">{panelTabs}</div>}
          </aside>
          {!mobile && (
            <div className="flex min-w-0 flex-1 flex-col">
              <div className="flex h-14 shrink-0 items-center border-b border-line px-6">{panelTabs}</div>
              <div className="min-h-0 flex-1">{panelBody}</div>
            </div>
          )}
        </motion.section>
      )}
    </AnimatePresence>
  );
}
