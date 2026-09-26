import type { AudioEngine, EngineEvent, NativeQueue, TrackInfo } from "@/listen/engine";
import type { Bookmark } from "@/listen/model";
import type { SleepMode } from "@/listen/player";
import { chapterFiles } from "./androidSource";
import { EbookPlayer, type NativeState } from "./plugins";

// Bộ máy phát của Android: mọi thứ thật sự chạy trong lõi Media3 (Playback.kt), kể cả khi tắt màn hình.
// Lớp này chỉ chuyển lệnh xuống và biến sự kiện "state" của lõi thành sự kiện mà trình phát (player.tsx) hiểu.

type Event = EngineEvent | "chapter" | "sleep";

export class NativeAudioEngine implements AudioEngine {
  readonly native = true;
  private current: NativeState | null = null;
  private handlers = new Map<Event, Set<() => void>>();

  constructor() {
    void EbookPlayer.addListener("state", (state) => this.receive(state));
    void EbookPlayer.getState().then((state) => this.receive(state)).catch(() => undefined);
  }

  private fire(event: Event) {
    this.handlers.get(event)?.forEach((handler) => handler());
  }

  private receive(next: NativeState) {
    const previous = this.current;
    this.current = next;
    if (!previous || previous.playing !== next.playing) this.fire(next.playing ? "play" : "pause");
    if (!previous || previous.duration !== next.duration) this.fire("duration");
    if (!previous || previous.chapterId !== next.chapterId || previous.bookId !== next.bookId) this.fire("chapter");
    if (!previous || JSON.stringify(previous.sleep) !== JSON.stringify(next.sleep)) this.fire("sleep");
    if (!previous || previous.buffering !== next.buffering) this.fire(next.buffering ? "waiting" : "playing");
    if (next.kind === "ended") this.fire("ended");
    this.fire("time");
  }

  get state(): NativeState | null {
    return this.current;
  }

  loadQueue(queue: NativeQueue): void {
    const files = chapterFiles.get(queue.bookId);
    void EbookPlayer.load({
      bookId: queue.bookId,
      bookTitle: queue.bookTitle,
      narrator: queue.narrator,
      chapters: queue.chapters
        .filter((chapter) => files?.get(chapter.id))
        .map((chapter) => ({ id: chapter.id, title: chapter.fullTitle, file: files!.get(chapter.id)!, duration: chapter.duration })),
      chapterId: queue.chapterId,
      seconds: queue.at,
      rate: queue.rate,
    }).then((state) => this.receive(state));
  }

  load(_track: TrackInfo, _startAt: number, _autoplay: boolean): void {
    /* Android nạp cả cuốn qua loadQueue */
  }

  play(): void {
    void EbookPlayer.play().then((state) => this.receive(state));
  }

  pause(): void {
    void EbookPlayer.pause().then((state) => this.receive(state));
  }

  toggle(): void {
    void EbookPlayer.toggle().then((state) => this.receive(state));
  }

  seek(seconds: number): void {
    void EbookPlayer.seekTo({ seconds }).then((state) => this.receive(state));
  }

  skipBy(delta: number): void {
    void EbookPlayer.skip({ delta }).then((state) => this.receive(state));
  }

  setRate(rate: number): void {
    void EbookPlayer.setRate({ rate });
  }

  setVolume(_volume: number): void {
    /* âm lượng theo phím âm lượng của máy */
  }

  stop(): void {
    void EbookPlayer.pause();
  }

  next(): void {
    void EbookPlayer.next().then((state) => this.receive(state));
  }

  previous(): void {
    void EbookPlayer.previous().then((state) => this.receive(state));
  }

  jumpTo(chapterId: number, seconds: number): void {
    void EbookPlayer.jumpTo({ chapterId, seconds }).then((state) => this.receive(state));
  }

  setSleep(mode: SleepMode): void {
    void EbookPlayer.setSleep(
      mode.kind === "minutes" ? { mode: "minutes", minutes: mode.minutes } : { mode: mode.kind === "chapter" ? "chapter" : "off" },
    ).then((state) => this.receive(state));
  }

  extendSleep(minutes?: number): void {
    void EbookPlayer.extendSleep({ minutes }).then((state) => this.receive(state));
  }

  addBookmark(note: string): Promise<Bookmark> {
    return EbookPlayer.addBookmark({ note });
  }

  get sleep(): SleepMode {
    const sleep = this.current?.sleep;
    if (!sleep || sleep.mode === "off") return { kind: "off" };
    if (sleep.mode === "chapter") return { kind: "chapter" };
    return { kind: "minutes", minutes: sleep.minutes ?? 0, endsAt: Date.now() + (sleep.remaining ?? 0) * 1000 };
  }

  get chapterId(): number | null {
    return this.current?.chapterId ?? null;
  }

  get bookId(): string {
    return this.current?.bookId ?? "";
  }

  get time(): number {
    return this.current?.position ?? 0;
  }

  get duration(): number {
    return this.current?.duration ?? 0;
  }

  get paused(): boolean {
    return !this.current?.playing;
  }

  get rate(): number {
    return this.current?.rate ?? 1;
  }

  on(event: EngineEvent | "chapter" | "sleep", handler: () => void): () => void {
    const set = this.handlers.get(event) ?? new Set();
    set.add(handler);
    this.handlers.set(event, set);
    return () => set.delete(handler);
  }
}
