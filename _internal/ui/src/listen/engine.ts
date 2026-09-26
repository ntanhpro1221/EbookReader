// Bộ máy phát. Máy tính dùng <audio> của trình duyệt; Android thay bằng bộ phát native (Media3/ExoPlayer) để
// phát khi tắt màn hình, hiện điều khiển ở màn hình khoá và nhận nút tai nghe. Trình phát (player.tsx) chỉ biết
// giao diện này.

export interface TrackInfo {
  url: string;
  title: string;
  album: string;
  artist: string;
}

export type EngineEvent = "time" | "duration" | "play" | "pause" | "ended" | "error" | "waiting" | "playing";

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
  on(event: EngineEvent, handler: () => void): () => void;
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
      navigator.mediaSession.metadata = new MediaMetadata({ title: track.title, album: track.album, artist: track.artist });
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
    this.audio.currentTime = Math.max(0, Math.min(limit, seconds));
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
    return this.audio.currentTime || 0;
  }

  get duration(): number {
    return Number.isFinite(this.audio.duration) ? this.audio.duration : 0;
  }

  get paused(): boolean {
    return this.audio.paused;
  }

  on(event: EngineEvent, handler: () => void): () => void {
    const names: Record<EngineEvent, string> = {
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
    const wrapped = event === "error" ? () => this.audio.getAttribute("src") && handler() : handler;
    this.audio.addEventListener(name, wrapped);
    return () => this.audio.removeEventListener(name, wrapped);
  }
}
