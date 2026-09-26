import { Capacitor } from "@capacitor/core";
import type { Cast, ListenBook, ListeningState, Script } from "@/listen/model";
import { bookProgress } from "./progress";
import type { ListenSource } from "@/listen/source";
import { EbookLibrary, EbookPlayer, type LocalBook } from "./plugins";

// Phía Nghe trên Android: đọc sách đã tải về máy (EbookLibrary). Audio chương do lõi phát native mở thẳng từ
// file, nên audioUrl không dùng tới; câu mẫu nhân vật phát trong WebView qua đường dẫn file đã chuyển đổi.

let root = "";
export async function initAndroidSource(): Promise<void> {
  root = (await EbookLibrary.info()).root;
}

function fileUrl(bookId: string, relative: string): string {
  return Capacitor.convertFileSrc(`${root}/books/${bookId}/${relative}`);
}

function toListenBook(book: LocalBook, withChapters: boolean): ListenBook {
  const chapters = book.chapters.map((chapter) => ({
    id: chapter.id,
    index: chapter.index,
    title: chapter.title,
    subtitle: chapter.subtitle,
    fullTitle: chapter.fullTitle,
    duration: chapter.duration,
    available: chapter.available && Boolean(chapter.file),
  }));
  const state: ListeningState = { ...book.state, chapters: book.state?.chapters ?? {}, bookmarks: book.state?.bookmarks ?? [] };
  return {
    id: book.id,
    title: book.title,
    narrator: book.narrator,
    duration: chapters.filter((chapter) => chapter.available).reduce((sum, chapter) => sum + chapter.duration, 0),
    chaptersTotal: book.chaptersTotal,
    chaptersAvailable: chapters.filter((chapter) => chapter.available).length,
    complete: book.complete,
    // Trên điện thoại không biết máy tính còn đang làm hay không: chỉ biết cuốn này chưa đủ chương.
    producing: false,
    paused: !book.complete,
    updatedAt: state.updatedAt ?? null,
    state,
    progress: bookProgress(state, chapters.filter((chapter) => chapter.available), book.complete),
    lastChapterTitle: chapters.find((chapter) => chapter.id === state.last?.chapterId)?.fullTitle ?? "",
    chapters: withChapters ? chapters : undefined,
  };
}

/** Tên file của chương trong gói - lõi phát native cần nó. */
export const chapterFiles = new Map<string, Map<number, string>>();

export const androidSource: ListenSource = {
  kind: "android",
  async library() {
    const { books } = await EbookLibrary.localBooks();
    return books.map((book) => toListenBook(book, false));
  },
  async book(id) {
    const book = await EbookLibrary.book({ id });
    chapterFiles.set(id, new Map(book.chapters.filter((chapter) => chapter.file).map((chapter) => [chapter.id, chapter.file!])));
    return toListenBook(book, true);
  },
  async script(bookId, chapterId) {
    const { text } = await EbookLibrary.readText({ id: bookId, path: `scripts/${chapterId}.json` });
    return JSON.parse(text) as Script;
  },
  async cast(bookId) {
    const { text } = await EbookLibrary.readText({ id: bookId, path: "cast.json" });
    return JSON.parse(text) as Cast;
  },
  audioUrl: (bookId, chapterId) => fileUrl(bookId, chapterFiles.get(bookId)?.get(chapterId) ?? ""),
  sampleUrl: (bookId, sampleId) => fileUrl(bookId, `samples/${sampleId}.wav`),
  voiceUrl: () => "",
  saveProgress: (id, chapterId, seconds, duration) => EbookLibrary.progress({ id, chapterId, seconds, duration }),
  setChapterDone: (id, chapterId, done) => EbookLibrary.setChapterDone({ id, chapterId, done }),
  setFinished: (id, finished) => EbookLibrary.setFinished({ id, finished }),
  setRate: (id, rate) => EbookLibrary.setRate({ id, rate }),
  addBookmark: (id, chapterId, seconds, note) => EbookLibrary.addBookmark({ id, chapterId, seconds, note }),
  updateBookmark: (id, markId, note) => EbookLibrary.updateBookmark({ id, markId, note }),
  deleteBookmark: (id, markId) => EbookLibrary.deleteBookmark({ id, markId }),
  restoreBookmark: async (id, mark) => {
    await EbookLibrary.addBookmark({ id, chapterId: mark.chapterId, seconds: mark.seconds, note: mark.note });
  },
  async lastNight() {
    const { session } = await EbookPlayer.lastNight();
    return session?.bookId ? { bookId: session.bookId, night: session } : null;
  },
  dismissNight: () => EbookPlayer.dismissLastNight(),
};
