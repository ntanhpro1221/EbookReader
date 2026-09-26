import type { EngineEvent, NativeEngine, NativeQueue, TrackInfo } from "@/listen/engine";
import type { Bookmark } from "@/listen/model";
import type { SleepMode, SleepRequest } from "@/listen/sleep";
import { chapterFiles } from "./androidSource";
import { EbookPlayer, type NativeState } from "./plugins";

// Bộ máy phát của Android: mọi thứ thật sự chạy trong lõi Media3 (Playback.kt), kể cả khi tắt màn hình.
// Lớp này chỉ chuyển lệnh xuống và biến sự kiện "state" của lõi thành sự kiện mà trình phát (player.tsx) hiểu.
//
// Lõi báo vị trí mỗi nửa giây; giữa hai lần báo, `time` nội suy theo đồng hồ và tốc độ để nhãn giây trên màn hình
// chạy đều thay vì nhảy từng nửa giây.

export class NativeAudioEngine implements NativeEngine {
  readonly native = true as const;
  private current: NativeState | null = null;
  private receivedAt = 0;
  private handlers = new Map<EngineEvent, Set<() => void>>();

  constructor() {
    void EbookPlayer.addListener("state", (state) => this.receive(state));
    void EbookPlayer.getState().then((state) => this.receive(state)).catch(() => undefined);
  }

  private fire(event: EngineEvent) {
    this.handlers.get(event)?.forEach((handler) => handler());
  }

  private receive(next: NativeState) {
    const previous = this.current;
    this.current = next;
    this.receivedAt = Date.now();
    if (!previous || previous.chapterId !== next.chapterId || previous.bookId !== next.bookId) this.fire("chapter");
    if (!previous || previous.playing !== next.playing) this.fire(next.playing ? "play" : "pause");
    if (!previous || previous.duration !== next.duration) this.fire("duration");
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
      autoplay: queue.autoplay,
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
    void EbookPlayer.setRate({ rate }).then((state) => this.receive(state));
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

  setSleep(request: SleepRequest): void {
    const options =
      request.kind === "minutes" ? { mode: "minutes" as const, minutes: request.minutes } : { mode: request.kind === "chapter" ? ("chapter" as const) : ("off" as const) };
    void EbookPlayer.setSleep(options).then((state) => this.receive(state));
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
    return {
      kind: "minutes",
      minutes: sleep.minutes ?? 0,
      leftMs: (sleep.remaining ?? 0) * 1000,
      since: this.current?.playing ? this.receivedAt : null,
    };
  }

  get bookId(): string {
    return this.current?.bookId ?? "";
  }

  get bookTitle(): string {
    return this.current?.bookTitle ?? "";
  }

  get chapterId(): number | null {
    return this.current?.chapterId ?? null;
  }

  get chapterTitle(): string {
    return this.current?.chapterTitle ?? "";
  }

  get time(): number {
    const state = this.current;
    if (!state) return 0;
    if (!state.playing) return state.position;
    const elapsed = ((Date.now() - this.receivedAt) / 1000) * (state.rate || 1);
    return Math.min(state.duration || Infinity, state.position + Math.min(elapsed, 2));
  }

  get duration(): number {
    return this.current?.duration ?? 0;
  }

  get paused(): boolean {
    return !this.current?.playing;
  }

  get ended(): boolean {
    return this.current?.kind === "ended";
  }

  get rate(): number {
    return this.current?.rate ?? 1;
  }

  on(event: EngineEvent, handler: () => void): () => void {
    const set = this.handlers.get(event) ?? new Set();
    set.add(handler);
    this.handlers.set(event, set);
    return () => set.delete(handler);
  }
}
