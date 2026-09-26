import type { Bookmark, Cast, ListenBook, ListeningSession, ListeningState, NightSession, Script } from "@/listen/model";
import type { ListenSource } from "@/listen/source";
import { api, mediaUrl } from "@/studio/api";

/** Phía Nghe trên máy tính: đọc từ server cục bộ (ebook_reader/webui). */
export const httpSource: ListenSource = {
  kind: "desktop",
  library: () => api<ListenBook[]>("/api/listen/library"),
  book: (id) => api<ListenBook>(`/api/listen/books/${id}`),
  script: (bookId, chapterId) => api<Script>(`/api/books/${bookId}/chapters/${chapterId}/script`),
  cast: (bookId) => api<Cast>(`/api/books/${bookId}/cast`),
  audioUrl: (bookId, chapterId) => mediaUrl(`/media/books/${bookId}/chapters/${chapterId}`),
  sampleUrl: (bookId, sampleId) => mediaUrl(`/media/books/${bookId}/samples/${sampleId}`),
  voiceUrl: (name) => mediaUrl(`/media/voices/${encodeURIComponent(name)}`),
  saveProgress: (bookId, chapterId, seconds, duration) =>
    api<ListeningState>(`/api/listen/books/${bookId}/progress`, { method: "POST", body: { chapterId, seconds, duration } }),
  setChapterDone: (bookId, chapterId, done) =>
    api<ListeningState>(`/api/listen/books/${bookId}/chapters/${chapterId}/done`, { method: "POST", body: { done } }),
  setFinished: (bookId, finished) =>
    api<ListeningState>(`/api/listen/books/${bookId}/finished`, { method: "POST", body: { finished } }),
  setRate: async (bookId, rate) => {
    await api(`/api/listen/books/${bookId}/rate`, { method: "POST", body: { rate } });
  },
  addBookmark: (bookId, chapterId, seconds, note) =>
    api<Bookmark>(`/api/listen/books/${bookId}/bookmarks`, { method: "POST", body: { chapterId, seconds, note } }),
  updateBookmark: async (bookId, id, note) => {
    await api(`/api/listen/books/${bookId}/bookmarks/${id}`, { method: "PUT", body: { note } });
  },
  deleteBookmark: async (bookId, id) => {
    await api(`/api/listen/books/${bookId}/bookmarks/${id}`, { method: "DELETE" });
  },
  restoreBookmark: async (bookId, mark) => {
    await api(`/api/listen/books/${bookId}/bookmarks/restore`, { method: "POST", body: mark });
  },
  lastNight: () => api<{ bookId: string; night: NightSession } | null>("/api/listen/night"),
  dismissNight: async (bookId, id) => {
    await api("/api/listen/night/dismiss", { method: "POST", body: { bookId, id } });
  },
  sessions: (bookId) => api<ListeningSession[]>(`/api/listen/books/${bookId}/sessions`),
  addSession: async (bookId, session) => {
    await api(`/api/listen/books/${bookId}/sessions`, { method: "POST", body: session });
  },
  saveReading: async (bookId, chapterId, index) => {
    await api(`/api/listen/books/${bookId}/reading`, { method: "POST", body: { chapterId, index } });
  },
  saveNight: async (bookId, night) => {
    await api(`/api/listen/books/${bookId}/night`, { method: "POST", body: night });
  },
};
