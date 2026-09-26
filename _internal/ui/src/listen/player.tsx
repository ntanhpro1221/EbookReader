import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { AudioEngine } from "./engine";
import type { Bookmark, ListenBook, ListenChapter } from "./model";
import { useSource } from "./source";

// Trình phát sách nói - chung cho máy tính và Android. Hành vi theo chuẩn Audible / Apple Books / Voice:
// nhớ vị trí và tốc độ từng cuốn, tự sang chương kế, hẹn giờ tắt có nhỏ dần, tự lùi khi nghe lại sau một lúc
// lâu, dấu trang một chạm, phím tắt và nút media.

export interface Track {
  bookId: string;
  bookTitle: string;
  narrator: string;
  chapterId: number;
  chapterTitle: string;
}

export type SleepMode = { kind: "off" } | { kind: "minutes"; endsAt: number; minutes: number } | { kind: "chapter" };

export const SPEEDS = [0.75, 0.9, 1, 1.1, 1.2, 1.3, 1.5, 1.75, 2, 2.5, 3];
export const SKIP_SECONDS = 15;
const SAVE_EVERY_MS = 10_000;
const AUTO_REWIND_AFTER_MS = 5 * 60_000;
const AUTO_REWIND_SECONDS = 5;
const FADE_SECONDS = 10;

interface PlayerState {
  track: Track | null;
  queue: ListenChapter[];
  playing: boolean;
  buffering: boolean;
  time: number;
  duration: number;
  rate: number;
  volume: number;
  sleep: SleepMode;
  expanded: boolean;
  error: string;
}

interface PlayerActions {
  play: (book: Pick<ListenBook, "id" | "title" | "narrator" | "state">, chapters: ListenChapter[], chapterId: number, at?: number) => void;
  toggle: () => void;
  seek: (seconds: number) => void;
  skip: (delta: number) => void;
  next: () => void;
  previous: () => void;
  jumpTo: (chapterId: number, at?: number) => void;
  setRate: (rate: number) => void;
  setVolume: (volume: number) => void;
  setSleep: (mode: SleepMode) => void;
  setExpanded: (expanded: boolean) => void;
  addBookmark: (note?: string) => Promise<Bookmark | null>;
  close: () => void;
}

const PlayerContext = createContext<(PlayerState & PlayerActions) | null>(null);

export function usePlayer() {
  const value = useContext(PlayerContext);
  if (!value) throw new Error("usePlayer ngoài PlayerProvider");
  return value;
}

function availableAfter(queue: ListenChapter[], chapterId: number, step: 1 | -1): ListenChapter | undefined {
  const index = queue.findIndex((chapter) => chapter.id === chapterId);
  for (let cursor = index + step; cursor >= 0 && cursor < queue.length; cursor += step) {
    if (queue[cursor].available) return queue[cursor];
  }
  return undefined;
}

export function PlayerProvider({
  engine,
  children,
  defaultRate = 1,
  defaultVolume = 0.9,
  keyboard = true,
}: {
  engine: AudioEngine;
  children: ReactNode;
  defaultRate?: number;
  defaultVolume?: number;
  keyboard?: boolean;
}) {
  const source = useSource();
  const client = useQueryClient();
  const [track, setTrack] = useState<Track | null>(null);
  const [queue, setQueue] = useState<ListenChapter[]>([]);
  const [playing, setPlaying] = useState(false);
  const [buffering, setBuffering] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [rate, setRateState] = useState(defaultRate);
  const [volume, setVolumeState] = useState(defaultVolume);
  const [sleep, setSleepState] = useState<SleepMode>({ kind: "off" });
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState("");
  const refs = useRef({ track: null as Track | null, queue: [] as ListenChapter[], sleep: { kind: "off" } as SleepMode,
    pausedAt: 0, lastSaved: 0, volume: defaultVolume });
  refs.current.track = track;
  refs.current.queue = queue;
  refs.current.sleep = sleep;
  refs.current.volume = volume;

  const refreshLists = useCallback((bookId: string) => {
    void client.invalidateQueries({ queryKey: ["listen", "library"] });
    void client.invalidateQueries({ queryKey: ["listen", "book", bookId] });
  }, [client]);

  const save = useCallback((force = false) => {
    const current = refs.current.track;
    if (!current) return;
    const now = Date.now();
    if (!force && now - refs.current.lastSaved < SAVE_EVERY_MS) return;
    refs.current.lastSaved = now;
    void source.saveProgress(current.bookId, current.chapterId, engine.time, engine.duration).catch(() => undefined);
    if (force) refreshLists(current.bookId);
  }, [engine, source, refreshLists]);

  const load = useCallback((next: Track, at: number, autoplay: boolean) => {
    save(true);
    setError("");
    setTrack(next);
    refs.current.track = next;
    setTime(at);
    setDuration(0);
    engine.load(
      { url: source.audioUrl(next.bookId, next.chapterId), title: next.chapterTitle, album: next.bookTitle, artist: next.narrator },
      at,
      autoplay,
    );
  }, [engine, source, save]);

  const play = useCallback<PlayerActions["play"]>((book, chapters, chapterId, at) => {
    const chapter = chapters.find((item) => item.id === chapterId);
    if (!chapter) return;
    setQueue(chapters);
    refs.current.queue = chapters;
    const current = refs.current.track;
    const bookRate = book.state?.rate;
    if (bookRate && bookRate !== rate) {
      setRateState(bookRate);
      engine.setRate(bookRate);
    }
    if (current && current.bookId === book.id && current.chapterId === chapterId && at === undefined) {
      engine.play();
      return;
    }
    load({ bookId: book.id, bookTitle: book.title, narrator: book.narrator, chapterId, chapterTitle: chapter.fullTitle },
      at ?? 0, true);
  }, [engine, load, rate]);

  const toggle = useCallback(() => {
    if (!refs.current.track) return;
    if (engine.paused) {
      if (refs.current.pausedAt && Date.now() - refs.current.pausedAt > AUTO_REWIND_AFTER_MS) {
        engine.seek(Math.max(0, engine.time - AUTO_REWIND_SECONDS));
      }
      engine.play();
    } else {
      engine.pause();
    }
  }, [engine]);

  const seek = useCallback((seconds: number) => {
    engine.seek(seconds);
    setTime(engine.time);
  }, [engine]);

  const skip = useCallback((delta: number) => seek(engine.time + delta), [engine, seek]);

  const jumpTo = useCallback((chapterId: number, at = 0) => {
    const current = refs.current.track;
    const chapter = refs.current.queue.find((item) => item.id === chapterId);
    if (!current || !chapter || !chapter.available) return;
    if (chapterId === current.chapterId) {
      seek(at);
      engine.play();
      return;
    }
    load({ ...current, chapterId, chapterTitle: chapter.fullTitle }, at, true);
  }, [engine, load, seek]);

  const step = useCallback((direction: 1 | -1) => {
    const current = refs.current.track;
    if (!current) return;
    if (direction === -1 && engine.time > 5) {
      seek(0);
      return;
    }
    const target = availableAfter(refs.current.queue, current.chapterId, direction);
    if (target) load({ ...current, chapterId: target.id, chapterTitle: target.fullTitle }, 0, true);
  }, [engine, load, seek]);

  const next = useCallback(() => step(1), [step]);
  const previous = useCallback(() => step(-1), [step]);

  const setRate = useCallback((value: number) => {
    setRateState(value);
    engine.setRate(value);
    const current = refs.current.track;
    if (current) void source.setRate(current.bookId, value).catch(() => undefined);
  }, [engine, source]);

  const setVolume = useCallback((value: number) => {
    const clamped = Math.max(0, Math.min(1, value));
    setVolumeState(clamped);
    engine.setVolume(clamped);
  }, [engine]);

  const setSleep = useCallback((mode: SleepMode) => {
    setSleepState(mode);
    engine.setVolume(refs.current.volume);
  }, [engine]);

  const addBookmark = useCallback(async (note = "") => {
    const current = refs.current.track;
    if (!current) return null;
    const mark = await source.addBookmark(current.bookId, current.chapterId, engine.time, note);
    refreshLists(current.bookId);
    return mark;
  }, [engine, source, refreshLists]);

  const close = useCallback(() => {
    save(true);
    engine.stop();
    setTrack(null);
    refs.current.track = null;
    setPlaying(false);
    setExpanded(false);
    setSleepState({ kind: "off" });
  }, [engine, save]);

  // Sự kiện của bộ máy phát.
  useEffect(() => {
    engine.setRate(rate);
    engine.setVolume(volume);
    const offs = [
      engine.on("time", () => {
        setTime(engine.time);
        save();
        const mode = refs.current.sleep;
        if (mode.kind === "minutes") {
          const left = (mode.endsAt - Date.now()) / 1000;
          if (left <= 0) {
            engine.pause();
            engine.setVolume(refs.current.volume);
            setSleepState({ kind: "off" });
          } else if (left < FADE_SECONDS) {
            engine.setVolume(refs.current.volume * (left / FADE_SECONDS));
          }
        }
      }),
      engine.on("duration", () => setDuration(engine.duration)),
      engine.on("play", () => {
        setPlaying(true);
        refs.current.pausedAt = 0;
      }),
      engine.on("pause", () => {
        setPlaying(false);
        refs.current.pausedAt = Date.now();
        save(true);
      }),
      engine.on("waiting", () => setBuffering(true)),
      engine.on("playing", () => setBuffering(false)),
      engine.on("ended", () => {
        save(true);
        if (refs.current.sleep.kind === "chapter") {
          setSleepState({ kind: "off" });
          return;
        }
        const current = refs.current.track;
        const target = current && availableAfter(refs.current.queue, current.chapterId, 1);
        if (current && target) load({ ...current, chapterId: target.id, chapterTitle: target.fullTitle }, 0, true);
      }),
      engine.on("error", () => {
        setError("Không phát được chương này - file có thể đã bị xoá hoặc đang được ghi lại.");
        setBuffering(false);
      }),
    ];
    return () => offs.forEach((off) => off());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [engine, load, save]);

  useEffect(() => {
    const onHide = () => save(true);
    window.addEventListener("pagehide", onHide);
    return () => window.removeEventListener("pagehide", onHide);
  }, [save]);

  // Phím tắt (máy tính): Space phát/dừng, ←/→ tua, Shift+←/→ đổi chương, B thêm dấu trang.
  useEffect(() => {
    if (!keyboard) return;
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))) return;
      if (!refs.current.track || event.ctrlKey || event.metaKey || event.altKey) return;
      if (event.code === "Space" && !(target && target.tagName === "BUTTON")) {
        event.preventDefault();
        toggle();
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        if (event.shiftKey) previous();
        else skip(-SKIP_SECONDS);
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        if (event.shiftKey) next();
        else skip(SKIP_SECONDS);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [keyboard, toggle, skip, next, previous]);

  // Nút media của hệ điều hành (bộ máy web; bộ máy native tự lo phần này).
  useEffect(() => {
    if (!("mediaSession" in navigator) || !track) return;
    const handlers: [MediaSessionAction, MediaSessionActionHandler][] = [
      ["play", () => toggle()],
      ["pause", () => toggle()],
      ["seekbackward", () => skip(-SKIP_SECONDS)],
      ["seekforward", () => skip(SKIP_SECONDS)],
      ["previoustrack", () => previous()],
      ["nexttrack", () => next()],
    ];
    for (const [action, handler] of handlers) {
      try {
        navigator.mediaSession.setActionHandler(action, handler);
      } catch {
        /* không hỗ trợ */
      }
    }
  }, [track, toggle, skip, next, previous]);

  const value = useMemo(() => ({
    track, queue, playing, buffering, time, duration, rate, volume, sleep, expanded, error,
    play, toggle, seek, skip, next, previous, jumpTo, setRate, setVolume, setSleep, setExpanded, addBookmark, close,
  }), [track, queue, playing, buffering, time, duration, rate, volume, sleep, expanded, error,
    play, toggle, seek, skip, next, previous, jumpTo, setRate, setVolume, setSleep, addBookmark, close]);

  return <PlayerContext.Provider value={value}>{children}</PlayerContext.Provider>;
}
