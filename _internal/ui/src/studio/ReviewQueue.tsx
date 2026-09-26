import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Ear, Loader2, Play, RotateCcw, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useClip } from "@/listen/clip";
import { cn } from "@/shared/cn";
import { formatPercent } from "@/shared/format";
import { EmptyState, Segmented, Vu } from "@/shared/ui";
import { api, urls } from "./api";

// "Cần nghe lại": câu mà khâu tự kiểm tra không chắc (webui/reviews.py). Nghe từng câu, bấm Ổn hoặc Cần thu lại -
// các chương có câu "cần thu lại" gom thành danh sách đúc lại cho ranh giới lô kế tiếp.

type Kind = "failed" | "unverified" | "name-low" | "name";

interface ReviewItem {
  segmentId: number;
  stableId: string;
  chapterId: number;
  chapterTitle: string;
  text: string;
  heard: string;
  similarity: number | null;
  speaker: string;
  kind: Kind;
  reason: string;
  playable: boolean;
  verdict: "ok" | "redo" | null;
}

interface ReviewView {
  counts: Record<Kind, number>;
  pending: number;
  redoChapters: number[];
  items: ReviewItem[];
}

const KIND_LABEL: Record<Kind, string> = {
  failed: "Hỏng",
  unverified: "Chưa kiểm được",
  "name-low": "Tên riêng lệch nhiều",
  name: "Tên riêng lệch ít",
};

const KIND_TONE: Record<Kind, string> = {
  failed: "bg-danger-soft text-danger",
  unverified: "bg-warning-soft text-warning",
  "name-low": "bg-info-soft text-info",
  name: "bg-hover text-fg-2",
};

export function useReviewCount(bookId: string) {
  const { data } = useQuery({
    queryKey: ["review", bookId, false],
    queryFn: () => api<ReviewView>(`/api/books/${bookId}/review`),
    enabled: Boolean(bookId),
    staleTime: 30_000,
  });
  return data?.pending ?? 0;
}

function Row({ bookId, item, onVerdict }: { bookId: string; item: ReviewItem; onVerdict: (verdict: ReviewItem["verdict"]) => void }) {
  const clip = useClip();
  const id = `review-${item.segmentId}`;
  const playing = clip.current === id;
  return (
    <li className={cn("grid grid-cols-[40px_minmax(0,1fr)_auto] items-start gap-3 rounded-xl px-3 py-3", item.verdict ? "opacity-70" : "hover:bg-hover")}>
      <button
        type="button"
        disabled={!item.playable}
        aria-label={playing ? "Dừng" : `Nghe câu: ${item.text}`}
        onClick={() => clip.toggle(id, urls.sample(bookId, item.segmentId))}
        className={cn(
          "grid size-10 place-items-center rounded-full transition-colors disabled:opacity-40",
          playing ? "bg-accent text-accent-ink" : "bg-hover text-fg hover:bg-line",
        )}
      >
        {playing && clip.loading ? <Loader2 className="size-4 animate-spin" /> : playing ? <Vu className="h-3" /> : <Play className="size-4 translate-x-[1px]" fill="currentColor" strokeWidth={0} />}
      </button>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className={cn("rounded-md px-1.5 py-0.5 font-semibold", KIND_TONE[item.kind])}>{KIND_LABEL[item.kind]}</span>
          <span className="text-fg-2">{item.chapterTitle}</span>
          {item.speaker && <span className="text-fg-2">· {item.speaker}</span>}
          {item.similarity !== null && <span className="tabular text-fg-2">· khớp {formatPercent(item.similarity)}</span>}
        </div>
        <p className="mt-1 text-[15px] leading-snug">{item.text}</p>
        {item.heard && (
          <p className="mt-1 text-[13px] leading-snug text-fg-2">
            <Ear className="mr-1 inline size-3.5 -translate-y-px" />
            Máy nghe ra: “{item.heard}”
          </p>
        )}
        <p className="mt-1 text-xs text-fg-2">{item.reason}</p>
      </div>
      <div className="flex gap-1.5">
        <button
          type="button"
          aria-pressed={item.verdict === "ok"}
          onClick={() => onVerdict(item.verdict === "ok" ? null : "ok")}
          className={cn(
            "inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-sm font-medium",
            item.verdict === "ok" ? "bg-success-soft text-success" : "border border-line hover:bg-hover",
          )}
        >
          <Check className="size-4" /> Ổn
        </button>
        <button
          type="button"
          aria-pressed={item.verdict === "redo"}
          onClick={() => onVerdict(item.verdict === "redo" ? null : "redo")}
          className={cn(
            "inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-sm font-medium",
            item.verdict === "redo" ? "bg-danger-soft text-danger" : "border border-line hover:bg-hover",
          )}
        >
          <RotateCcw className="size-4" /> Cần thu lại
        </button>
      </div>
    </li>
  );
}

export function ReviewQueue({ bookId }: { bookId: string }) {
  const client = useQueryClient();
  const [showMinor, setShowMinor] = useState(false);
  const [filter, setFilter] = useState<"todo" | "done">("todo");
  const { data, isLoading } = useQuery({
    queryKey: ["review", bookId, showMinor],
    queryFn: () => api<ReviewView>(`/api/books/${bookId}/review${showMinor ? "?all=1" : ""}`),
  });
  const verdict = useMutation({
    mutationFn: (body: { stableId: string; chapterId: number; verdict: ReviewItem["verdict"] }) =>
      api(`/api/books/${bookId}/review`, { method: "POST", body }),
    onMutate: async (body) => {
      // Cập nhật ngay trên màn hình; hỏi lại máy chủ sau.
      const key = ["review", bookId, showMinor];
      const previous = client.getQueryData<ReviewView>(key);
      if (previous) {
        client.setQueryData<ReviewView>(key, {
          ...previous,
          items: previous.items.map((item) => (item.stableId === body.stableId ? { ...item, verdict: body.verdict } : item)),
        });
      }
    },
    onSettled: () => void client.invalidateQueries({ queryKey: ["review", bookId] }),
  });

  if (isLoading || !data) return <div className="mt-6 text-sm text-fg-2">Đang tìm các câu cần nghe lại…</div>;
  const items = data.items.filter((item) => (filter === "todo" ? !item.verdict : Boolean(item.verdict)));
  const minor = data.counts.name;
  return (
    <div className="mt-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-fg-2 text-pretty">
          {data.pending ? (
            <>
              Còn <span className="font-semibold text-fg">{data.pending} câu</span> máy tự kiểm không chắc - nghe bằng tai rồi bấm Ổn hoặc
              Cần thu lại.
            </>
          ) : (
            "Đã xem hết các câu đáng lo."
          )}
        </p>
        <Segmented<"todo" | "done">
          label="Lọc"
          value={filter}
          onChange={setFilter}
          options={[
            { value: "todo", label: "Chưa xem" },
            { value: "done", label: "Đã xem" },
          ]}
        />
      </div>
      {data.redoChapters.length > 0 && (
        <p className="mt-3 rounded-xl bg-danger-soft px-4 py-2.5 text-sm text-danger">
          Chương cần thu lại: {data.redoChapters.length} chương - sẽ được đúc lại ở lần sản xuất kế tiếp.
        </p>
      )}
      {items.length ? (
        <ul className="mt-3 space-y-1">
          {items.map((item) => (
            <Row
              key={item.stableId}
              bookId={bookId}
              item={item}
              onVerdict={(value) => verdict.mutate({ stableId: item.stableId, chapterId: item.chapterId, verdict: value })}
            />
          ))}
        </ul>
      ) : (
        <EmptyState icon={ShieldCheck} title={filter === "todo" ? "Không còn câu nào cần xem" : "Chưa đánh dấu câu nào"} className="mt-4">
          {filter === "todo" ? "Mọi câu đáng lo đều đã có phán quyết." : "Nghe một câu rồi bấm Ổn hoặc Cần thu lại."}
        </EmptyState>
      )}
      {minor > 0 && (
        <button type="button" onClick={() => setShowMinor((value) => !value)} className="mt-4 text-sm font-medium text-fg-2 hover:text-fg">
          {showMinor ? "Ẩn" : "Hiện"} {minor} câu tên riêng lệch ít (thường vẫn ổn)
        </button>
      )}
    </div>
  );
}
