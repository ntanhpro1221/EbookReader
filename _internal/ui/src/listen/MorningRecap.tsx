import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Hand, Moon, Play, Smartphone, TimerReset, X } from "lucide-react";
import { useMemo, useState } from "react";
import { cn } from "@/shared/cn";
import { formatClock } from "@/shared/format";
import { usePlayListenBook } from "./LibraryScreen";
import type { NightEvent, NightSession, Script } from "./model";
import { sentenceAt } from "./PlayerViews";
import { useSource } from "./source";

// "Tối qua bạn nghe tới đâu?" - thẻ buổi sáng, chung cho máy tính và điện thoại.
//
// Không ai biết chính xác lúc người nghe thiếp đi. Nhưng nhật ký đêm có những mốc chắc chắn: lúc hẹn giờ, lần cuối
// còn chạm vào máy (chắc chắn còn thức), lúc điện thoại bắt đầu nằm yên (rất có thể là lúc ngủ - chỉ điện thoại có
// cảm biến), lúc tự dừng. Thẻ đặt CÂU VĂN đang được đọc ở mỗi mốc cạnh nhau: người nghe nhận ra đoạn cuối mình còn
// nhớ nhanh hơn nhiều so với nhìn một con số giây. Muốn chính xác hơn nữa thì lướt từng câu.

const RECENT_HOURS = 18;
const BEFORE_SLEEP_SECONDS = 120;

interface Marker {
  key: string;
  icon: typeof Moon;
  label: string;
  hint: string;
  at: number;
  chapterId: number;
  chapterTitle: string;
  seconds: number;
  suggested?: boolean;
}

function timeOf(at: number): string {
  return new Date(at * 1000).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

function markersOf(session: NightSession): Marker[] {
  const events = session.events.filter((event) => event.position?.chapterId != null);
  const make = (event: NightEvent | undefined, key: string, icon: typeof Moon, label: string, hint: string, shift = 0): Marker | null =>
    event
      ? {
          key, icon, label, hint, at: event.at,
          chapterId: event.position.chapterId!, chapterTitle: event.position.chapterTitle,
          seconds: Math.max(0, event.position.seconds - shift),
        }
      : null;
  const timer = events.find((event) => event.type === "timer");
  const touches = events.filter((event) => event.type === "touch" || event.type === "shake" || event.type === "extend");
  const lastTouch = touches[touches.length - 1];
  const still = [...events].reverse().find((event) => event.type === "still");
  const stopped = [...events].reverse().find((event) => event.type === "stopped");
  const phone = session.device !== "desktop";
  const safety = timer?.action === "safety";
  const list = [
    safety ? null : make(timer, "timer", TimerReset, "Hẹn giờ ngủ", "chắc chắn còn thức"),
    lastTouch && lastTouch !== timer
      ? make(lastTouch, "touch", Hand, phone ? "Lần cuối chạm máy" : "Lần cuối dùng máy", "chắc chắn còn thức")
      : null,
    make(still, "still", Smartphone, "Máy bắt đầu nằm yên", "có lẽ bạn ngủ từ khoảng này", BEFORE_SLEEP_SECONDS),
    make(stopped, "stopped", Moon, "Tự dừng", safety ? "không ai chạm máy suốt một lúc lâu" : "lúc hết giờ hẹn"),
  ].filter(Boolean) as Marker[];
  const suggested = list.find((marker) => marker.key === "still") ?? list.find((marker) => marker.key === "touch") ?? list[0];
  if (suggested) suggested.suggested = true;
  return list;
}

export function MorningRecap({ className }: { className?: string }) {
  const source = useSource();
  const client = useQueryClient();
  const playBook = usePlayListenBook();
  const [scrubbing, setScrubbing] = useState(false);
  const { data } = useQuery({ queryKey: ["listen", "night"], queryFn: () => source.lastNight(), staleTime: 60_000 });
  const session = data?.night ?? null;
  const bookId = data?.bookId ?? "";
  const fresh = Boolean(
    session &&
      !session.dismissed &&
      session.endedAt &&
      session.events.some((event) => event.type === "stopped") &&
      Date.now() / 1000 - session.endedAt < RECENT_HOURS * 3600,
  );
  const markers = useMemo(() => (session && fresh ? markersOf(session) : []), [session, fresh]);
  const chapterIds = [...new Set(markers.map((marker) => marker.chapterId))];
  const scripts = useQuery({
    queryKey: ["listen", "night-scripts", bookId, chapterIds.join(",")],
    enabled: fresh && chapterIds.length > 0,
    queryFn: async () => Object.fromEntries(await Promise.all(chapterIds.map(async (id) => [id, await source.script(bookId, id)] as const))) as Record<number, Script>,
    staleTime: Infinity,
  });
  if (!fresh || !session || !markers.length) return null;

  const dismiss = async () => {
    await source.dismissNight(bookId, session.id);
    void client.invalidateQueries({ queryKey: ["listen", "night"] });
  };
  const resume = async (chapterId: number, seconds: number) => {
    const book = await source.book(bookId);
    await playBook(book, chapterId, seconds);
    await dismiss();
  };
  const suggested = markers.find((marker) => marker.suggested)!;
  const script = scripts.data?.[suggested.chapterId];
  const starts = script?.timed ? script.segments.map((segment) => segment.start ?? 0) : [];
  const indexAt = (seconds: number) => {
    let found = 0;
    starts.forEach((start, index) => {
      if (start <= seconds) found = index;
    });
    return found;
  };
  const earliest = markers.find((marker) => marker.chapterId === suggested.chapterId) ?? suggested;
  const scrubFrom = indexAt(earliest.seconds);
  const scrubTo = Math.max(scrubFrom, indexAt(markers[markers.length - 1].seconds));

  return (
    <section className={cn("relative overflow-hidden rounded-2xl border border-line bg-panel p-4 shadow-card sm:p-5", className)} aria-label="Tối qua">
      <button type="button" aria-label="Ẩn thẻ này" onClick={() => void dismiss()} className="absolute right-2 top-2 grid size-9 place-items-center rounded-full text-fg-2 hover:bg-hover">
        <X className="size-4" />
      </button>
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.08em] text-accent-text">
        <Moon className="size-3.5" /> Tối qua · {session.bookTitle}
      </div>
      <h2 className="mt-1.5 pr-8 text-lg font-semibold leading-snug">Bạn nghe tới đâu rồi thiếp đi?</h2>

      <ol className="mt-4 grid gap-3 lg:grid-cols-2">
        {markers.map((marker) => {
          const sentence = sentenceAt(scripts.data?.[marker.chapterId], marker.seconds);
          return (
            <li key={marker.key}>
              <button
                type="button"
                onClick={() => void resume(marker.chapterId, marker.seconds)}
                className={cn(
                  "flex h-full w-full gap-3 rounded-xl p-3 text-left",
                  marker.suggested ? "bg-accent-soft ring-1 ring-accent/40" : "bg-hover/60 hover:bg-hover",
                )}
              >
                <marker.icon className={cn("mt-0.5 size-4 shrink-0", marker.suggested ? "text-accent-text" : "text-fg-2")} />
                <span className="min-w-0 flex-1">
                  <span className="flex items-baseline justify-between gap-2">
                    <span className="text-sm font-semibold">{marker.label}</span>
                    <span className="tabular shrink-0 text-xs text-fg-2">{timeOf(marker.at)}</span>
                  </span>
                  <span className="tabular block text-xs text-fg-2">
                    {marker.hint} · {marker.chapterTitle} {formatClock(marker.seconds)}
                  </span>
                  {sentence && <span className="mt-1.5 line-clamp-2 block text-sm italic leading-snug text-fg">“{sentence}”</span>}
                </span>
              </button>
            </li>
          );
        })}
      </ol>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void resume(suggested.chapterId, suggested.seconds)}
          className="flex h-11 flex-1 items-center justify-center gap-2 rounded-xl bg-accent px-4 font-semibold text-accent-ink sm:flex-none"
        >
          <Play className="size-4" fill="currentColor" strokeWidth={0} /> Nghe tiếp từ {sentenceAt(script, suggested.seconds) ? "câu này" : formatClock(suggested.seconds)}
        </button>
        {script?.timed && (
          <button type="button" onClick={() => setScrubbing((value) => !value)} className="h-11 rounded-xl bg-hover px-4 text-sm font-medium">
            {scrubbing ? "Thu gọn" : "Tìm đúng câu"}
          </button>
        )}
      </div>

      {scrubbing && script?.timed && (
        <div className="mt-4 max-h-80 overflow-y-auto rounded-xl border border-line">
          <p className="sticky top-0 bg-panel px-3 py-2 text-xs text-fg-2">Chọn câu cuối cùng bạn còn nhớ:</p>
          {script.segments.slice(Math.max(0, scrubFrom - 2), scrubTo + 3).map((segment) => (
            <button
              key={segment.id}
              type="button"
              onClick={() => void resume(suggested.chapterId, segment.start ?? 0)}
              className="block w-full border-t border-line px-3 py-2.5 text-left text-[15px] leading-snug hover:bg-hover active:bg-hover"
            >
              {segment.speaker && <span className="mr-1.5 text-[11px] font-semibold uppercase text-accent-text">{segment.speaker}</span>}
              {segment.text}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
