import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  api,
  type ActivityItem,
  type AppInfo,
  type BookSummary,
  type Cast,
  type Chapter,
  type Preferences,
  type ScanResult,
  type Script,
  type Voice,
} from "./api";
import type { Phase } from "./api";
import type { Tone } from "@/shared/ui";

export function phaseTone(phase: Phase, running: boolean): Tone {
  if (phase === "done") return "success";
  if (phase === "error") return "danger";
  if (running) return "accent";
  return "muted";
}

// Nhịp hỏi server: sách đang chạy thì 2 giây (thanh tiến độ phải sống), không thì thưa hẳn.
const LIVE_MS = 2000;
const IDLE_MS = 15000;

export function useAppInfo() {
  return useQuery({ queryKey: ["app"], queryFn: () => api<AppInfo>("/api/app"), staleTime: Infinity });
}

export function useLibrary() {
  return useQuery({
    queryKey: ["library"],
    queryFn: () => api<{ root: string; books: BookSummary[] }>("/api/library"),
    refetchInterval: (query) =>
      query.state.data?.books.some((book) => book.running || book.starting) ? LIVE_MS * 2 : IDLE_MS,
  });
}

export function useBook(id: string | undefined) {
  return useQuery({
    queryKey: ["book", id],
    enabled: Boolean(id),
    queryFn: () => api<{ book: BookSummary; chapters: Chapter[] }>(`/api/books/${id}`),
    refetchInterval: (query) => (query.state.data?.book.running || query.state.data?.book.starting ? LIVE_MS : IDLE_MS),
  });
}

export function useCast(id: string | undefined, live: boolean) {
  return useQuery({
    queryKey: ["cast", id],
    enabled: Boolean(id),
    queryFn: () => api<Cast>(`/api/books/${id}/cast`),
    refetchInterval: live ? 20000 : false,
  });
}

export function useActivity(id: string | undefined, technical: boolean, live: boolean) {
  return useQuery({
    queryKey: ["activity", id, technical],
    enabled: Boolean(id),
    queryFn: () => api<ActivityItem[]>(`/api/books/${id}/activity${technical ? "?technical=1" : ""}`),
    refetchInterval: live ? 5000 : false,
  });
}

export function useScript(bookId: string | undefined, chapterId: number | undefined) {
  return useQuery({
    queryKey: ["script", bookId, chapterId],
    enabled: Boolean(bookId && chapterId),
    queryFn: () => api<Script>(`/api/books/${bookId}/chapters/${chapterId}/script`),
    staleTime: Infinity,
  });
}

export function useVoices() {
  return useQuery({ queryKey: ["voices"], queryFn: () => api<Voice[]>("/api/voices"), staleTime: Infinity });
}

function useRefresh() {
  const client = useQueryClient();
  return (id?: string) => {
    void client.invalidateQueries({ queryKey: ["library"] });
    if (id) void client.invalidateQueries({ queryKey: ["book", id] });
  };
}

export function useStart() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (id: string) => api<BookSummary>(`/api/books/${id}/start`, { method: "POST" }),
    onSuccess: (_book, id) => {
      refresh(id);
      toast.success("Đang khởi động", { description: "Sách chạy nền - đóng cửa sổ cũng không dừng." });
    },
    onError: (error: Error) => toast.error("Không bắt đầu được", { description: error.message }),
  });
}

export function useStop() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (id: string) => api<BookSummary>(`/api/books/${id}/stop`, { method: "POST" }),
    onSuccess: (_book, id) => {
      refresh(id);
      toast("Đang dừng", { description: "Sách sẽ dừng ở câu đang làm dở; mọi thứ đã xong được giữ nguyên." });
    },
    onError: (error: Error) => toast.error("Không dừng được", { description: error.message }),
  });
}

export function useReveal() {
  return useMutation({
    mutationFn: (id: string) => api(`/api/books/${id}/reveal`, { method: "POST" }),
    onError: (error: Error) => toast.error("Không mở được thư mục", { description: error.message }),
  });
}

export function useScan() {
  return useMutation({
    mutationFn: (paths: string[]) => api<ScanResult>("/api/scan", { method: "POST", body: { paths } }),
  });
}

export function useCreateBook() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (body: { paths: string[]; title: string; profile: string; narrator: string; start: boolean }) =>
      api<{ id: string }>("/api/books", { method: "POST", body }),
    onSuccess: () => refresh(),
  });
}

export function useOpenBook() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (path: string) => api<{ id: string }>("/api/books/open", { method: "POST", body: { path } }),
    onSuccess: () => refresh(),
  });
}

export function usePreferences() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["preferences"], queryFn: () => api<Preferences>("/api/preferences") });
  const mutation = useMutation({
    mutationFn: (changes: Partial<Preferences>) => api<Preferences>("/api/preferences", { method: "PUT", body: changes }),
    onSuccess: (data) => {
      client.setQueryData(["preferences"], data);
      void client.invalidateQueries({ queryKey: ["library"] });
    },
  });
  return { ...query, update: mutation.mutate, updating: mutation.isPending };
}

export async function pickFolder(title: string, start = ""): Promise<string | null> {
  const result = await api<{ path: string | null }>("/api/dialog/folder", { method: "POST", body: { title, start } });
  return result.path;
}

export async function pickFiles(title: string, start = ""): Promise<string[]> {
  const result = await api<{ paths: string[] }>("/api/dialog/files", { method: "POST", body: { title, start } });
  return result.paths;
}
