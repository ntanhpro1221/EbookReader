import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Hand, Moon, Play, Smartphone, TimerReset, X } from "lucide-react";
import { useMemo, useState } from "react";
import { usePlayListenBook } from "@/listen/LibraryScreen";
import type { Script } from "@/listen/model";
import { useSource } from "@/listen/source";
import { cn } from "@/shared/cn";
import { formatClock } from "@/shared/format";
import { EbookPlayer, type BedtimeEvent, type BedtimeSession } from "./plugins";

// "Tối qua bạn nghe tới đâu?" - thẻ buổi sáng.
//
// Không ai biết chính xác lúc người nghe thiếp đi. Nhưng nhật ký đêm (Bedtime.kt) có những mốc chắc chắn:
// lúc hẹn giờ và lần cuối chạm/lắc máy (chắc chắn còn thức), lúc điện thoại bắt đầu nằm yên (rất có thể là
// lúc ngủ), lúc tự dừng. Thẻ đặt CÂU VĂN đang được đọc ở mỗi mốc cạnh nhau: người nghe nhận ra đoạn cuối mình
// còn nhớ nhanh hơn nhiều so với nhìn một con số giây. Muốn chính xác hơn nữa thì lướt ngược từng câu.

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

function markersOf(session: BedtimeSession): Marker[] {
  const events = session.events.filter((event) => event.position?.chapterId != null);
  const make = (event: BedtimeEvent | undefined, key: string, icon: typeof Moon, label: string, hint: string, shift = 0): Marker | null =>
    event
      ? {
          key, icon, label, hint, at: event.at,
          chapterId: event.position.chapterId!, chapterTitle: event.position.chapterTitle,
          seconds: Math.max(0, event.position.seconds - shift),
        }
      : null;
  const timer = events.find((event) => event.type === "timer");
  const touches = events.filter((event) => event.type === "touch" || event.type === "shake");
  const lastTouch = touches[touches.length - 1];
  const still = [...events].reverse().find((event) => event.type === "still");
  const stopped = [...events].reverse().find((event) => event.type === "stopped");
  const list = [
    make(timer, "timer", TimerReset, "Hẹn giờ ngủ", "chắc chắn còn thức"),
    lastTouch && lastTouch !== timer ? make(lastTouch, "touch", Hand, "Lần cuối chạm máy", "chắc chắn còn thức") : null,
    make(still, "still", Smartphone, "Máy bắt đầu nằm yên", "có lẽ bạn ngủ từ khoảng này", BEFORE_SLEEP_SECONDS),
    make(stopped, "stopped", Moon, "Tự dừng", "lúc hết giờ hẹn"),
  ].filter(Boolean) as Marker[];
  const suggested = list.find((marker) => marker.key === "still") ?? list.find((marker) => marker.key === "touch") ?? list[0];
  if (suggested) suggested.suggested = true;
  return list;
}

function sentenceAt(script: Script | undefined, seconds: number): { index: number; text: string } | null {
  if (!script?.timed) return null;
  let index = -1;
  for (let cursor = 0; cursor < script.segments.length; cursor += 1) {
    if ((script.segments[cursor].start ?? 0) <= seconds) index = cursor;
    else break;
  }
  return index >= 0 ? { index, text: script.segments[index].text } : null;
}

export function MorningRecap() {
  const source = useSource();
  const client = useQueryClient();
  const playBook = usePlayListenBook();
  const [scrubbing, setScrubbing] = useState(false);
  const { data } = useQuery({ queryKey: ["bedtime"], queryFn: () => EbookPlayer.lastNight(), staleTime: 60_000 });
  const session = data?.session ?? null;
  const fresh = Boolean(
    session && !session.dismissed && session.endedAt && Date.now() / 1000 - session.endedAt < RECENT_HOURS * 3600,
  );
  const markers = useMemo(() => (session && fresh ? markersOf(session) : []), [session, fresh]);
  const chapterIds = [...new Set(markers.map((marker) => marker.chapterId))];
  const scripts = useQuery({
    queryKey: ["bedtime-scripts", session?.bookId, chapterIds.join(",")],
    enabled: fresh && chapterIds.length > 0,
    queryFn: async () => Object.fromEntries(await Promise.all(chapterIds.map(async (id) => [id, await source.script(session!.bookId, id)] as const))),
    staleTime: Infinity,
  });
  if (!fresh || !session || !markers.length) return null;

  const dismiss = async () => {
    await EbookPlayer.dismissLastNight();
    void client.invalidateQueries({ queryKey: ["bedtime"] });
  };
  const resume = async (chapterId: number, seconds: number) => {
    const book = await source.book(session.bookId);
    await playBook(book, chapterId, seconds);
    await dismiss();
  };
  const suggested = markers.find((marker) => marker.suggested)!;
  const script = scripts.data?.[suggested.chapterId];
  const suggestedSentence = sentenceAt(script, suggested.seconds);
  const earliest = markers.find((marker) => marker.chapterId === suggested.chapterId) ?? suggested;
  const scrubFrom = sentenceAt(script, earliest.seconds)?.index ?? 0;
  const scrubTo = sentenceAt(script, markers[markers.length - 1].seconds)?.index ?? scrubFrom;

  return (
    <section className="relative overflow-hidden rounded-2xl border border-line bg-panel p-4 shadow-card">
      <button type="button" aria-label="Ẩn" onClick={() => void dismiss()} className="absolute right-2 top-2 grid size-9 place-items-center rounded-full text-fg-3">
        <X className="size-4" />
      </button>
      <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-accent-text">
        <Moon className="size-3.5" /> Tối qua · {session.bookTitle}
      </div>
      <h2 className="mt-1.5 pr-8 text-lg font-semibold leading-snug">Bạn nghe tới đâu rồi thiếp đi?</h2>

      <ol className="mt-4 space-y-3">
        {markers.map((marker) => {
          const sentence = sentenceAt(scripts.data?.[marker.chapterId], marker.seconds);
          return (
            <li key={marker.key}>
              <button
                type="button"
                onClick={() => void resume(marker.chapterId, marker.seconds)}
                className={cn(
                  "flex w-full gap-3 rounded-xl p-3 text-left",
                  marker.suggested ? "bg-accent-soft ring-1 ring-accent/40" : "bg-hover/60",
                )}
              >
                <marker.icon className={cn("mt-0.5 size-4 shrink-0", marker.suggested ? "text-accent-text" : "text-fg-3")} />
                <span className="min-w-0 flex-1">
                  <span className="flex items-baseline justify-between gap-2">
                    <span className="text-sm font-semibold">{marker.label}</span>
                    <span className="tabular shrink-0 text-xs text-fg-2">{timeOf(marker.at)}</span>
                  </span>
                  <span className="block text-xs text-fg-2">
                    {marker.hint} · {marker.chapterTitle} {formatClock(marker.seconds)}
                  </span>
                  {sentence && <span className="mt-1.5 line-clamp-2 block text-sm italic leading-snug text-fg">“{sentence.text}”</span>}
                </span>
              </button>
            </li>
          );
        })}
      </ol>

      <div className="mt-4 flex gap-2">
        <button
          type="button"
          onClick={() => void resume(suggested.chapterId, suggested.seconds)}
          className="flex h-12 flex-1 items-center justify-center gap-2 rounded-xl bg-accent font-semibold text-accent-ink"
        >
          <Play className="size-4" fill="currentColor" strokeWidth={0} /> Nghe tiếp từ {suggestedSentence ? "câu này" : formatClock(suggested.seconds)}
        </button>
        {script?.timed && (
          <button type="button" onClick={() => setScrubbing((value) => !value)} className="h-12 rounded-xl bg-hover px-4 text-sm font-medium">
            {scrubbing ? "Thu gọn" : "Tìm câu"}
          </button>
        )}
      </div>

      {scrubbing && script?.timed && (
        <div className="mt-4 max-h-80 overflow-y-auto rounded-xl border border-line">
          <p className="sticky top-0 bg-panel px-3 py-2 text-xs text-fg-2">Chạm vào câu cuối cùng bạn còn nhớ:</p>
          {script.segments.slice(Math.max(0, scrubFrom - 2), scrubTo + 3).map((segment) => (
            <button
              key={segment.id}
              type="button"
              onClick={() => void resume(suggested.chapterId, segment.start ?? 0)}
              className="block w-full border-t border-line px-3 py-2.5 text-left text-[15px] leading-snug active:bg-hover"
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
