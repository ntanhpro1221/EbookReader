import { FolderOpen, Plus, Wand2 } from "lucide-react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { BookCover } from "@/shared/BookCover";
import { cn } from "@/shared/cn";
import { formatEta, formatPercent, formatRelative } from "@/shared/format";
import { Button, EmptyState, Progress, Skeleton, StatusPill } from "@/shared/ui";
import type { BookSummary } from "./api";
import { phaseTone, pickFolder, useAppInfo, useLibrary, useOpenBook } from "./data";

// Studio: nơi làm sách. Danh sách là bảng công việc - trạng thái sản xuất, tiến độ, thời gian còn lại - chứ không
// phải kệ sách (kệ sách là của phía Nghe).

function ProjectRow({ book }: { book: BookSummary }) {
  const navigate = useNavigate();
  const live = book.running || book.starting;
  if (book.broken) {
    return (
      <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 rounded-xl border border-dashed border-line px-4 py-3 text-sm">
        <span className="truncate font-medium">{book.title}</span>
        <span className="text-xs text-danger">Không đọc được: {book.broken}</span>
      </div>
    );
  }
  const detail =
    book.phase === "done"
      ? `${book.chapters.completed}/${book.chapters.total} chương`
      : book.eta && live
        ? formatEta(book.eta.seconds)
        : `${book.chapters.completed}/${book.chapters.total} chương xong`;
  return (
    <button
      type="button"
      onClick={() => navigate(`/studio/${book.id}`)}
      className="grid w-full grid-cols-[48px_minmax(0,1fr)_170px_200px_110px] items-center gap-4 rounded-xl px-3 py-2.5 text-left transition-colors hover:bg-hover"
    >
      <BookCover title={book.title} size="sm" className="size-12" />
      <div className="min-w-0">
        <div className="truncate font-semibold">{book.title}</div>
        <div className="truncate text-xs text-fg-2">
          {book.settings.narrator ? `Giọng kể ${book.settings.narrator} · ` : ""}
          {book.settings.profileLabel}
        </div>
      </div>
      <div>
        <StatusPill label={book.starting ? "Đang khởi động" : book.statusLabel} tone={phaseTone(book.phase, live)} live={live} />
      </div>
      <div>
        {book.phase === "done" ? (
          <span className="text-xs text-fg-2">{detail}</span>
        ) : (
          <>
            <div className="flex items-center gap-2">
              <Progress value={book.progress.overall} running={live} tone={live ? "accent" : "muted"} size="sm" />
              <span className="tabular w-9 text-right text-xs font-semibold">{formatPercent(book.progress.overall)}</span>
            </div>
            <div className="mt-1 text-[11px] text-fg-3">{detail}</div>
          </>
        )}
      </div>
      <div className={cn("tabular text-right text-xs", live ? "text-accent-text" : "text-fg-3")}>
        {live ? "đang chạy" : formatRelative(book.updatedAt)}
      </div>
    </button>
  );
}

export function ProjectsScreen() {
  const { data, isLoading } = useLibrary();
  const { data: info } = useAppInfo();
  const navigate = useNavigate();
  const open = useOpenBook();
  const books = data?.books ?? [];
  const live = books.filter((book) => book.running || book.starting);
  const others = books.filter((book) => !(book.running || book.starting));

  const openExisting = async () => {
    try {
      const path = await pickFolder("Chọn thư mục một cuốn sách đã tạo");
      if (!path) return;
      const result = await open.mutateAsync(path);
      navigate(`/studio/${result.id}`);
    } catch (error) {
      toast.error("Không mở được sách", { description: (error as Error).message });
    }
  };

  return (
    <div className="mx-auto max-w-[1180px] px-10 pb-16 pt-9">
      <header className="flex items-end justify-between gap-6">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wider text-accent-text">Studio</div>
          <h1 className="mt-1 text-[28px] font-bold tracking-tight">Dự án sách nói</h1>
          <p className="mt-1 text-sm text-fg-2">
            {books.length ? `${books.length} dự án` : "Chưa có dự án"}
            {data?.root ? <span className="text-fg-3"> · {data.root}</span> : null}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {info?.dialogs && (
            <Button variant="ghost" icon={FolderOpen} onClick={() => void openExisting()}>
              Mở dự án có sẵn
            </Button>
          )}
          <Button variant="primary" icon={Plus} onClick={() => navigate("/studio/new")}>
            Dự án mới
          </Button>
        </div>
      </header>

      {isLoading ? (
        <div className="mt-8 space-y-2">
          {Array.from({ length: 4 }, (_, index) => (
            <Skeleton key={index} className="h-16 rounded-xl" />
          ))}
        </div>
      ) : !books.length ? (
        <EmptyState
          icon={Wand2}
          title="Biến truyện chữ thành sách nói"
          className="mt-12 rounded-2xl border border-dashed border-line"
          action={
            <Button variant="primary" size="lg" icon={Plus} onClick={() => navigate("/studio/new")}>
              Tạo dự án đầu tiên
            </Button>
          }
        >
          Chọn thư mục chứa các chương TXT. Ebook Reader đọc cả truyện, nhận ra từng nhân vật, trao cho mỗi người một
          giọng riêng rồi thu thành MP3 theo chương.
        </EmptyState>
      ) : (
        <>
          {live.length > 0 && (
            <section className="mt-8">
              <h2 className="mb-2 px-3 text-xs font-semibold uppercase tracking-wider text-fg-3">Đang chạy</h2>
              <div className="rounded-2xl border border-accent/30 bg-panel p-1.5">
                {live.map((book) => (
                  <ProjectRow key={book.id} book={book} />
                ))}
              </div>
            </section>
          )}
          <section className="mt-8">
            <div className="grid grid-cols-[48px_minmax(0,1fr)_170px_200px_110px] gap-4 border-b border-line px-3 pb-2 text-[11px] font-semibold uppercase tracking-wider text-fg-3">
              <span />
              <span>Dự án</span>
              <span>Trạng thái</span>
              <span>Tiến độ</span>
              <span className="text-right">Cập nhật</span>
            </div>
            <div className="mt-1.5 space-y-0.5">
              {others.map((book) => (
                <ProjectRow key={book.id} book={book} />
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
