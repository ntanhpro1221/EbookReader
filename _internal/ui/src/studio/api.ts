// Hợp đồng với server Python (ebook_reader/webui/server.py). Mọi chữ hiển thị đã được server dịch sẵn
// sang tiếng Việt (humanize.py); ở đây chỉ định kiểu và gọi.

export type Phase = "idle" | "analysis" | "casting" | "synthesis" | "done" | "stopped" | "error";

export interface Position {
  chapterId: number;
  seconds: number;
  duration: number;
  at: number;
}

export interface BookSummary {
  id: string;
  path: string;
  title: string;
  status: string;
  stage: string;
  phase: Phase;
  statusLabel: string;
  running: boolean;
  interrupted: boolean;
  starting: boolean;
  startError: string;
  createdAt: number | null;
  updatedAt: number | null;
  lastError: string;
  settings: { profile: string; profileLabel: string; narrator: string };
  chapters: { total: number; completed: number; failed: number; working: number };
  segments: { total: number; analyzed: number; recorded: number; finished: number; failed: number };
  progress: { overall: number; analysis: number; synthesis: number };
  audioSeconds: number;
  eta: { phase: Phase; seconds: number } | null;
  position: Position | null;
  broken?: string;
}

export interface Chapter {
  id: number;
  index: number;
  title: string;
  displayTitle: string;
  subtitle: string;
  fullTitle: string;
  status: string;
  statusLabel: string;
  segments: {
    total: number;
    analyzed: number;
    recorded: number;
    finished: number;
    failed: number;
    warnings: number;
  };
  seconds: number;
  playable: boolean;
  startedAt: number | null;
  completedAt: number | null;
  lastError: string;
}

export interface VoiceProfile {
  key: string;
  preset: string;
  tone: string;
}

export interface CastMember {
  name: string;
  displayName: string;
  gender: string;
  age: string;
  lines: number;
  seconds: number;
  voice: VoiceProfile | null;
  sampleId: number | null;
  firstChapter: string;
}

export interface Cast {
  narrator: { voice: string; lines: number; seconds: number; profile: VoiceProfile | null };
  characters: CastMember[];
  extras: CastMember[];
}

export interface ActivityItem {
  id: string;
  at: number;
  level: "info" | "success" | "warning" | "error";
  kind?: string;
  code?: string;
  text: string;
}

export interface ScriptSegment {
  id: number;
  paragraph: number;
  text: string;
  kind: "narration" | "dialogue" | "thought" | string;
  speaker: string;
  start: number | null;
  end: number | null;
  status: string;
}

export interface Script {
  chapterId: number;
  title: string;
  timed: boolean;
  duration: number;
  segments: ScriptSegment[];
}

export interface Voice {
  name: string;
  gender: string;
  region: string;
  style: string;
  recommended: boolean;
  preview: boolean;
}

export interface ScannedFile {
  path: string;
  name: string;
  title: string;
  firstLine: string;
  words: number;
  bytes: number;
}

export interface ScanResult {
  files: ScannedFile[];
  skipped: string[];
  suggestedTitle: string;
  totals: { chapters: number; words: number; audioSeconds: number };
}

export interface AppInfo {
  version: string;
  readOnly: boolean;
  dialogs: boolean;
  libraryRoot: string;
  theme: "system" | "light" | "dark";
  playbackRate: number;
  volume: number;
  sleepFadeSeconds: number;
  sleepExtendMinutes: number;
}

export interface Preferences {
  libraryRoot: string;
  theme: "system" | "light" | "dark";
  playbackRate: number;
  volume: number;
  sleepFadeSeconds: number;
  sleepExtendMinutes: number;
}

// Mã phiên do cửa sổ app gắn vào URL (?t=...). Giữ lại trong phiên để điều hướng nội bộ không làm mất nó.
const TOKEN_KEY = "ebook-reader-token";
const token: string = (() => {
  const fromUrl = new URLSearchParams(window.location.search).get("t");
  try {
    if (fromUrl) sessionStorage.setItem(TOKEN_KEY, fromUrl);
    return fromUrl ?? sessionStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return fromUrl ?? "";
  }
})();

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(path: string, init?: { method?: string; body?: unknown }): Promise<T> {
  const response = await fetch(path, {
    method: init?.method ?? "GET",
    headers: {
      "X-Ebook-Token": token,
      ...(init?.body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: init?.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new ApiError(response.status, (data && data.error) || `Lỗi ${response.status}`);
  }
  return data as T;
}

export function mediaUrl(path: string): string {
  return token ? `${path}${path.includes("?") ? "&" : "?"}t=${encodeURIComponent(token)}` : path;
}

export const urls = {
  chapterAudio: (bookId: string, chapterId: number) => mediaUrl(`/media/books/${bookId}/chapters/${chapterId}`),
  sample: (bookId: string, segmentId: number) => mediaUrl(`/media/books/${bookId}/samples/${segmentId}`),
  voice: (name: string) => mediaUrl(`/media/voices/${encodeURIComponent(name)}`),
};
