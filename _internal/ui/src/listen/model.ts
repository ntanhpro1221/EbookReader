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
  updatedAt?: number;
}

export interface BookProgress {
  heardSeconds: number;
  totalSeconds: number;
  fraction: number;
  chaptersDone: number;
  finished: boolean;
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
  updatedAt: number | null;
  state: ListeningState;
  progress: BookProgress;
  chapters?: ListenChapter[];
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
