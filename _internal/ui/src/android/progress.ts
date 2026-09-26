import type { BookProgress, ListenChapter, ListeningState } from "@/listen/model";

/** Đã nghe bao nhiêu phần của cuốn - cùng phép tính với máy tính (ebook_reader/webui/listening.py). */
export function bookProgress(state: ListeningState, chapters: ListenChapter[]): BookProgress {
  const total = chapters.reduce((sum, chapter) => sum + chapter.duration, 0);
  let heard = 0;
  let done = 0;
  for (const chapter of chapters) {
    const record = state.chapters[String(chapter.id)];
    if (!record) continue;
    if (record.done) {
      heard += chapter.duration;
      done += 1;
    } else {
      heard += Math.min(chapter.duration, record.heard || 0);
    }
  }
  return {
    heardSeconds: heard,
    totalSeconds: total,
    fraction: total ? heard / total : 0,
    chaptersDone: done,
    finished: Boolean(state.finished) || (chapters.length > 0 && done === chapters.length),
  };
}
