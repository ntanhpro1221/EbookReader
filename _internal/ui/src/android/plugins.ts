import { registerPlugin, type PluginListenerHandle } from "@capacitor/core";
import type { Bookmark, ListeningState } from "@/listen/model";

// Hai plugin native của app Android (mobile/android/app/src/main/java/vn/ebookreader/player):
//  EbookPlayer  - lõi phát Media3: hàng đợi chương, hẹn giờ ngủ, lắc để nghe thêm, nhật ký đêm.
//  EbookLibrary - sách đã tải + đồng bộ với máy tính qua Wi-Fi.

export interface NativeSleep {
  mode: "off" | "minutes" | "chapter";
  remaining?: number;
  minutes?: number;
  stoppedAt?: number;
}

export interface NativeState {
  kind?: string;
  bookId: string;
  bookTitle: string;
  chapterId: number | null;
  chapterTitle: string;
  position: number;
  duration: number;
  playing: boolean;
  buffering: boolean;
  rate: number;
  sleep: NativeSleep;
}

export interface BedtimePosition {
  chapterId: number | null;
  chapterTitle: string;
  seconds: number;
}

export interface BedtimeEvent {
  type: "timer" | "touch" | "shake" | "still" | "moved" | "stopped";
  at: number;
  action?: string;
  minutes?: number;
  position: BedtimePosition;
}

export interface BedtimeSession {
  bookId: string;
  bookTitle: string;
  startedAt: number;
  endedAt?: number;
  dismissed?: boolean;
  events: BedtimeEvent[];
  timeline: (BedtimePosition & { at: number })[];
}

export interface EbookPlayerPlugin {
  load(options: {
    bookId: string;
    bookTitle: string;
    narrator: string;
    chapters: { id: number; title: string; file: string; duration: number }[];
    chapterId: number;
    seconds: number;
    rate: number;
  }): Promise<NativeState>;
  play(): Promise<NativeState>;
  pause(): Promise<NativeState>;
  toggle(): Promise<NativeState>;
  next(): Promise<NativeState>;
  previous(): Promise<NativeState>;
  seekTo(options: { seconds: number }): Promise<NativeState>;
  skip(options: { delta: number }): Promise<NativeState>;
  setRate(options: { rate: number }): Promise<NativeState>;
  jumpTo(options: { chapterId: number; seconds: number }): Promise<NativeState>;
  getState(): Promise<NativeState>;
  addBookmark(options: { note: string }): Promise<Bookmark>;
  setSleep(options: { mode: "off" | "minutes" | "chapter"; minutes?: number }): Promise<NativeState>;
  extendSleep(options: { minutes?: number }): Promise<NativeState>;
  configure(options: {
    sleepExtendMinutes?: number;
    sleepFadeSeconds?: number;
    shakeToExtend?: boolean;
    rewindAfterMinutes?: number;
    rewindSeconds?: number;
  }): Promise<NativeState>;
  lastNight(): Promise<{ session: BedtimeSession | null }>;
  dismissLastNight(): Promise<void>;
  addListener(event: "state", handler: (state: NativeState) => void): Promise<PluginListenerHandle>;
}

export interface RemoteBook {
  id: string;
  title: string;
  narrator: string;
  duration: number;
  chaptersTotal: number;
  chaptersAvailable: number;
  complete: boolean;
  updatedAt: number | null;
  downloaded: boolean;
  localChapters: number;
}

export interface ManifestChapter {
  id: number;
  index: number;
  title: string;
  subtitle: string;
  fullTitle: string;
  duration: number;
  available: boolean;
  file: string | null;
  size: number;
  script: string | null;
}

export interface LocalBook {
  format: string;
  id: string;
  title: string;
  narrator: string;
  duration: number;
  chaptersTotal: number;
  chaptersAvailable: number;
  complete: boolean;
  version: string;
  chapters: ManifestChapter[];
  samples: string[];
  state: ListeningState;
  bytes?: number;
}

export interface DownloadEvent {
  bookId: string;
  done?: number;
  total?: number;
  files?: number;
  filesTotal?: number;
  finished?: boolean;
  error?: string;
}

export interface EbookLibraryPlugin {
  info(): Promise<{ root: string }>;
  discover(options: { timeoutMs?: number }): Promise<{ computers: { host: string; port: number; name: string }[] }>;
  pair(options: { host: string; port: number; code: string; device?: string }): Promise<{ name: string }>;
  connection(): Promise<{ paired: boolean; host: string; port: number; name: string }>;
  unpair(): Promise<void>;
  remoteLibrary(): Promise<{ name: string; books: RemoteBook[] }>;
  download(options: { bookId: string }): Promise<{ bookId: string }>;
  localBooks(): Promise<{ books: LocalBook[] }>;
  book(options: { id: string }): Promise<LocalBook>;
  readText(options: { id: string; path: string }): Promise<{ text: string }>;
  deleteBook(options: { id: string }): Promise<void>;
  storage(): Promise<{ bytes: number; free: number }>;
  progress(options: { id: string; chapterId: number; seconds: number; duration: number }): Promise<ListeningState>;
  setChapterDone(options: { id: string; chapterId: number; done: boolean }): Promise<ListeningState>;
  setFinished(options: { id: string; finished: boolean }): Promise<ListeningState>;
  setRate(options: { id: string; rate: number }): Promise<void>;
  addBookmark(options: { id: string; chapterId: number; seconds: number; note: string }): Promise<Bookmark>;
  updateBookmark(options: { id: string; markId: string; note: string }): Promise<void>;
  deleteBookmark(options: { id: string; markId: string }): Promise<void>;
  syncState(options: { id: string }): Promise<ListeningState>;
  addListener(event: "download", handler: (event: DownloadEvent) => void): Promise<PluginListenerHandle>;
}

export const EbookPlayer = registerPlugin<EbookPlayerPlugin>("EbookPlayer");
export const EbookLibrary = registerPlugin<EbookLibraryPlugin>("EbookLibrary");
