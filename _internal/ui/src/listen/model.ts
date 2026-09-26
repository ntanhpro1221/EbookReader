// Hợp đồng dữ liệu của phía NGHE - chung cho máy tính và Android.
// Máy tính: server cục bộ dựng từ project (ebook_reader/webui/listen_view.py).
// Android: đọc từ gói sách đã tải về (book.json cùng hình dạng).

export interface ListenChapter {
  id: number;
  index: number;
  title: string;
  subtitle: string;
  fullTitle: string;
  duration: number;
  available: boolean;
}

export interface Bookmark {
  id: string;
  chapterId: number;
  seconds: number;
  note: string;
  at: number;
  /** Máy chủ trả về dấu đã có ngay chỗ ấy (±5 giây) thay vì tạo dấu trùng. */
  existing?: boolean;
}

export interface ChapterState {
  heard: number;
  done: boolean;
  duration?: number;
  at?: number;
}

export interface ListeningState {
  last?: { chapterId: number; seconds: number; at: number };
  chapters: Record<string, ChapterState>;
  rate?: number;
  finished?: boolean;
  bookmarks: Bookmark[];
  /** Chỗ đọc dở ở chế độ đọc (câu thứ `index` của chương). */
  reading?: { chapterId: number; index: number; at: number };
  updatedAt?: number;
}

export interface BookProgress {
  heardSeconds: number;
  totalSeconds: number;
  fraction: number;
  chaptersDone: number;
  finished: boolean;
  /** Sách đang làm dở, đã nghe hết phần đã có - chưa phải "nghe xong". */
  caughtUp?: boolean;
}

export interface ListenBook {
  id: string;
  title: string;
  narrator: string;
  duration: number;
  chaptersTotal: number;
  chaptersAvailable: number;
  complete: boolean;
  producing: boolean;
  /** Chưa làm xong và cũng không đang làm (Studio đã dừng). */
  paused?: boolean;
  updatedAt: number | null;
  state: ListeningState;
  progress: BookProgress;
  lastChapterTitle?: string;
  /** Sách đang làm: ước lượng của giai đoạn hiện tại (máy tính). */
  eta?: { phase: string; seconds: number } | null;
  chapters?: ListenChapter[];
}

/** Bộ và số tập từ tên sách ("Throne of Magical Arcana · Tập 16" -> bộ "Throne of Magical Arcana", tập 16). */
export function seriesOf(title: string): { series: string; volume: number | null } {
  const match = title.match(/^(.*?)\s*[·|:—–-]\s*(?:Tập|Quyển|Phần|Vol\.?|Book)\s*(\d+)\b/i);
  if (!match) return { series: title.trim(), volume: null };
  return { series: match[1].trim(), volume: Number(match[2]) };
}

/** Một phiên nghe: bấm phát tới lúc dừng. */
export interface ListeningSession {
  id: string;
  device: string;
  startedAt: number;
  endedAt: number;
  listened: number;
  from: { chapterId: number; seconds: number };
  to: { chapterId: number; seconds: number };
}

// ---- Nhật ký đêm (hẹn giờ ngủ) ------------------------------------------------------------------------------
// Cùng hình dạng với nhật ký của lõi phát Android (Bedtime.kt); máy tính ghi bằng NightRecorder (night.ts).

export interface NightPosition {
  chapterId: number | null;
  chapterTitle: string;
  seconds: number;
}

export interface NightEvent {
  type: "timer" | "touch" | "shake" | "extend" | "still" | "moved" | "fading" | "stopped";
  at: number;
  action?: string;
  minutes?: number;
  position: NightPosition;
}

export interface NightSession {
  id?: string;
  device?: string;
  bookId?: string;
  bookTitle: string;
  startedAt: number;
  endedAt?: number | null;
  dismissed?: boolean;
  events: NightEvent[];
  timeline: (NightPosition & { at: number })[];
}

export interface ScriptSegment {
  id: number;
  paragraph: number;
  text: string;
  kind: "narration" | "dialogue" | "thought" | "heading" | string;
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

export interface CastMember {
  name: string;
  displayName: string;
  gender: string;
  age: string;
  lines: number;
  seconds: number;
  voice: { key: string; preset: string; tone: string } | null;
  sampleId: number | null;
  firstChapter: string;
}

export interface Cast {
  narrator: { voice: string; lines: number; seconds: number };
  characters: CastMember[];
  extras: CastMember[];
}

/** Chương nên phát khi bấm "Nghe": chỗ đang nghe dở nếu chương ấy còn nghe được (nghe gần hết thì sang chương
 *  kế), không thì chương đầu tiên chưa nghe xong, cuối cùng là chương đầu. */
export function resumePoint(book: ListenBook, chapters: ListenChapter[]): { chapter: ListenChapter; at: number } | null {
  const playable = chapters.filter((chapter) => chapter.available);
  if (!playable.length) return null;
  const last = book.state.last;
  if (last) {
    const index = playable.findIndex((chapter) => chapter.id === last.chapterId);
    if (index >= 0) {
      const chapter = playable[index];
      const nearEnd = chapter.duration > 0 && chapter.duration - last.seconds < 15;
      if (!nearEnd) return { chapter, at: last.seconds };
      if (playable[index + 1]) return { chapter: playable[index + 1], at: 0 };
      // Nghe tới cuối chương cuối ĐÃ CÓ của một cuốn còn đang làm: đứng yên ở đó, đừng quay về chương đầu.
      if (!book.complete) return { chapter, at: last.seconds };
    }
  }
  const unheard = playable.find((chapter) => !book.state.chapters[String(chapter.id)]?.done);
  return { chapter: unheard ?? playable[0], at: 0 };
}

export function chapterHeard(state: ListeningState, chapter: ListenChapter): number {
  const record = state.chapters[String(chapter.id)];
  if (!record) return 0;
  if (record.done) return 1;
  return chapter.duration > 0 ? Math.min(1, record.heard / chapter.duration) : 0;
}

/** Tìm không dấu: "tap 16" khớp "Tập 16", "duc tri" khớp "Đức Trí". */
export function foldVietnamese(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase();
}
