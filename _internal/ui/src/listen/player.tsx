import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { coverArtwork } from "@/shared/cover";
import { formatClock } from "@/shared/format";
import { Clock, ClockContext } from "./clock";
import { isNative, type AudioEngine } from "./engine";
import type { Bookmark, ListenBook, ListenChapter, NightPosition } from "./model";
import { NightRecorder } from "./night";
import {
  DEFAULT_EXTEND_MINUTES,
  DEFAULT_FADE_SECONDS,
  fadeGain,
  rewindAfter,
  sleepExtended,
  sleepFrom,
  sleepLeftMs,
  sleepPaused,
  sleepResumed,
  type SleepMode,
  type SleepRequest,
} from "./sleep";
import { useSource } from "./source";

export type { SleepMode, SleepRequest } from "./sleep";

// Trình phát sách nói - chung cho máy tính và Android. Hành vi theo chuẩn Audible / Apple Books / Smart AudioBook
// Player: nhớ vị trí và tốc độ từng cuốn, tự sang chương kế, hẹn giờ ngủ nhỏ dần và gia hạn được, tự lùi khi nghe
// lại theo độ dài lần dừng, "quay lại chỗ vừa nghe" sau mỗi cú nhảy xa, dấu trang một chạm, phím tắt, nút media.
//
// Bộ máy web (máy tính): trình phát tự lo hàng đợi, hẹn giờ, nhật ký đêm, lưu vị trí.
// Bộ máy native (Android): lõi Media3 lo hết những việc đó - trình phát chỉ chuyển lệnh và phản chiếu trạng thái.
//
// Thời gian phát KHÔNG nằm trong context này mà ở Clock (clock.ts): nó đổi nhiều lần mỗi giây.

export interface Track {
  bookId: string;
  bookTitle: string;
  narrator: string;
  chapterId: number;
  chapterTitle: string;
}

/** "review": nghe kiểm trong Studio - không ghi đè chỗ đang nghe dở của người nghe. */
export type Purpose = "listen" | "review";

/** Lịch đêm: bấm nghe trong khung giờ này thì tự hẹn giờ ngủ (giờ dạng "22:00", khung có thể qua nửa đêm). */
export interface SleepSchedule {
  from: string;
  to: string;
  minutes: number;
}

export interface PlayerOptions {
  fadeSeconds: number;
  extendMinutes: number;
  /** Phát liên tục chừng này giờ mà không ai chạm máy thì tự nhỏ dần rồi dừng (0 = tắt) - lưới cho người ngủ quên. */
  safetyStopHours: number;
  schedule: SleepSchedule | null;
}

function minutesOf(clock: string): number {
  const [hours, minutes] = clock.split(":").map(Number);
  return (hours || 0) * 60 + (minutes || 0);
}

/** Đang trong khung giờ của lịch? Trả về khoá của đêm ấy (ngày bắt đầu khung) để biết người dùng đã tắt nó chưa. */
export function scheduleWindow(schedule: SleepSchedule | null, now = new Date()): string | null {
  if (!schedule) return null;
  const from = minutesOf(schedule.from);
  const to = minutesOf(schedule.to);
  const current = now.getHours() * 60 + now.getMinutes();
  const overnight = from > to;
  const inside = overnight ? current >= from || current < to : current >= from && current < to;
  if (!inside) return null;
  const start = new Date(now);
  if (overnight && current < to) start.setDate(start.getDate() - 1);
  return start.toDateString();
}

type BookRef = Pick<ListenBook, "id" | "title" | "narrator" | "state"> & { complete?: boolean };

interface PlayerState {
  track: Track | null;
  queue: ListenChapter[];
  playing: boolean;
  buffering: boolean;
  rate: number;
  volume: number;
  sleep: SleepMode;
  /** Đang nhỏ dần trước khi tự tắt. */
  fading: boolean;
  /** Lúc hẹn giờ vừa dừng phát (ms) - để nói "Đã tắt lúc 23:42" và mời bật lại. */
  sleepStoppedAt: number | null;
  lastSleepMinutes: number;
  purpose: Purpose;
  /** Phát hết chương cuối đã có: "finished" nếu cuốn đã đủ, "caughtUp" nếu cuốn còn đang làm. */
  atEnd: "none" | "caughtUp" | "finished";
  canGoBack: boolean;
  error: string;
  options: PlayerOptions;
}

interface PlayerActions {
  play: (book: BookRef, chapters: ListenChapter[], chapterId: number, at?: number, extra?: { purpose?: Purpose }) => void;
  /** Nạp sẵn ở trạng thái dừng (mở lại app: thanh phát có ngay cuốn đang nghe dở, bấm Space là nghe tiếp). */
  prepare: (book: BookRef, chapters: ListenChapter[], chapterId: number, at: number) => void;
  toggle: () => void;
  resume: () => void;
  pause: () => void;
  seek: (seconds: number) => void;
  skip: (delta: number) => void;
  next: () => void;
  previous: () => void;
  jumpTo: (chapterId: number, at?: number) => void;
  goBack: () => void;
  setRate: (rate: number) => void;
  setVolume: (volume: number) => void;
  setSleep: (request: SleepRequest) => void;
  extendSleep: (minutes?: number) => void;
  addBookmark: (note?: string) => Promise<Bookmark | null>;
  close: () => void;
  /** Lần cuối vị trí trên máy này được nạp hoặc lưu (ms) - vị trí trên máy chủ mới hơn mốc này là từ thiết bị khác. */
  positionStamp: () => number;
}

export type PlayerValue = PlayerState & PlayerActions;

const PlayerContext = createContext<PlayerValue | null>(null);
const NowPlayingContext = createContext<{ expanded: boolean; setExpanded: (expanded: boolean) => void } | null>(null);

export function usePlayer(): PlayerValue {
  const value = useContext(PlayerContext);
  if (!value) throw new Error("usePlayer ngoài PlayerProvider");
  return value;
}

/** Màn hình "Đang nghe" mở hay đóng - tách khỏi trình phát để mở/đóng không render lại cả cây. */
export function useNowPlaying() {
  const value = useContext(NowPlayingContext);
  if (!value) throw new Error("useNowPlaying ngoài PlayerProvider");
  return value;
}

export const SPEEDS = [0.75, 0.9, 1, 1.1, 1.2, 1.3, 1.5, 1.75, 2, 2.5, 3];
export const SKIP_SECONDS = 15;
const SAVE_EVERY_MS = 10_000;
/** Nhảy xa hơn chừng này (tua, chương, dấu trang) thì mời "quay lại chỗ vừa nghe". */
const JUMP_SECONDS = 30;
const HISTORY = 5;
/** Sự kiện mở ô ghi chú cho một dấu trang (từ toast "Thêm dấu trang"). */
export const EDIT_BOOKMARK_EVENT = "ebook-reader:edit-bookmark";

function availableAfter(queue: ListenChapter[], chapterId: number, step: 1 | -1): ListenChapter | undefined {
  const index = queue.findIndex((chapter) => chapter.id === chapterId);
  for (let cursor = index + step; cursor >= 0 && cursor < queue.length; cursor += step) {
    if (queue[cursor].available) return queue[cursor];
  }
  return undefined;
}

function nearestSpeed(rate: number, step: 1 | -1): number {
  if (step === 1) return SPEEDS.find((speed) => speed > rate + 1e-6) ?? SPEEDS[SPEEDS.length - 1];
  return [...SPEEDS].reverse().find((speed) => speed < rate - 1e-6) ?? SPEEDS[0];
}

export function PlayerProvider({
  engine,
  children,
  defaultRate = 1,
  defaultVolume = 0.9,
  keyboard = true,
  fadeSeconds = DEFAULT_FADE_SECONDS,
  extendMinutes = DEFAULT_EXTEND_MINUTES,
  safetyStopHours = 2,
  sleepSchedule = null,
}: {
  engine: AudioEngine;
  children: ReactNode;
  defaultRate?: number;
  defaultVolume?: number;
  keyboard?: boolean;
  fadeSeconds?: number;
  extendMinutes?: number;
  safetyStopHours?: number;
  sleepSchedule?: SleepSchedule | null;
}) {
  const source = useSource();
  const client = useQueryClient();
  const native = isNative(engine) ? engine : null;
  const clock = useMemo(() => new Clock(), []);
  const night = useMemo(
    () => new NightRecorder(source.saveNight ? (bookId, session) => source.saveNight!(bookId, session) : undefined),
    [source],
  );
  const scheduleKey = sleepSchedule ? `${sleepSchedule.from}-${sleepSchedule.to}-${sleepSchedule.minutes}` : "";
  const options = useMemo<PlayerOptions>(
    () => ({ fadeSeconds, extendMinutes, safetyStopHours, schedule: sleepSchedule }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [fadeSeconds, extendMinutes, safetyStopHours, scheduleKey],
  );

  const [track, setTrack] = useState<Track | null>(null);
  const [queue, setQueue] = useState<ListenChapter[]>([]);
  const [playing, setPlaying] = useState(false);
  const [buffering, setBuffering] = useState(false);
  const [rate, setRateState] = useState(defaultRate);
  const [volume, setVolumeState] = useState(defaultVolume);
  const [sleep, setSleepState] = useState<SleepMode>({ kind: "off" });
  const [fading, setFading] = useState(false);
  const [sleepStoppedAt, setSleepStoppedAt] = useState<number | null>(null);
  const [lastSleepMinutes, setLastSleepMinutes] = useState(30);
  const [purpose, setPurpose] = useState<Purpose>("listen");
  const [atEnd, setAtEnd] = useState<PlayerState["atEnd"]>("none");
  const [canGoBack, setCanGoBack] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState("");

  const refs = useRef({
    track: null as Track | null,
    queue: [] as ListenChapter[],
    book: null as { id: string; title: string; complete: boolean } | null,
    sleep: { kind: "off" } as SleepMode,
    purpose: "listen" as Purpose,
    fading: false,
    pausedAt: 0,
    lastSaved: 0,
    volume: defaultVolume,
    rate: defaultRate,
    defaultRate,
    history: [] as { chapterId: number; seconds: number }[],
    bookmarking: false,
    muted: 0,
    stamp: 0,
    session: null as { id: string; startedAt: number; from: { chapterId: number; seconds: number }; bookId: string; listened: number; mark: number } | null,
    lastActivity: Date.now(),
    lastActivityPosition: null as NightPosition | null,
    scheduleOffFor: "",
  });
  refs.current.track = track;
  refs.current.queue = queue;
  refs.current.volume = volume;
  refs.current.rate = rate;
  refs.current.defaultRate = defaultRate;

  const position = useCallback(
    (): NightPosition => ({
      chapterId: refs.current.track?.chapterId ?? null,
      chapterTitle: refs.current.track?.chapterTitle ?? "",
      seconds: engine.time,
    }),
    [engine],
  );

  const applySleep = useCallback((mode: SleepMode) => {
    refs.current.sleep = mode;
    setSleepState(mode);
  }, []);

  const refreshLists = useCallback((bookId: string) => {
    void client.invalidateQueries({ queryKey: ["listen", "library"] });
    void client.invalidateQueries({ queryKey: ["listen", "book", bookId] });
  }, [client]);

  const save = useCallback((force = false) => {
    const current = refs.current.track;
    if (!current || native || refs.current.purpose === "review") return;
    const now = Date.now();
    if (!force && now - refs.current.lastSaved < SAVE_EVERY_MS) return;
    refs.current.lastSaved = now;
    refs.current.stamp = now;
    void source.saveProgress(current.bookId, current.chapterId, engine.time, engine.duration).catch(() => undefined);
    if (force) refreshLists(current.bookId);
  }, [engine, native, source, refreshLists]);

  const load = useCallback((next: Track, at: number, autoplay: boolean) => {
    save(true);
    setError("");
    setAtEnd("none");
    setTrack(next);
    refs.current.track = next;
    clock.set(at, 0);
    refs.current.stamp = Date.now();
    engine.load(
      {
        url: source.audioUrl(next.bookId, next.chapterId),
        title: next.chapterTitle,
        album: next.bookTitle,
        artist: next.narrator,
        artwork: coverArtwork(next.bookTitle),
      },
      at,
      autoplay,
    );
  }, [clock, engine, source, save]);

  const remember = useCallback((from: { chapterId: number; seconds: number }, to: { chapterId: number; seconds: number }) => {
    // Nhảy xa là một đoạn nghe khác: phiên cũ kết thúc ở chỗ trước khi nhảy.
    splitSessionRef.current(from);
    const history = refs.current.history;
    history.push(from);
    if (history.length > HISTORY) history.shift();
    setCanGoBack(true);
    const sameChapter = from.chapterId === to.chapterId;
    const title = refs.current.queue.find((chapter) => chapter.id === from.chapterId)?.title ?? "";
    toast(`Đã tới ${sameChapter ? formatClock(to.seconds) : refs.current.queue.find((c) => c.id === to.chapterId)?.title ?? ""}`, {
      id: "jump",
      duration: 8000,
      action: {
        label: `Quay lại ${sameChapter ? formatClock(from.seconds) : `${title} ${formatClock(from.seconds)}`}`,
        onClick: () => goBackRef.current(),
      },
    });
  }, []);

  const applyRate = useCallback((value: number) => {
    refs.current.rate = value;
    setRateState(value);
    engine.setRate(value);
  }, [engine]);

  const adoptBook = useCallback((book: BookRef, chapters: ListenChapter[], purposeValue: Purpose) => {
    setQueue(chapters);
    refs.current.queue = chapters;
    refs.current.book = { id: book.id, title: book.title, complete: book.complete ?? true };
    refs.current.purpose = purposeValue;
    setPurpose(purposeValue);
    const bookRate = book.state?.rate ?? refs.current.defaultRate;
    if (bookRate !== refs.current.rate) applyRate(bookRate);
    return bookRate;
  }, [applyRate]);

  const play = useCallback<PlayerActions["play"]>((book, chapters, chapterId, at, extra) => {
    const chapter = chapters.find((item) => item.id === chapterId);
    if (!chapter) return;
    const current = refs.current.track;
    const sameSpot = current && current.bookId === book.id && current.chapterId === chapterId && at === undefined;
    const bookRate = adoptBook(book, chapters, extra?.purpose ?? "listen");
    const next: Track = { bookId: book.id, bookTitle: book.title, narrator: book.narrator, chapterId, chapterTitle: chapter.fullTitle };
    if (native) {
      setTrack(next);
      refs.current.track = next;
      if (sameSpot) native.play();
      else native.loadQueue({ bookId: book.id, bookTitle: book.title, narrator: book.narrator, chapters, chapterId, at: at ?? 0, rate: bookRate, autoplay: true });
      return;
    }
    if (sameSpot) {
      resumeRef.current();
      return;
    }
    // Nghe tiếp đúng chỗ đã lưu: lùi theo độ dài lần dừng (mở lại app sáng hôm sau thì lùi hẳn 30 giây).
    let start = at ?? 0;
    const last = book.state?.last;
    if (at !== undefined && last && last.chapterId === chapterId && Math.abs(last.seconds - at) < 1) {
      start = Math.max(0, at - rewindAfter(Date.now() - last.at * 1000));
    }
    load(next, start, true);
  }, [adoptBook, load, native]);

  const prepare = useCallback<PlayerActions["prepare"]>((book, chapters, chapterId, at) => {
    if (refs.current.track) return;
    const chapter = chapters.find((item) => item.id === chapterId && item.available);
    if (!chapter) return;
    const bookRate = adoptBook(book, chapters, "listen");
    const next: Track = { bookId: book.id, bookTitle: book.title, narrator: book.narrator, chapterId, chapterTitle: chapter.fullTitle };
    setTrack(next);
    refs.current.track = next;
    if (native) {
      if (!native.bookId) {
        native.loadQueue({ bookId: book.id, bookTitle: book.title, narrator: book.narrator, chapters, chapterId, at, rate: bookRate, autoplay: false });
      }
      return;
    }
    const last = book.state?.last;
    const back = last ? rewindAfter(Date.now() - last.at * 1000) : 0;
    refs.current.pausedAt = 0;
    load(next, Math.max(0, at - back), false);
  }, [adoptBook, load, native]);

  const resume = useCallback(() => {
    const current = refs.current.track;
    if (!current) return;
    night.touch("play", position(), true);
    if (native) {
      native.play();
      return;
    }
    if (engine.ended) {
      const target = availableAfter(refs.current.queue, current.chapterId, 1);
      if (target) load({ ...current, chapterId: target.id, chapterTitle: target.fullTitle }, 0, true);
      else toast("Đã nghe hết phần đã có của cuốn này");
      return;
    }
    const back = refs.current.pausedAt ? rewindAfter(Date.now() - refs.current.pausedAt) : 0;
    if (back) engine.seek(Math.max(0, engine.time - back));
    engine.play();
  }, [engine, load, native, night, position]);
  const resumeRef = useRef(resume);
  resumeRef.current = resume;

  const pause = useCallback(() => {
    night.touch("pause", position(), true);
    engine.pause();
  }, [engine, night, position]);

  const toggle = useCallback(() => {
    if (!refs.current.track) return;
    if (engine.paused) resume();
    else pause();
  }, [engine, pause, resume]);

  const seek = useCallback((seconds: number) => {
    const current = refs.current.track;
    if (!current) return;
    const from = engine.time;
    engine.seek(seconds);
    clock.set(Math.max(0, seconds), engine.duration);
    night.touch("seek", position());
    if (Math.abs(seconds - from) > JUMP_SECONDS) remember({ chapterId: current.chapterId, seconds: from }, { chapterId: current.chapterId, seconds });
  }, [clock, engine, night, position, remember]);

  const skip = useCallback((delta: number) => {
    if (!refs.current.track) return;
    night.touch("skip", position());
    if (native) {
      native.skipBy(delta);
      return;
    }
    const target = Math.max(0, engine.time + delta);
    engine.seek(target);
    clock.set(target, engine.duration);
  }, [clock, engine, native, night, position]);

  const jumpTo = useCallback((chapterId: number, at = 0) => {
    const current = refs.current.track;
    const chapter = refs.current.queue.find((item) => item.id === chapterId);
    if (!current || !chapter || !chapter.available) return;
    night.touch("chapter", position(), true);
    const from = { chapterId: current.chapterId, seconds: engine.time };
    if (chapterId !== current.chapterId || Math.abs(at - from.seconds) > JUMP_SECONDS) remember(from, { chapterId, seconds: at });
    if (native) {
      native.jumpTo(chapterId, at);
      return;
    }
    if (chapterId === current.chapterId) {
      engine.seek(at);
      clock.set(at, engine.duration);
      engine.play();
      return;
    }
    load({ ...current, chapterId, chapterTitle: chapter.fullTitle }, at, true);
  }, [clock, engine, load, native, night, position, remember]);

  const goBack = useCallback(() => {
    const target = refs.current.history.pop();
    setCanGoBack(refs.current.history.length > 0);
    toast.dismiss("jump");
    const current = refs.current.track;
    if (!target || !current) return;
    if (native) {
      native.jumpTo(target.chapterId, target.seconds);
      return;
    }
    if (target.chapterId === current.chapterId) {
      engine.seek(target.seconds);
      clock.set(target.seconds, engine.duration);
      return;
    }
    const chapter = refs.current.queue.find((item) => item.id === target.chapterId);
    if (chapter) load({ ...current, chapterId: chapter.id, chapterTitle: chapter.fullTitle }, target.seconds, !engine.paused);
  }, [clock, engine, load, native]);
  const goBackRef = useRef(goBack);
  goBackRef.current = goBack;

  const step = useCallback((direction: 1 | -1) => {
    const current = refs.current.track;
    if (!current) return;
    night.touch(direction === 1 ? "next" : "previous", position(), true);
    if (native) {
      if (direction === 1) native.next();
      else native.previous();
      return;
    }
    if (direction === -1 && engine.time > 5) {
      engine.seek(0);
      clock.set(0, engine.duration);
      return;
    }
    const target = availableAfter(refs.current.queue, current.chapterId, direction);
    if (!target) return;
    remember({ chapterId: current.chapterId, seconds: engine.time }, { chapterId: target.id, seconds: 0 });
    load({ ...current, chapterId: target.id, chapterTitle: target.fullTitle }, 0, !engine.paused || engine.ended);
  }, [clock, engine, load, native, night, position, remember]);

  const next = useCallback(() => step(1), [step]);
  const previous = useCallback(() => step(-1), [step]);

  const setRate = useCallback((value: number) => {
    applyRate(value);
    night.touch("rate", position());
    const current = refs.current.track;
    if (current && !native && refs.current.purpose !== "review") void source.setRate(current.bookId, value).catch(() => undefined);
  }, [applyRate, native, night, position, source]);

  const setVolume = useCallback((value: number) => {
    const clamped = Math.max(0, Math.min(1, value));
    refs.current.volume = clamped;
    setVolumeState(clamped);
    if (!refs.current.fading) engine.setVolume(clamped);
    night.touch("volume", position());
  }, [engine, night, position]);

  const endFade = useCallback(() => {
    if (refs.current.fading) {
      refs.current.fading = false;
      setFading(false);
    }
    engine.setVolume(refs.current.volume);
  }, [engine]);

  const setSleep = useCallback((request: SleepRequest) => {
    if (native) {
      native.setSleep(request);
      return;
    }
    endFade();
    applySleep(sleepFrom(request, !engine.paused, Date.now()));
    const book = refs.current.book;
    if (request.kind === "off") {
      night.cancel(position());
      // Tự tắt hẹn giờ trong khung lịch đêm: đêm ấy không tự bật lại nữa.
      refs.current.scheduleOffFor = scheduleWindow(options.schedule) ?? "";
      return;
    }
    if (request.kind === "minutes") setLastSleepMinutes(request.minutes);
    setSleepStoppedAt(null);
    if (book && refs.current.purpose === "listen") night.start(book, request.kind === "minutes" ? request.minutes : null, position());
  }, [applySleep, endFade, engine, native, night, options.schedule, position]);

  const setSleepRef = useRef(setSleep);
  setSleepRef.current = setSleep;

  const extendSleep = useCallback((minutes = options.extendMinutes) => {
    if (native) {
      native.extendSleep(minutes);
      return;
    }
    if (refs.current.sleep.kind === "off") return;
    endFade();
    applySleep(sleepExtended(refs.current.sleep, minutes, !engine.paused, Date.now()));
    night.extend(minutes, position());
    toast.success(`Nghe thêm ${minutes} phút`, { id: "sleep-extend", duration: 2500 });
  }, [applySleep, endFade, engine, native, night, options.extendMinutes, position]);

  const addBookmark = useCallback(async (note = "") => {
    const current = refs.current.track;
    if (!current || refs.current.bookmarking) return null;
    refs.current.bookmarking = true;
    try {
      const mark = native
        ? await native.addBookmark(note)
        : await source.addBookmark(current.bookId, current.chapterId, engine.time, note);
      night.touch("bookmark", position(), true);
      refreshLists(current.bookId);
      return mark;
    } finally {
      refs.current.bookmarking = false;
    }
  }, [engine, native, night, position, refreshLists, source]);

  const close = useCallback(() => {
    save(true);
    night.cancel(position());
    engine.stop();
    setTrack(null);
    refs.current.track = null;
    setPlaying(false);
    setExpanded(false);
    endFade();
    applySleep({ kind: "off" });
    setPurpose("listen");
    refs.current.purpose = "listen";
    refs.current.history = [];
    setCanGoBack(false);
  }, [applySleep, endFade, engine, night, position, save]);

  const positionStamp = useCallback(() => refs.current.stamp, []);

  const splitSessionRef = useRef<(at: { chapterId: number; seconds: number }) => void>(() => undefined);

  // Phiên nghe (bộ máy web; lõi native chưa ghi): mở lúc bắt đầu phát, đóng lúc dừng. Phiên dưới 20 giây nghe
  // thật thì bỏ - bấm phát rồi dừng ngay không phải là "đã nghe".
  const openSession = useCallback(() => {
    const current = refs.current.track;
    if (native || !current || refs.current.purpose !== "listen" || !source.addSession) return;
    if (refs.current.session && refs.current.session.bookId === current.bookId) {
      refs.current.session.mark = Date.now();
      return;
    }
    refs.current.session = {
      id: Math.random().toString(16).slice(2, 14),
      startedAt: Date.now() / 1000,
      from: { chapterId: current.chapterId, seconds: engine.time },
      bookId: current.bookId,
      listened: 0,
      mark: Date.now(),
    };
  }, [engine, native, source]);

  const closeSession = useCallback((leaving = false) => {
    const session = refs.current.session;
    const current = refs.current.track;
    if (!session || !current || !source.addSession) return;
    session.listened += (Date.now() - session.mark) / 1000;
    session.mark = Date.now();
    refs.current.session = null;
    if (session.listened < 20 || session.bookId !== current.bookId) return;
    if (leaving && source.addSessionOnExit) {
      source.addSessionOnExit(session.bookId, {
        id: session.id,
        device: "desktop",
        startedAt: session.startedAt,
        endedAt: Date.now() / 1000,
        listened: session.listened,
        from: session.from,
        to: { chapterId: current.chapterId, seconds: engine.time },
      });
      return;
    }
    void source
      .addSession(session.bookId, {
        id: session.id,
        device: "desktop",
        startedAt: session.startedAt,
        endedAt: Date.now() / 1000,
        listened: session.listened,
        from: session.from,
        to: { chapterId: current.chapterId, seconds: engine.time },
      })
      .catch(() => undefined);
  }, [engine, source]);

  splitSessionRef.current = (at) => {
    const session = refs.current.session;
    if (!session || native) return;
    const book = session.bookId;
    session.listened += (Date.now() - session.mark) / 1000;
    refs.current.session = null;
    if (session.listened >= 20 && source.addSession) {
      void source
        .addSession(book, { id: session.id, device: "desktop", startedAt: session.startedAt, endedAt: Date.now() / 1000,
          listened: session.listened, from: session.from, to: at })
        .catch(() => undefined);
    }
    if (!engine.paused) window.setTimeout(() => openSession(), 0);
  };

  /** Hẹn giờ vừa hết: dừng, trả âm lượng, ghi mốc "tự dừng" cho buổi sáng. */
  const stopBySleep = useCallback(() => {
    night.stop(position());
    engine.pause();
    endFade();
    applySleep({ kind: "off" });
    setSleepStoppedAt(Date.now());
    save(true);
  }, [applySleep, endFade, engine, night, position, save]);

  // ---- sự kiện của bộ máy phát ----------------------------------------------------------------------------

  useEffect(() => {
    engine.setRate(refs.current.rate);
    engine.setVolume(refs.current.volume);
    const syncClock = () => clock.set(engine.time, engine.duration);
    const offs = [
      engine.on("time", () => {
        syncClock();
        save();
      }),
      engine.on("duration", syncClock),
      engine.on("play", () => {
        setPlaying(true);
        refs.current.pausedAt = 0;
        openSession();
        if (!native) applySleep(sleepResumed(refs.current.sleep, Date.now()));
      }),
      engine.on("pause", () => {
        setPlaying(false);
        closeSession();
        syncClock();
        refs.current.pausedAt = Date.now();
        if (!native) applySleep(sleepPaused(refs.current.sleep, Date.now()));
        save(true);
      }),
      engine.on("waiting", () => setBuffering(true)),
      engine.on("playing", () => setBuffering(false)),
      engine.on("ended", () => {
        const current = refs.current.track;
        if (!current) return;
        const target = availableAfter(refs.current.queue, current.chapterId, 1);
        if (native) {
          if (!target) setAtEnd(refs.current.book?.complete === false ? "caughtUp" : "finished");
          refreshLists(current.bookId);
          return;
        }
        save(true);
        if (refs.current.sleep.kind === "chapter") {
          // Hẹn "hết chương": dừng ở đây, nhưng nạp sẵn chương kế ở 0:00 và lưu nó làm chỗ nghe tiếp - sáng mai
          // bấm Tiếp tục là vào chương mới, không phải nghe lại chương vừa xong từ đầu.
          stopBySleep();
          if (target) {
            load({ ...current, chapterId: target.id, chapterTitle: target.fullTitle }, 0, false);
            if (refs.current.purpose === "listen") {
              void source.saveProgress(current.bookId, target.id, 0, target.duration).then(() => refreshLists(current.bookId)).catch(() => undefined);
            }
          }
          return;
        }
        if (target) {
          load({ ...current, chapterId: target.id, chapterTitle: target.fullTitle }, 0, true);
          return;
        }
        const caughtUp = refs.current.book?.complete === false;
        setAtEnd(caughtUp ? "caughtUp" : "finished");
        toast(caughtUp ? "Đã nghe hết phần đã có" : "Đã nghe hết cuốn sách", {
          description: caughtUp ? "Chương tiếp theo sẽ nghe được khi Studio làm xong." : undefined,
        });
      }),
      engine.on("error", () => {
        setError("Không phát được chương này - file có thể đã bị xoá hoặc đang được ghi lại.");
        setBuffering(false);
      }),
      engine.on("chapter", () => {
        if (!native || native.chapterId === null || !native.bookId) return;
        const narrator = refs.current.track?.bookId === native.bookId ? refs.current.track.narrator : "";
        const next: Track = {
          bookId: native.bookId,
          bookTitle: native.bookTitle,
          narrator,
          chapterId: native.chapterId,
          chapterTitle: native.chapterTitle,
        };
        refs.current.track = next;
        setTrack(next);
        setAtEnd("none");
        refreshLists(native.bookId);
      }),
      engine.on("sleep", () => {
        if (!native) return;
        const previousKind = refs.current.sleep.kind;
        applySleep(native.sleep);
        if (previousKind !== "off" && native.sleep.kind === "off" && native.paused) setSleepStoppedAt(Date.now());
      }),
    ];
    return () => offs.forEach((off) => off());
  }, [applySleep, clock, closeSession, engine, load, native, openSession, refreshLists, save, source, stopBySleep]);

  // Đồng hồ chạy theo khung hình khi đang phát: nhãn giây đổi đúng nhịp 1 giây thay vì theo timeupdate (~4 lần/giây,
  // lệch tới 270 ms). Chỉ component nào chọn giá trị đổi mới render lại.
  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    const tick = () => {
      clock.set(engine.time, engine.duration);
      frame = window.requestAnimationFrame(tick);
    };
    frame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frame);
  }, [clock, engine, playing]);

  // Hẹn giờ (bộ máy web): kiểm hạn bằng nhịp riêng - không dựa vào timeupdate - và nhỏ dần theo dB.
  useEffect(() => {
    if (native || !playing || sleep.kind === "off") return;
    const tick = () => {
      const mode = refs.current.sleep;
      const now = Date.now();
      let left: number | null = null;
      if (mode.kind === "minutes") left = sleepLeftMs(mode, now);
      else if (mode.kind === "chapter" && engine.duration > 0) {
        left = ((engine.duration - engine.time) / Math.max(0.25, refs.current.rate)) * 1000;
      }
      if (left === null) return;
      if (mode.kind === "minutes" && left <= 0) {
        stopBySleep();
        return;
      }
      const fadeMs = options.fadeSeconds * 1000;
      if (left < fadeMs) {
        engine.setVolume(refs.current.volume * fadeGain(left, fadeMs));
        if (!refs.current.fading) {
          refs.current.fading = true;
          setFading(true);
          night.fading(position());
        }
      } else if (refs.current.fading) {
        endFade();
      }
      night.checkpoint(position());
    };
    tick();
    const timer = window.setInterval(tick, 100);
    return () => window.clearInterval(timer);
  }, [endFade, engine, native, night, options.fadeSeconds, playing, position, sleep.kind, stopBySleep]);

  // Máy tính: chạm phím/chuột lúc đang nhỏ dần = "lắc máy" - nghe thêm. Phím ấy không làm gì khác (không tạm dừng).
  useEffect(() => {
    if (native || !fading) return;
    const names = ["keydown", "pointerdown", "pointermove", "wheel"] as const;
    const onActivity = (event: Event) => {
      if (event.type === "keydown") {
        event.preventDefault();
        event.stopPropagation();
      }
      extendSleep();
    };
    names.forEach((name) => window.addEventListener(name, onActivity, { capture: true, once: true }));
    return () => names.forEach((name) => window.removeEventListener(name, onActivity, { capture: true }));
  }, [extendSleep, fading, native]);

  // Mọi thao tác trên máy là bằng chứng "còn thức": cho lưới an toàn ngủ quên, và cho nhật ký đêm khi đang hẹn giờ.
  useEffect(() => {
    if (native) return;
    const onActivity = () => {
      refs.current.lastActivity = Date.now();
      if (refs.current.track) refs.current.lastActivityPosition = position();
      if (refs.current.sleep.kind !== "off") night.touch("activity", position());
    };
    const names = ["keydown", "pointerdown", "wheel"] as const;
    names.forEach((name) => window.addEventListener(name, onActivity, { passive: true }));
    return () => names.forEach((name) => window.removeEventListener(name, onActivity));
  }, [native, night, position]);

  // Lưới an toàn: phát liên tục quá lâu mà không ai chạm máy (ngủ quên, quên hẹn giờ) thì tự hẹn 1 phút - nhỏ dần
  // rồi dừng như hẹn giờ thường - và ghi nhật ký đêm để sáng ra thẻ "Tối qua" vẫn giúp tìm lại chỗ.
  useEffect(() => {
    if (native || !playing || sleep.kind !== "off" || options.safetyStopHours <= 0) return;
    const check = () => {
      if (refs.current.sleep.kind !== "off" || refs.current.purpose !== "listen") return;
      if (Date.now() - refs.current.lastActivity < options.safetyStopHours * 3_600_000) return;
      const book = refs.current.book;
      if (book) {
        night.start(book, 1, position(), "safety");
        const before = refs.current.lastActivityPosition;
        if (before) night.touchAt(refs.current.lastActivity, "last-activity", before);
      }
      applySleep(sleepFrom({ kind: "minutes", minutes: 1 }, true, Date.now()));
      toast(`Không thấy ai chạm máy suốt ${options.safetyStopHours} giờ - sẽ tắt sau 1 phút`, {
        id: "safety-stop",
        duration: 60_000,
        action: { label: "Vẫn đang nghe", onClick: () => setSleepRef.current({ kind: "off" }) },
      });
    };
    const timer = window.setInterval(check, 30_000);
    return () => window.clearInterval(timer);
  }, [applySleep, native, night, options.safetyStopHours, playing, position, sleep.kind]);

  // Lịch đêm: bắt đầu nghe trong khung giờ thì tự hẹn giờ (trừ khi đêm nay người dùng đã tự tắt nó).
  useEffect(() => {
    if (native || !playing || sleep.kind !== "off" || refs.current.purpose !== "listen") return;
    const night_ = scheduleWindow(options.schedule);
    if (!night_ || !options.schedule || refs.current.scheduleOffFor === night_) return;
    setSleepRef.current({ kind: "minutes", minutes: options.schedule.minutes });
    toast(`Đã tự hẹn giờ ${options.schedule.minutes} phút`, {
      id: "sleep-schedule",
      description: `Lịch đêm ${options.schedule.from}-${options.schedule.to}. Tắt ở nút mặt trăng nếu chưa muốn ngủ.`,
    });
  }, [native, options.schedule, playing, sleep.kind]);

  useEffect(() => {
    const onHide = () => {
      save(true);
      closeSession(true);
      night.flush();
    };
    window.addEventListener("pagehide", onHide);
    return () => window.removeEventListener("pagehide", onHide);
  }, [closeSession, night, save]);

  // Phím tắt (máy tính). Không tranh phím với ô nhập, thanh trượt, tab, menu, hộp thoại; Space trên một nút chỉ
  // kích hoạt nút đó khi người dùng Tab tới nó bằng bàn phím (:focus-visible) - bấm chuột xong thì Space vẫn là
  // phát/tạm dừng như Spotify, YouTube.
  useEffect(() => {
    if (!keyboard || native) return;
    // Focus đến từ chuột hay bàn phím? Chỉ khi người dùng Tab tới một nút thì Space mới kích hoạt nút ấy.
    let keyboardNavigation = false;
    const onPointer = () => {
      keyboardNavigation = false;
    };
    const onTab = (event: KeyboardEvent) => {
      if (event.key === "Tab" || event.key.startsWith("Arrow")) keyboardNavigation = true;
    };
    window.addEventListener("pointerdown", onPointer, true);
    window.addEventListener("keydown", onTab, true);
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (!target || !refs.current.track) return;
      if (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (target.closest('[role="menu"],[role="listbox"],[role="dialog"]')) return;
      const widget = target.closest('[role="slider"],[role="tab"],[role="radio"],[role="option"],[role="menuitem"]');
      const keyboardFocused = target !== document.body && keyboardNavigation;
      switch (event.key) {
        case " ": {
          // Thanh trượt không dùng Space vào việc gì: Space trên thanh tua vẫn là phát/tạm dừng.
          const activatable = target.tagName === "BUTTON" || target.tagName === "A" || (widget && widget.getAttribute("role") !== "slider");
          if (activatable && keyboardFocused) return;
          event.preventDefault();
          toggle();
          break;
        }
        case "ArrowLeft":
        case "ArrowRight": {
          if (widget) return;
          event.preventDefault();
          const forward = event.key === "ArrowRight";
          if (event.shiftKey) (forward ? next : previous)();
          else skip(forward ? SKIP_SECONDS : -SKIP_SECONDS);
          break;
        }
        case "b":
        case "B":
          event.preventDefault();
          window.dispatchEvent(new CustomEvent("ebook-reader:bookmark"));
          break;
        case "m":
        case "M":
          event.preventDefault();
          if (refs.current.volume > 0) {
            refs.current.muted = refs.current.volume;
            setVolume(0);
          } else {
            setVolume(refs.current.muted || 0.9);
          }
          break;
        case "[":
        case "]":
          event.preventDefault();
          setRate(nearestSpeed(refs.current.rate, event.key === "]" ? 1 : -1));
          break;
        default:
          break;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onPointer, true);
      window.removeEventListener("keydown", onTab, true);
    };
  }, [keyboard, native, next, previous, setRate, setVolume, skip, toggle]);

  // Nút media của hệ điều hành (bộ máy web; lõi native tự lo phần này).
  useEffect(() => {
    if (native || !("mediaSession" in navigator) || !track) return;
    const handlers: [MediaSessionAction, MediaSessionActionHandler][] = [
      ["play", () => resume()],
      ["pause", () => pause()],
      ["stop", () => pause()],
      ["seekbackward", () => skip(-SKIP_SECONDS)],
      ["seekforward", () => skip(SKIP_SECONDS)],
      ["previoustrack", () => previous()],
      ["nexttrack", () => next()],
      ["seekto", (details) => {
        if (details.seekTime !== undefined) seek(details.seekTime);
      }],
    ];
    for (const [action, handler] of handlers) {
      try {
        navigator.mediaSession.setActionHandler(action, handler);
      } catch {
        /* không hỗ trợ */
      }
    }
  }, [native, next, pause, previous, resume, seek, skip, track]);

  useEffect(() => {
    if (native || !("mediaSession" in navigator) || !track) return;
    navigator.mediaSession.playbackState = playing ? "playing" : "paused";
    const report = () => {
      const duration = engine.duration;
      if (!duration) return;
      try {
        navigator.mediaSession.setPositionState({ duration, playbackRate: refs.current.rate, position: Math.min(engine.time, duration) });
      } catch {
        /* vị trí không hợp lệ lúc đang nạp */
      }
    };
    report();
    const timer = playing ? window.setInterval(report, 5000) : undefined;
    const off = engine.on("duration", report);
    return () => {
      window.clearInterval(timer);
      off();
    };
  }, [engine, native, playing, rate, track]);

  const value = useMemo<PlayerValue>(() => ({
    track, queue, playing, buffering, rate, volume, sleep, fading, sleepStoppedAt, lastSleepMinutes, purpose, atEnd,
    canGoBack, error, options,
    play, prepare, toggle, resume, pause, seek, skip, next, previous, jumpTo, goBack, setRate, setVolume, setSleep,
    extendSleep, addBookmark, close, positionStamp,
  }), [track, queue, playing, buffering, rate, volume, sleep, fading, sleepStoppedAt, lastSleepMinutes, purpose, atEnd,
    canGoBack, error, options, play, prepare, toggle, resume, pause, seek, skip, next, previous, jumpTo, goBack, setRate,
    setVolume, setSleep, extendSleep, addBookmark, close, positionStamp]);

  const nowPlaying = useMemo(() => ({ expanded, setExpanded }), [expanded]);

  return (
    <ClockContext.Provider value={clock}>
      <PlayerContext.Provider value={value}>
        <NowPlayingContext.Provider value={nowPlaying}>{children}</NowPlayingContext.Provider>
      </PlayerContext.Provider>
    </ClockContext.Provider>
  );
}
