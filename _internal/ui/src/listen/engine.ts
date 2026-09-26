// Bộ máy phát. Máy tính dùng <audio> của trình duyệt; Android thay bằng bộ phát native (Media3/ExoPlayer) để
// phát khi tắt màn hình, hiện điều khiển ở màn hình khoá và nhận nút tai nghe. Trình phát (player.tsx) chỉ biết
// giao diện này.
//
// Bộ máy web chỉ phát MỘT chương; trình phát lo hàng đợi, hẹn giờ, lưu vị trí. Bộ máy native (`native: true`) giữ
// cả cuốn trong hàng đợi và tự lo hết những việc đó ở lõi - vì tắt màn hình thì JavaScript bị treo, nên những thứ
// phải chạy khi người nghe đã ngủ không được nằm ở JavaScript.

import type { Bookmark, ListenChapter } from "./model";
import type { SleepMode, SleepRequest } from "./sleep";

export interface TrackInfo {
  url: string;
  title: string;
  album: string;
  artist: string;
  artwork?: string;
}

export type EngineEvent =
  | "time"
  | "duration"
  | "play"
  | "pause"
  | "ended"
  | "error"
  | "waiting"
  | "playing"
  /** chỉ bộ máy native: chương/cuốn đang phát đổi (tự sang chương, nút trên thông báo...). */
  | "chapter"
  /** chỉ bộ máy native: hẹn giờ ngủ đổi (đặt, gia hạn, lắc máy, tự tắt). */
  | "sleep";

export interface AudioEngine {
  load(track: TrackInfo, startAt: number, autoplay: boolean): void;
  play(): void;
  pause(): void;
  seek(seconds: number): void;
  setRate(rate: number): void;
  setVolume(volume: number): void;
  stop(): void;
  readonly time: number;
  readonly duration: number;
  readonly paused: boolean;
  readonly ended: boolean;
  on(event: EngineEvent, handler: () => void): () => void;
}

export interface NativeQueue {
  bookId: string;
  bookTitle: string;
  narrator: string;
  chapters: ListenChapter[];
  chapterId: number;
  at: number;
  rate: number;
  autoplay: boolean;
}

export interface NativeEngine extends AudioEngine {
  readonly native: true;
  loadQueue(queue: NativeQueue): void;
  toggle(): void;
  skipBy(delta: number): void;
  next(): void;
  previous(): void;
  jumpTo(chapterId: number, seconds: number): void;
  setSleep(request: SleepRequest): void;
  extendSleep(minutes?: number): void;
  addBookmark(note: string): Promise<Bookmark>;
  readonly sleep: SleepMode;
  readonly bookId: string;
  readonly bookTitle: string;
  readonly chapterId: number | null;
  readonly chapterTitle: string;
  readonly rate: number;
}

export function isNative(engine: AudioEngine): engine is NativeEngine {
  return (engine as Partial<NativeEngine>).native === true;
}

export class WebAudioEngine implements AudioEngine {
  private audio = new Audio();
  private pendingSeek: number | null = null;

  constructor() {
    this.audio.preload = "auto";
    // ?mute=1: kiểm thử tự động không được phát tiếng ra loa của người dùng.
    this.audio.muted = new URLSearchParams(window.location.search).get("mute") === "1";
    this.audio.addEventListener("loadedmetadata", () => {
      if (this.pendingSeek !== null) {
        this.audio.currentTime = Math.min(this.pendingSeek, Math.max(0, (this.audio.duration || 0) - 1));
        this.pendingSeek = null;
      }
    });
  }

  load(track: TrackInfo, startAt: number, autoplay: boolean): void {
    this.pendingSeek = startAt > 0 ? startAt : null;
    this.audio.src = track.url;
    if ("mediaSession" in navigator) {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: track.title,
        album: track.album,
        artist: track.artist,
        artwork: track.artwork ? [{ src: track.artwork, sizes: "512x512", type: "image/png" }] : [],
      });
    }
    if (autoplay) void this.audio.play().catch(() => undefined);
  }

  play(): void {
    void this.audio.play().catch(() => undefined);
  }

  pause(): void {
    this.audio.pause();
  }

  seek(seconds: number): void {
    const limit = Number.isFinite(this.audio.duration) ? this.audio.duration : seconds;
    const target = Math.max(0, Math.min(limit, seconds));
    if (this.audio.readyState < 1) this.pendingSeek = target;
    else this.audio.currentTime = target;
  }

  setRate(rate: number): void {
    this.audio.playbackRate = rate;
    this.audio.defaultPlaybackRate = rate;
  }

  setVolume(volume: number): void {
    this.audio.volume = Math.max(0, Math.min(1, volume));
  }

  stop(): void {
    this.audio.pause();
    this.audio.removeAttribute("src");
    this.audio.load();
  }

  get time(): number {
    return this.pendingSeek ?? (this.audio.currentTime || 0);
  }

  get duration(): number {
    return Number.isFinite(this.audio.duration) ? this.audio.duration : 0;
  }

  get paused(): boolean {
    return this.audio.paused;
  }

  get ended(): boolean {
    return this.audio.ended;
  }

  on(event: EngineEvent, handler: () => void): () => void {
    const names: Partial<Record<EngineEvent, string>> = {
      time: "timeupdate",
      duration: "loadedmetadata",
      play: "play",
      pause: "pause",
      ended: "ended",
      error: "error",
      waiting: "waiting",
      playing: "playing",
    };
    const name = names[event];
    if (!name) return () => undefined;
    const wrapped = event === "error" ? () => this.audio.getAttribute("src") && handler() : handler;
    this.audio.addEventListener(name, wrapped);
    return () => this.audio.removeEventListener(name, wrapped);
  }
}
