import * as Popover from "@radix-ui/react-popover";
import * as Slider from "@radix-ui/react-slider";
import { useQueries, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownToLine,
  Bookmark as BookmarkIcon,
  BookmarkPlus,
  Check,
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
  Undo2,
  Volume1,
  Volume2,
  VolumeX,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from "react";
import { toast } from "sonner";
import { BookCover } from "@/shared/BookCover";
import { cn } from "@/shared/cn";
import { formatClock, formatLength, formatPercent, formatWhen, spokenClock } from "@/shared/format";
import { IconButton, Tooltip, Vu } from "@/shared/ui";
import { useClock, useClockReader, useDuration, usePlaybackSecond } from "./clock";
import type { Bookmark, ListenChapter, Script } from "./model";
import { EDIT_BOOKMARK_EVENT, SKIP_SECONDS, SPEEDS, useNowPlaying, usePlayer } from "./player";
import { SLEEP_CHOICES, sleepLabel, sleepLeftMs, sleepSpoken } from "./sleep";
import { useListenBook, useListenMutations, useScript, useSource } from "./source";

export function speedLabel(rate: number): string {
  return `${rate.toLocaleString("vi-VN", { maximumFractionDigits: 2 })}×`;
}

/** Nút điều khiển không giữ focus sau cú bấm chuột: Space sau đó vẫn là phát/tạm dừng, không lặp lại nút vừa bấm. */
const keepFocus = { onMouseDown: (event: { preventDefault: () => void }) => event.preventDefault() };

function useTicker(active: boolean, every = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    setNow(Date.now());
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), every);
    return () => window.clearInterval(timer);
  }, [active, every]);
  return now;
}

/** Câu đang đọc ở giây `seconds` (tìm nhị phân trên mốc bắt đầu). */
export function sentenceIndexAt(starts: number[], seconds: number): number {
  let low = 0;
  let high = starts.length - 1;
  let found = -1;
  while (low <= high) {
    const middle = (low + high) >> 1;
    if (starts[middle] <= seconds + 0.05) {
      found = middle;
      low = middle + 1;
    } else {
      high = middle - 1;
    }
  }
  return found;
}

export function sentenceAt(script: Script | undefined, seconds: number): string | null {
  if (!script?.timed) return null;
  const starts = script.segments.map((segment) => segment.start ?? 0);
  const index = sentenceIndexAt(starts, seconds);
  return index >= 0 ? script.segments[index].text : null;
}

// ---- Thanh tua -------------------------------------------------------------------------------------------

function SeekBar({ large = false }: { large?: boolean }) {
  const { seek, skip, track } = usePlayer();
  const second = usePlaybackSecond();
  const duration = useDuration();
  const [dragging, setDragging] = useState<number | null>(null);
  const pointer = useRef(false);
  useEffect(() => setDragging(null), [track?.chapterId, track?.bookId]);
  const shown = dragging ?? second;
  const max = duration > 0 ? duration : 1;
  const onKeyDown = (event: ReactKeyboardEvent) => {
    // Bàn phím trên thanh tua đi theo đúng bước của trình phát (15 giây), không qua trạng thái "đang kéo".
    const steps: Record<string, () => void> = {
      ArrowLeft: () => skip(-SKIP_SECONDS),
      ArrowDown: () => skip(-SKIP_SECONDS),
      ArrowRight: () => skip(SKIP_SECONDS),
      ArrowUp: () => skip(SKIP_SECONDS),
      PageDown: () => skip(-60),
      PageUp: () => skip(60),
      Home: () => seek(0),
      End: () => seek(Math.max(0, duration - 2)),
    };
    const action = steps[event.key];
    if (!action) return;
    event.preventDefault();
    event.stopPropagation();
    action();
  };
  return (
    <div className={cn("w-full", large ? "space-y-1.5" : "flex items-center gap-3")}>
      {!large && <span className="tabular w-12 shrink-0 text-right text-xs text-fg-2">{formatClock(shown)}</span>}
      <Slider.Root
        className={cn("group relative flex touch-none select-none items-center", large ? "h-5 w-full" : "h-4 flex-1")}
        min={0}
        max={max}
        step={1}
        value={[Math.min(shown, max)]}
        onPointerDown={() => (pointer.current = true)}
        onValueChange={([value]) => {
          if (pointer.current) setDragging(value);
        }}
        onValueCommit={([value]) => {
          pointer.current = false;
          seek(value);
          window.setTimeout(() => setDragging(null), 0);
        }}
        onKeyDown={onKeyDown}
        disabled={!duration}
      >
        <Slider.Track className={cn("relative grow overflow-hidden rounded-full bg-line-strong", large ? "h-1.5" : "h-1")}>
          <Slider.Range className="absolute h-full rounded-full bg-fg group-hover:bg-accent" />
        </Slider.Track>
        <Slider.Thumb
          aria-label="Vị trí trong chương"
          aria-valuetext={`${spokenClock(shown)} trên ${spokenClock(duration)}`}
          className={cn(
            "block rounded-full bg-fg shadow transition-opacity focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
            large ? "size-4 opacity-100" : "size-3 opacity-0 group-hover:opacity-100 focus-visible:opacity-100",
          )}
        />
      </Slider.Root>
      {large ? (
        <div className="tabular flex justify-between text-xs text-fg-2">
          <span>{formatClock(shown)}</span>
          <span>-{formatClock(Math.max(0, duration - shown))}</span>
        </div>
      ) : (
        <span className="tabular w-12 shrink-0 text-xs text-fg-2">-{formatClock(Math.max(0, duration - shown))}</span>
      )}
    </div>
  );
}

// ---- Nút điều khiển ------------------------------------------------------------------------------------

function skipIcon(Base: typeof RotateCcw) {
  return function SkipGlyph({ className }: { className?: string; strokeWidth?: number }) {
    return (
      <span className={cn("relative inline-grid place-items-center", className)}>
        <Base className="size-full" strokeWidth={1.75} />
        <span className="tabular absolute inset-0 grid place-items-center pt-[1px] text-[0.42em] font-bold leading-none">
          {SKIP_SECONDS}
        </span>
      </span>
    );
  };
}
const Back15 = skipIcon(RotateCcw);
const Forward15 = skipIcon(RotateCw);

function Transport({ large = false }: { large?: boolean }) {
  const { playing, buffering, toggle, skip, next, previous, queue, track } = usePlayer();
  const hasNext = useMemo(() => {
    const index = queue.findIndex((chapter) => chapter.id === track?.chapterId);
    return queue.slice(index + 1).some((chapter) => chapter.available);
  }, [queue, track?.chapterId]);
  const size = large ? "lg" : "sm";
  return (
    <div className={cn("flex items-center", large ? "gap-4 sm:gap-6" : "gap-1")}>
      <IconButton label="Chương trước (Shift+←)" icon={SkipBack} size={size} onClick={previous} {...keepFocus} />
      <IconButton label={`Lùi ${SKIP_SECONDS} giây (←)`} icon={Back15} size={size} onClick={() => skip(-SKIP_SECONDS)} {...keepFocus} />
      <button
        type="button"
        onClick={toggle}
        {...keepFocus}
        aria-label={playing ? "Tạm dừng" : "Phát"}
        aria-keyshortcuts="Space"
        data-player-toggle
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
      <IconButton label={`Tới ${SKIP_SECONDS} giây (→)`} icon={Forward15} size={size} onClick={() => skip(SKIP_SECONDS)} {...keepFocus} />
      <IconButton label="Chương sau (Shift+→)" icon={SkipForward} size={size} onClick={next} disabled={!hasNext} {...keepFocus} />
    </div>
  );
}

function MenuShell({
  trigger,
  label,
  children,
  active,
  width = "w-56",
}: {
  trigger: ReactNode;
  label: string;
  children: ReactNode;
  active?: boolean;
  width?: string;
}) {
  return (
    <Popover.Root>
      <Tooltip label={label}>
        <Popover.Trigger asChild>
          <button
            type="button"
            aria-label={label}
            {...keepFocus}
            className={cn(
              "tabular inline-flex h-9 min-w-9 shrink-0 items-center justify-center gap-1 whitespace-nowrap rounded-lg px-2 text-[13px] font-semibold transition-colors hover:bg-hover",
              active ? "text-accent-text" : "text-fg-2",
            )}
          >
            {trigger}
          </button>
        </Popover.Trigger>
      </Tooltip>
      <Popover.Portal>
        <Popover.Content sideOffset={8} collisionPadding={12} className={cn("z-50 rounded-xl border border-line bg-panel p-1.5 shadow-float", width)}>
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
      <div className="px-2 pb-1 pt-1 text-xs font-medium text-fg-2">Tốc độ đọc · nhớ riêng cho cuốn này</div>
      <div className="grid grid-cols-3 gap-1 p-1">
        {SPEEDS.map((speed) => (
          <Popover.Close asChild key={speed}>
            <button
              type="button"
              onClick={() => setRate(speed)}
              aria-pressed={speed === rate}
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
      <p className="px-2 pb-1 pt-1.5 text-xs text-fg-2">
        Phím <kbd className="font-semibold">[</kbd> và <kbd className="font-semibold">]</kbd> để giảm, tăng.
      </p>
    </MenuShell>
  );
}

export function SleepMenu() {
  const { sleep, setSleep, extendSleep, options, sleepStoppedAt, lastSleepMinutes, track } = usePlayer();
  const counting = sleep.kind === "minutes" && sleep.since !== null;
  const now = useTicker(counting);
  const active = sleep.kind !== "off";
  const recentlyStopped = !active && sleepStoppedAt !== null && now - sleepStoppedAt < 30 * 60_000;
  const left = sleepLeftMs(sleep, now);
  return (
    <MenuShell
      label={active ? sleepSpoken(sleep, now) : "Hẹn giờ tắt"}
      active={active}
      width="w-64"
      trigger={
        <>
          <Moon className="size-4" />
          {active && <span className="tabular">{sleepLabel(sleep, now)}</span>}
        </>
      }
    >
      {active ? (
        <div className="px-2 pb-2 pt-1.5">
          <div className="text-xs font-medium text-fg-2">{sleep.kind === "chapter" ? "Dừng khi" : "Tắt sau"}</div>
          <div className="tabular mt-0.5 text-2xl font-semibold tracking-tight">
            {sleep.kind === "chapter" ? "hết chương này" : sleepLabel(sleep, now)}
          </div>
          {sleep.kind === "minutes" && sleep.since === null && left !== null && (
            <div className="mt-0.5 text-xs text-fg-2">Đang tạm dừng - đồng hồ cũng dừng.</div>
          )}
          <div className="mt-3 flex gap-1.5">
            <Popover.Close asChild>
              <button
                type="button"
                onClick={() => extendSleep()}
                className="h-9 flex-1 rounded-lg bg-accent-soft text-sm font-semibold text-accent-text hover:brightness-95"
              >
                +{options.extendMinutes} phút
              </button>
            </Popover.Close>
            <Popover.Close asChild>
              <button type="button" onClick={() => setSleep({ kind: "off" })} className="h-9 flex-1 rounded-lg text-sm font-medium text-danger hover:bg-hover">
                Tắt hẹn giờ
              </button>
            </Popover.Close>
          </div>
        </div>
      ) : recentlyStopped ? (
        <div className="px-2 pb-2 pt-1.5">
          <div className="text-sm">
            Hẹn giờ đã tắt tiếng lúc{" "}
            <span className="tabular font-semibold">{new Date(sleepStoppedAt!).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}</span>.
          </div>
          <Popover.Close asChild>
            <button
              type="button"
              onClick={() => setSleep({ kind: "minutes", minutes: lastSleepMinutes })}
              className="mt-2 h-9 w-full rounded-lg bg-accent-soft text-sm font-semibold text-accent-text"
            >
              Bật lại {lastSleepMinutes} phút
            </button>
          </Popover.Close>
        </div>
      ) : null}
      <div className="px-2 pb-1 pt-1 text-xs font-medium text-fg-2">{active ? "Đặt lại" : "Dừng phát sau"}</div>
      <div className="grid grid-cols-4 gap-1 p-1">
        {SLEEP_CHOICES.map((minutes) => (
          <Popover.Close asChild key={minutes}>
            <button
              type="button"
              disabled={!track}
              onClick={() => setSleep({ kind: "minutes", minutes })}
              className="tabular h-9 rounded-lg text-sm hover:bg-hover disabled:opacity-40"
            >
              {minutes}′
            </button>
          </Popover.Close>
        ))}
      </div>
      <Popover.Close asChild>
        <button
          type="button"
          disabled={!track}
          onClick={() => setSleep({ kind: "chapter" })}
          className="flex h-9 w-full items-center rounded-lg px-2 text-sm hover:bg-hover disabled:opacity-40"
        >
          Hết chương này
        </button>
      </Popover.Close>
      <p className="px-2 pb-1 pt-2 text-xs leading-snug text-fg-2">
        Tiếng nhỏ dần {options.fadeSeconds} giây trước khi dừng. Lúc đó chạm phím hoặc chuột để nghe thêm {options.extendMinutes} phút.
        Sáng hôm sau, thẻ “Tối qua” giúp tìm lại đoạn bạn còn nhớ.
      </p>
    </MenuShell>
  );
}

function VolumeControl() {
  const { volume, setVolume } = usePlayer();
  const Icon = volume === 0 ? VolumeX : volume < 0.5 ? Volume1 : Volume2;
  const remembered = useRef(volume || 0.9);
  return (
    <div className="flex items-center gap-1">
      <IconButton
        label={volume === 0 ? "Bật tiếng (M)" : "Tắt tiếng (M)"}
        icon={Icon}
        size="sm"
        {...keepFocus}
        onClick={() => {
          if (volume === 0) setVolume(remembered.current);
          else {
            remembered.current = volume;
            setVolume(0);
          }
        }}
      />
      <Slider.Root
        className="group relative hidden h-4 w-20 touch-none select-none items-center xl:flex"
        min={0}
        max={1}
        step={0.05}
        value={[volume]}
        onValueChange={([value]) => setVolume(value)}
        onKeyDown={(event) => event.stopPropagation()}
      >
        <Slider.Track className="relative h-1 grow overflow-hidden rounded-full bg-line-strong">
          <Slider.Range className="absolute h-full rounded-full bg-fg-2 group-hover:bg-accent" />
        </Slider.Track>
        <Slider.Thumb
          aria-label="Âm lượng"
          aria-valuetext={`Âm lượng ${Math.round(volume * 100)}%`}
          className="block size-3 rounded-full bg-fg opacity-0 shadow group-hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-2 focus-visible:outline-accent"
        />
      </Slider.Root>
    </div>
  );
}

/** Thêm dấu trang kèm thông báo có "Ghi chú" và "Hoàn tác". Dấu trùng chỗ (±5 giây) không tạo thêm. */
export function useAddBookmark() {
  const { addBookmark, track } = usePlayer();
  const { setExpanded } = useNowPlaying();
  const source = useSource();
  const client = useQueryClient();
  const readClock = useClockReader();
  return useCallback(async () => {
    if (!track) return;
    const at = readClock().time;
    const mark = await addBookmark().catch(() => null);
    if (!mark) {
      toast.error("Chưa thêm được dấu trang");
      return;
    }
    if (mark.existing) {
      toast("Đã có dấu trang ở chỗ này", { id: "bookmark", description: formatClock(mark.seconds) });
      return;
    }
    toast.success("Đã thêm dấu trang", {
      id: "bookmark",
      description: `${track.chapterTitle} · ${formatClock(at)}`,
      action: {
        label: "Ghi chú",
        onClick: () => {
          setExpanded(true);
          window.setTimeout(() => window.dispatchEvent(new CustomEvent(EDIT_BOOKMARK_EVENT, { detail: mark.id })), 50);
        },
      },
      cancel: {
        label: "Hoàn tác",
        onClick: () => {
          void source.deleteBookmark(track.bookId, mark.id).then(() => {
            void client.invalidateQueries({ queryKey: ["listen", "book", track.bookId] });
          });
        },
      },
    });
  }, [addBookmark, client, readClock, setExpanded, source, track]);
}

function BookmarkButton() {
  const add = useAddBookmark();
  return <IconButton label="Thêm dấu trang (B)" icon={BookmarkPlus} size="sm" {...keepFocus} onClick={() => void add()} />;
}

/** Phím B: một chỗ lắng nghe duy nhất (thanh phát luôn có mặt khi đang nghe). */
function BookmarkShortcut() {
  const add = useAddBookmark();
  useEffect(() => {
    const onShortcut = () => void add();
    window.addEventListener("ebook-reader:bookmark", onShortcut);
    return () => window.removeEventListener("ebook-reader:bookmark", onShortcut);
  }, [add]);
  return null;
}

/** Đang nhỏ dần trước khi tắt: nói rõ và cho nghe thêm bằng một chạm. */
function FadingNotice({ className }: { className?: string }) {
  const { fading, extendSleep, options } = usePlayer();
  if (!fading) return null;
  return (
    <div className={cn("flex items-center gap-3 rounded-xl bg-accent-soft px-3 py-2 text-sm text-accent-text", className)} role="status">
      <Moon className="size-4 shrink-0" />
      <span className="min-w-0 flex-1">Sắp tắt · chạm phím hoặc chuột để nghe thêm {options.extendMinutes} phút</span>
      <button type="button" onClick={() => extendSleep()} className="shrink-0 rounded-lg bg-accent px-2.5 py-1 text-xs font-semibold text-accent-ink">
        +{options.extendMinutes} phút
      </button>
    </div>
  );
}

function TrackSubtitle() {
  const { track, error, purpose, atEnd } = usePlayer();
  if (!track) return null;
  if (error) return <span className="text-danger">{error}</span>;
  return (
    <>
      {purpose === "review" && (
        <span className="mr-1.5 inline-block rounded bg-info-soft px-1.5 text-[11px] font-semibold uppercase tracking-wide text-info">Nghe kiểm</span>
      )}
      {atEnd === "caughtUp" ? "Đã nghe hết phần đã có" : track.bookTitle}
    </>
  );
}

function CompactProgress() {
  const fraction = useClock((time, duration) => (duration > 0 ? Math.round((time / duration) * 400) / 400 : 0));
  return (
    <div className="absolute inset-x-0 top-0 h-[2px] bg-line">
      <div className="h-full bg-accent" style={{ width: `${fraction * 100}%` }} />
    </div>
  );
}

/** Thiết bị khác (điện thoại) đã nghe xa hơn chỗ đang nạp ở đây: hỏi, đừng lặng lẽ nhảy - và đừng để lần lưu kế tiếp
 *  của máy này ghi đè vị trí mới hơn ấy (Audible hỏi "tới vị trí xa nhất?"; Audiobookshelf bị chê vì không hỏi). */
function FurtherElsewhere() {
  const { track, playing, queue, positionStamp, jumpTo, purpose } = usePlayer();
  const { data: book } = useListenBook(track?.bookId);
  const readClock = useClockReader();
  const asked = useRef("");
  const last = book?.state.last;
  useEffect(() => {
    if (!track || !last || playing || purpose !== "listen") return;
    const key = `${track.bookId}:${last.at}`;
    if (asked.current === key || last.at * 1000 <= positionStamp() + 1000) return;
    const here = readClock().time;
    if (last.chapterId === track.chapterId && Math.abs(last.seconds - here) < 30) return;
    asked.current = key;
    const chapter = queue.find((item) => item.id === last.chapterId);
    if (!chapter?.available) return;
    toast("Thiết bị khác đã nghe tới chỗ khác", {
      id: "further-elsewhere",
      duration: 20_000,
      description: `${chapter.title} · ${formatClock(last.seconds)} (${formatWhen(last.at)})`,
      action: { label: "Nghe tiếp từ đó", onClick: () => jumpTo(last.chapterId, last.seconds) },
      cancel: { label: "Ở lại đây", onClick: () => undefined },
    });
  }, [jumpTo, last, playing, positionStamp, purpose, queue, readClock, track]);
  return null;
}

// ---- Thanh phát nhỏ ------------------------------------------------------------------------------------

export function PlayerBar({ compact = false }: { compact?: boolean }) {
  const { track, close, playing, toggle } = usePlayer();
  const { setExpanded } = useNowPlaying();
  if (!track) return null;
  if (compact) {
    return (
      <section aria-label="Trình phát" className="relative z-20 shrink-0 border-t border-line bg-panel">
        <CompactProgress />
        <FadingNotice className="mx-3 mt-2" />
        <div className="flex h-16 items-center gap-3 px-3">
          <button type="button" onClick={() => setExpanded(true)} className="flex min-w-0 flex-1 items-center gap-3 text-left" aria-label="Mở màn hình đang nghe">
            <BookCover title={track.bookTitle} size="sm" className="size-11" />
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold">{track.chapterTitle}</div>
              <div className="truncate text-xs text-fg-2">
                <TrackSubtitle />
              </div>
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
      </section>
    );
  }
  return (
    <section aria-label="Trình phát" className="relative z-20 shrink-0 border-t border-line bg-panel">
      <BookmarkShortcut />
      <FurtherElsewhere />
      <FadingNotice className="mx-4 mt-2" />
      <div className="grid h-[76px] grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-4 px-4">
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="flex min-w-0 items-center gap-3 rounded-lg p-1 text-left hover:bg-hover"
          aria-label="Mở màn hình đang nghe"
        >
          <BookCover title={track.bookTitle} size="sm" className="size-12" />
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">{track.chapterTitle}</div>
            <div className="truncate text-xs text-fg-2">
              <TrackSubtitle />
            </div>
          </div>
        </button>
        <div className="flex w-[min(40vw,560px)] flex-col items-center gap-0.5">
          <Transport />
          <SeekBar />
        </div>
        <div className="flex min-w-0 items-center justify-end gap-0.5">
          <SpeedMenu />
          <SleepMenu />
          <BookmarkButton />
          <VolumeControl />
          <IconButton label="Mở màn hình đang nghe" icon={Maximize2} size="sm" onClick={() => setExpanded(true)} {...keepFocus} />
          <IconButton label="Đóng trình phát" icon={X} size="sm" onClick={close} {...keepFocus} />
        </div>
      </div>
    </section>
  );
}

// ---- Bảng bên của màn hình đang nghe ---------------------------------------------------------------------

function ReadAlong() {
  const { track, seek, playing, queue } = usePlayer();
  const source = useSource();
  const client = useQueryClient();
  const { data: script, isLoading } = useScript(track?.bookId, track?.chapterId);
  const container = useRef<HTMLDivElement | null>(null);
  const autoScrolling = useRef(0);
  const [following, setFollowing] = useState(true);
  const starts = useMemo(() => (script?.timed ? script.segments.map((segment) => segment.start ?? 0) : []), [script]);
  const active = useClock((time) => (starts.length ? sentenceIndexAt(starts, time) : -1));
  const nearEnd = useClock((time, duration) => duration > 0 && duration - time < 30);

  useEffect(() => setFollowing(true), [track?.chapterId]);

  // Sắp hết chương: nạp sẵn văn bản chương kế để sang chương không bị chớp "đang mở".
  useEffect(() => {
    if (!nearEnd || !track) return;
    const index = queue.findIndex((chapter) => chapter.id === track.chapterId);
    const upcoming = queue.slice(index + 1).find((chapter) => chapter.available);
    if (upcoming) {
      void client.prefetchQuery({
        queryKey: ["listen", "script", track.bookId, upcoming.id],
        queryFn: () => source.script(track.bookId, upcoming.id),
        staleTime: Infinity,
      });
    }
  }, [client, nearEnd, queue, source, track]);

  const scrollToActive = useCallback((smooth: boolean) => {
    const element = container.current?.querySelector<HTMLElement>(`[data-index="${active}"]`);
    if (!element) return;
    autoScrolling.current = Date.now();
    element.scrollIntoView({ block: "center", behavior: smooth ? "smooth" : "auto" });
  }, [active]);

  useEffect(() => {
    if (active < 0 || !following) return;
    scrollToActive(playing);
  }, [active, following, playing, scrollToActive]);

  if (isLoading) return <div className="animate-[fade-in_0.2s_0.3s_both] p-10 text-fg-2">Đang mở văn bản chương…</div>;
  if (!script) return null;
  const paragraphs: { key: number; items: { index: number; segment: (typeof script.segments)[number] }[] }[] = [];
  script.segments.forEach((segment, index) => {
    const last = paragraphs[paragraphs.length - 1];
    if (last && last.key === segment.paragraph) last.items.push({ index, segment });
    else paragraphs.push({ key: segment.paragraph, items: [{ index, segment }] });
  });
  const jump = (start: number | null) => {
    if (script.timed && start !== null) {
      seek(start);
      setFollowing(true);
    }
  };
  const onKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement;
    const index = Number(target.dataset.index);
    if (!Number.isFinite(index)) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      event.stopPropagation();
      jump(script.segments[index].start);
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      event.stopPropagation();
      const next = container.current?.querySelector<HTMLElement>(`[data-index="${index + (event.key === "ArrowDown" ? 1 : -1)}"]`);
      next?.focus();
    }
  };
  return (
    <div className="relative h-full">
      <div
        ref={container}
        onScroll={() => {
          if (Date.now() - autoScrolling.current > 900) setFollowing(false);
        }}
        onKeyDown={onKeyDown}
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
                  tabIndex={first.index === Math.max(0, active) ? 0 : -1}
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
                      role={script.timed ? "button" : undefined}
                      tabIndex={script.timed ? (index === Math.max(0, active) ? 0 : -1) : undefined}
                      aria-current={index === active ? "true" : undefined}
                      onClick={() => jump(segment.start)}
                      className={cn(
                        "rounded-[4px] [box-decoration-break:clone] transition-colors duration-300",
                        script.timed && "cursor-pointer hover:bg-hover",
                        segment.kind === "thought" && "italic",
                        index === active && "read-along-active",
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
      {!following && active >= 0 && (
        <button
          type="button"
          onClick={() => {
            setFollowing(true);
            scrollToActive(true);
          }}
          className="absolute bottom-5 left-1/2 inline-flex -translate-x-1/2 items-center gap-1.5 rounded-full bg-fg px-4 py-2 text-sm font-semibold text-bg shadow-float"
        >
          <ArrowDownToLine className="size-4" /> Về câu đang đọc
        </button>
      )}
    </div>
  );
}

export function chapterStatusLabel(producing: boolean): string {
  return producing ? "Đang thu âm…" : "Chưa có audio";
}

function ChapterPanel() {
  const { track, queue, jumpTo, playing } = usePlayer();
  const { data: book } = useListenBook(track?.bookId);
  const container = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    container.current?.querySelector<HTMLElement>("[data-current=true]")?.scrollIntoView({ block: "center" });
  }, []);
  return (
    <div ref={container} className="h-full overflow-y-auto px-3 py-4 sm:px-6">
      {queue.map((chapter) => {
        const current = chapter.id === track?.chapterId;
        const done = book?.state.chapters[String(chapter.id)]?.done;
        return (
          <button
            key={chapter.id}
            type="button"
            data-current={current}
            disabled={!chapter.available}
            aria-current={current ? "true" : undefined}
            onClick={() => jumpTo(chapter.id)}
            className={cn(
              "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left",
              current ? "bg-accent-soft" : chapter.available && "hover:bg-hover",
            )}
          >
            <span className="grid w-5 shrink-0 place-items-center">
              {current && playing ? (
                <Vu className="h-3 text-accent" />
              ) : done ? (
                <Check className="size-4 text-success" aria-label="Đã nghe" />
              ) : null}
            </span>
            <span className="min-w-0 flex-1">
              <span className={cn("block truncate text-sm font-medium", current && "text-accent-text", !chapter.available && "text-fg-2")}>
                {chapter.subtitle || chapter.title}
              </span>
              <span className="tabular block truncate text-xs text-fg-2">
                {chapter.subtitle ? `${chapter.title} · ` : ""}
                {chapter.available ? formatLength(chapter.duration) : chapterStatusLabel(Boolean(book?.producing))}
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

// ---- Dấu trang (dùng chung cho màn Đang nghe và trang sách) ------------------------------------------------

function BookmarkRow({
  bookId,
  mark,
  chapter,
  quote,
  editing,
  onEdit,
  onJump,
}: {
  bookId: string;
  mark: Bookmark;
  chapter: ListenChapter | undefined;
  quote: string | null;
  editing: boolean;
  onEdit: (editing: boolean) => void;
  onJump: (mark: Bookmark) => void;
}) {
  const mutations = useListenMutations(bookId);
  const [note, setNote] = useState(mark.note);
  useEffect(() => setNote(mark.note), [mark.note]);
  const remove = () => {
    mutations.deleteBookmark.mutate(mark.id, {
      onSuccess: () =>
        toast("Đã xoá dấu trang", {
          id: `bookmark-${mark.id}`,
          action: { label: "Hoàn tác", onClick: () => mutations.restoreBookmark.mutate(mark) },
        }),
    });
  };
  return (
    <li className="group rounded-lg px-3 py-2.5 hover:bg-hover">
      <div className="flex items-start gap-2">
        <button type="button" onClick={() => onJump(mark)} className="min-w-0 flex-1 text-left">
          <span className="block truncate text-sm font-medium">{chapter ? chapter.subtitle || chapter.title : "Chương đã bị gỡ"}</span>
          <span className="tabular block text-xs text-fg-2">
            {chapter?.subtitle ? `${chapter.title} · ` : ""}
            {formatClock(mark.seconds)} · {formatWhen(mark.at)}
          </span>
          {quote && <span className="mt-1 line-clamp-2 block text-sm italic leading-snug text-fg">“{quote}”</span>}
        </button>
        <IconButton label="Sửa ghi chú" icon={Pencil} size="sm" onClick={() => onEdit(!editing)} />
        <IconButton label="Xoá dấu trang" icon={Trash2} size="sm" onClick={remove} />
      </div>
      {editing ? (
        <form
          className="mt-2 space-y-1"
          onSubmit={(event) => {
            event.preventDefault();
            mutations.updateBookmark.mutate({ id: mark.id, note });
            onEdit(false);
          }}
        >
          <div className="flex gap-2">
            <input
              autoFocus
              value={note}
              maxLength={500}
              onChange={(event) => setNote(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  event.preventDefault();
                  event.stopPropagation();
                  setNote(mark.note);
                  onEdit(false);
                }
              }}
              placeholder="Ghi chú cho dấu trang này"
              aria-label="Ghi chú"
              className="h-9 min-w-0 flex-1 rounded-md border border-line bg-bg px-2 text-sm outline-none focus:border-accent"
            />
            <button type="submit" className="rounded-md bg-accent px-3 text-sm font-medium text-accent-ink">
              Lưu
            </button>
          </div>
          <div className="tabular text-right text-[11px] text-fg-2">{note.length}/500</div>
        </form>
      ) : mark.note ? (
        <p className="mt-1.5 whitespace-pre-wrap rounded-md bg-sunken px-2.5 py-1.5 text-sm text-fg-2">{mark.note}</p>
      ) : null}
    </li>
  );
}

/** Danh sách dấu trang - mới nhất lên đầu, mỗi dấu kèm câu văn ở chỗ đó để nhận ra mà không cần nhớ giây. */
export function BookmarkList({
  bookId,
  chapters,
  marks,
  onJump,
  editingId,
  setEditingId,
}: {
  bookId: string;
  chapters: ListenChapter[];
  marks: Bookmark[];
  onJump: (mark: Bookmark) => void;
  editingId?: string | null;
  setEditingId?: (id: string | null) => void;
}) {
  const source = useSource();
  const [localEditing, setLocalEditing] = useState<string | null>(null);
  const editing = editingId !== undefined ? editingId : localEditing;
  const setEditing = setEditingId ?? setLocalEditing;
  const sorted = useMemo(() => [...marks].sort((a, b) => b.at - a.at), [marks]);
  const chapterIds = useMemo(() => [...new Set(sorted.map((mark) => mark.chapterId))], [sorted]);
  const scripts = useQueries({
    queries: chapterIds.map((chapterId) => ({
      queryKey: ["listen", "script", bookId, chapterId],
      queryFn: () => source.script(bookId, chapterId),
      staleTime: Infinity,
      enabled: chapters.some((chapter) => chapter.id === chapterId && chapter.available),
    })),
  });
  const scriptOf = (chapterId: number) => scripts[chapterIds.indexOf(chapterId)]?.data as Script | undefined;
  return (
    <ul className="space-y-1">
      {sorted.map((mark) => (
        <BookmarkRow
          key={mark.id}
          bookId={bookId}
          mark={mark}
          chapter={chapters.find((chapter) => chapter.id === mark.chapterId)}
          quote={sentenceAt(scriptOf(mark.chapterId), mark.seconds)}
          editing={editing === mark.id}
          onEdit={(value) => setEditing(value ? mark.id : null)}
          onJump={onJump}
        />
      ))}
    </ul>
  );
}

function BookmarkPanel({ editingId, setEditingId }: { editingId: string | null; setEditingId: (id: string | null) => void }) {
  const { track, queue, jumpTo } = usePlayer();
  const { data: book } = useListenBook(track?.bookId);
  const marks = book?.state.bookmarks ?? [];
  if (!track || !marks.length) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-8 text-center">
        <BookmarkIcon className="size-8 text-fg-3" />
        <p className="mt-3 font-medium">Chưa có dấu trang</p>
        <p className="mt-1 text-sm text-fg-2">Bấm biểu tượng dấu trang (hoặc phím B) khi nghe tới đoạn muốn quay lại.</p>
      </div>
    );
  }
  return (
    <div className="h-full overflow-y-auto px-3 py-4 sm:px-6">
      <BookmarkList
        bookId={track.bookId}
        chapters={queue}
        marks={marks}
        onJump={(mark) => jumpTo(mark.chapterId, mark.seconds)}
        editingId={editingId}
        setEditingId={setEditingId}
      />
    </div>
  );
}

type Panel = "text" | "chapters" | "bookmarks";
const PANELS: { value: Panel; label: string; icon: typeof Text }[] = [
  { value: "text", label: "Đọc theo", icon: Text },
  { value: "chapters", label: "Chương", icon: ListOrdered },
  { value: "bookmarks", label: "Dấu trang", icon: BookmarkIcon },
];
const PANEL_KEY = "ebook-reader-now-playing-panel";

function initialPanel(): Panel {
  try {
    const stored = localStorage.getItem(PANEL_KEY);
    if (stored === "text" || stored === "chapters" || stored === "bookmarks") return stored;
  } catch {
    /* không có bộ nhớ trình duyệt */
  }
  return "text";
}

/** Tiến độ cả cuốn (phần đã có audio): "Cả cuốn 42% · còn 3 giờ 48 phút (2 giờ 32 phút ở 1,5×)". */
function BookProgressLine() {
  const { queue, track, rate } = usePlayer();
  const tens = useClock((time) => Math.floor(time / 10));
  const { before, total } = useMemo(() => {
    let heardBefore = 0;
    let sum = 0;
    let reached = false;
    for (const chapter of queue) {
      if (!chapter.available) continue;
      if (chapter.id === track?.chapterId) reached = true;
      else if (!reached) heardBefore += chapter.duration;
      sum += chapter.duration;
    }
    return { before: heardBefore, total: sum };
  }, [queue, track?.chapterId]);
  if (!track || total <= 0) return null;
  const heard = Math.min(total, before + tens * 10);
  const left = Math.max(0, total - heard);
  return (
    <p className="tabular mt-1 text-xs text-fg-2">
      Cả cuốn {formatPercent(heard / total)} · còn {formatLength(left)}
      {rate !== 1 && left > 60 ? ` (${formatLength(left / rate)} ở ${speedLabel(rate)})` : ""}
    </p>
  );
}

function CaughtUpNotice() {
  const { atEnd } = usePlayer();
  if (atEnd !== "caughtUp") return null;
  return (
    <p className="mt-3 rounded-xl bg-hover px-3 py-2 text-center text-sm text-fg-2">
      Bạn đã nghe hết phần đã có. Chương tiếp theo sẽ nghe được khi Studio làm xong.
    </p>
  );
}

// ---- Màn hình đang nghe ------------------------------------------------------------------------------------

export function NowPlaying({ mobile = false }: { mobile?: boolean }) {
  const { track, sleep, canGoBack, goBack } = usePlayer();
  const { expanded, setExpanded } = useNowPlaying();
  const [panel, setPanelState] = useState<Panel>(initialPanel);
  const [showPanel, setShowPanel] = useState(!mobile);
  const [editingId, setEditingId] = useState<string | null>(null);
  const section = useRef<HTMLElement | null>(null);
  const opener = useRef<HTMLElement | null>(null);
  const open = expanded && Boolean(track);

  const setPanel = (value: Panel) => {
    setPanelState(value);
    try {
      localStorage.setItem(PANEL_KEY, value);
    } catch {
      /* không lưu được thì thôi */
    }
  };

  // Mở: đưa focus vào nút Phát; đóng: trả focus về chỗ đã mở.
  useEffect(() => {
    if (!open) return;
    opener.current = document.activeElement as HTMLElement | null;
    const timer = window.setTimeout(() => section.current?.querySelector<HTMLElement>("[data-player-toggle]")?.focus(), 30);
    return () => {
      window.clearTimeout(timer);
      opener.current?.focus?.();
    };
  }, [open]);

  useEffect(() => {
    const onEdit = (event: Event) => {
      setPanel("bookmarks");
      setShowPanel(true);
      setEditingId(String((event as CustomEvent).detail));
    };
    window.addEventListener(EDIT_BOOKMARK_EVENT, onEdit);
    return () => window.removeEventListener(EDIT_BOOKMARK_EVENT, onEdit);
  }, []);

  const onKeyDown = (event: ReactKeyboardEvent) => {
    if (event.key !== "Escape" || event.defaultPrevented) return;
    const target = event.target as HTMLElement;
    if (["INPUT", "TEXTAREA"].includes(target.tagName)) return;
    // Một lần Esc đóng một lớp: menu hay popover đang mở thì chỉ đóng nó.
    if (document.querySelector("[data-radix-popper-content-wrapper], [role='menu']")) return;
    event.preventDefault();
    setExpanded(false);
  };

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

  const panelBody =
    panel === "text" ? <ReadAlong /> : panel === "chapters" ? <ChapterPanel /> : <BookmarkPanel editingId={editingId} setEditingId={setEditingId} />;

  if (!open || !track) return null;
  return (
    <section
      ref={section}
      onKeyDown={onKeyDown}
      className={cn("now-playing absolute inset-0 z-30 flex bg-bg", mobile && "flex-col")}
      aria-label="Đang nghe"
    >
      <aside className={cn("flex shrink-0 flex-col bg-panel", mobile ? "min-h-0 flex-1 px-6 pb-6 pt-3" : "w-[400px] border-r border-line px-8 pb-8 pt-5")}>
        <div className="flex items-center justify-between">
          <IconButton label="Thu nhỏ (Esc)" icon={ChevronDown} onClick={() => setExpanded(false)} />
          <span className="text-xs font-semibold uppercase tracking-[0.08em] text-fg-2">Đang nghe</span>
          {canGoBack ? <IconButton label="Quay lại chỗ vừa nghe" icon={Undo2} onClick={goBack} /> : <span className="size-9" />}
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
          <p className="mt-0.5 truncate text-sm text-fg-2">
            <TrackSubtitle />
          </p>
          <BookProgressLine />
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
        {sleep.kind === "chapter" && <p className="mt-2 text-center text-xs text-fg-2">Sẽ dừng khi hết chương này.</p>}
        <FadingNotice className="mt-3" />
        <CaughtUpNotice />
        {mobile && <div className="mt-4 flex justify-center">{panelTabs}</div>}
      </aside>
      {!mobile && (
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex h-14 shrink-0 items-center border-b border-line px-6">{panelTabs}</div>
          <div className="min-h-0 flex-1">{panelBody}</div>
        </div>
      )}
    </section>
  );
}
