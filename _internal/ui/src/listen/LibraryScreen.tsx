import { Headphones, Play, Search } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router";
import { BookCover } from "@/shared/BookCover";
import { cn } from "@/shared/cn";
import { formatLength, formatRelative } from "@/shared/format";
import { EmptyState, Progress, Segmented, Skeleton } from "@/shared/ui";
import { resumePoint, type ListenBook } from "./model";
import { usePlayer } from "./player";
import { useListenLibrary, useSource } from "./source";

type Filter = "all" | "listening" | "new" | "finished";

function stateOf(book: ListenBook): Filter {
  if (book.progress.finished) return "finished";
  if (book.progress.heardSeconds > 0 || book.state.last) return "listening";
  return "new";
}

function leftText(book: ListenBook): string {
  if (book.progress.finished) return "Đã nghe xong";
  const left = Math.max(0, book.duration - book.progress.heardSeconds);
  if (book.progress.heardSeconds <= 0) return formatLength(book.duration);
  return `Còn ${formatLength(left)}`;
}

export function usePlayListenBook() {
  const source = useSource();
  const player = usePlayer();
  return async (book: ListenBook, chapterId?: number, at?: number) => {
    const full = book.chapters ? book : await source.book(book.id);
    const chapters = full.chapters ?? [];
    if (chapterId !== undefined) {
      player.play(full, chapters, chapterId, at ?? 0);
      return;
    }
    const point = resumePoint(full, chapters);
    if (point) player.play(full, chapters, point.chapter.id, point.at);
  };
}

function BookTile({ book }: { book: ListenBook }) {
  const navigate = useNavigate();
  const playBook = usePlayListenBook();
  const player = usePlayer();
  const current = player.track?.bookId === book.id;
  return (
    <div className="group">
      <div className="relative">
        <button type="button" onClick={() => navigate(`/book/${book.id}`)} className="block w-full rounded-lg" aria-label={`Mở ${book.title}`}>
          <BookCover title={book.title} size="md" className="w-full" />
        </button>
        <button
          type="button"
          aria-label={`Nghe ${book.title}`}
          onClick={() => void playBook(book)}
          className="absolute bottom-2.5 right-2.5 grid size-10 place-items-center rounded-full bg-accent text-accent-ink opacity-0 shadow-float transition-opacity duration-150 group-hover:opacity-100 focus-visible:opacity-100 max-md:opacity-100"
        >
          <Play className="size-4 translate-x-[1px]" fill="currentColor" strokeWidth={0} />
        </button>
        {book.progress.fraction > 0 && !book.progress.finished && (
          <div className="absolute inset-x-0 bottom-0 h-1 overflow-hidden rounded-b-lg bg-black/40">
            <div className="h-full bg-accent" style={{ width: `${book.progress.fraction * 100}%` }} />
          </div>
        )}
      </div>
      <button type="button" onClick={() => navigate(`/book/${book.id}`)} className="mt-2.5 block w-full text-left">
        <div className={cn("line-clamp-2 text-sm font-semibold leading-snug", current && "text-accent-text")}>{book.title}</div>
        <div className="mt-1 text-xs text-fg-2">
          {book.producing ? `Đang làm · ${book.chaptersAvailable}/${book.chaptersTotal} chương` : leftText(book)}
        </div>
      </button>
    </div>
  );
}

function ContinueCard({ book }: { book: ListenBook }) {
  const navigate = useNavigate();
  const playBook = usePlayListenBook();
  return (
    <section className="flex items-center gap-4 rounded-2xl border border-line bg-panel p-4 shadow-card sm:gap-5 sm:p-5">
      <button type="button" onClick={() => navigate(`/book/${book.id}`)} aria-label={`Mở ${book.title}`}>
        <BookCover title={book.title} size="md" className="w-20 sm:w-28" />
      </button>
      <div className="min-w-0 flex-1">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-accent-text">Đang nghe dở</div>
        <h2 className="mt-1 line-clamp-2 text-base font-semibold sm:text-lg">{book.title}</h2>
        <p className="mt-0.5 text-sm text-fg-2">
          {leftText(book)}
          {book.state.last ? ` · ${formatRelative(book.state.last.at)}` : ""}
        </p>
        <Progress value={book.progress.fraction} size="xs" className="mt-3 max-w-md" />
      </div>
      <button
        type="button"
        onClick={() => void playBook(book)}
        aria-label="Nghe tiếp"
        className="grid size-14 shrink-0 place-items-center rounded-full bg-accent text-accent-ink shadow-card transition-transform hover:scale-105"
      >
        <Play className="size-6 translate-x-[1px]" fill="currentColor" strokeWidth={0} />
      </button>
    </section>
  );
}

export function LibraryScreen({ empty, header }: { empty?: ReactNode; header?: ReactNode }) {
  const { data: books, isLoading } = useListenLibrary();
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const listening = useMemo(
    () => (books ?? []).filter((book) => book.state.last && !book.progress.finished)
      .sort((a, b) => (b.state.last?.at ?? 0) - (a.state.last?.at ?? 0))[0],
    [books],
  );
  const shown = (books ?? []).filter(
    (book) => (filter === "all" || stateOf(book) === filter) && (!query || book.title.toLowerCase().includes(query.toLowerCase())),
  );
  return (
    <div className="mx-auto max-w-[1180px] px-4 pb-16 pt-6 sm:px-10 sm:pt-9">
      <header className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight sm:text-[28px]">Thư viện</h1>
          <p className="mt-1 text-sm text-fg-2">{books?.length ? `${books.length} cuốn` : ""}</p>
        </div>
        {header}
      </header>
      {isLoading ? (
        <div className="mt-8 grid grid-cols-2 gap-x-4 gap-y-7 sm:grid-cols-[repeat(auto-fill,minmax(160px,1fr))] sm:gap-x-6">
          {Array.from({ length: 6 }, (_, index) => (
            <div key={index}>
              <Skeleton className="aspect-square w-full rounded-lg" />
              <Skeleton className="mt-3 h-4 w-3/4" />
            </div>
          ))}
        </div>
      ) : !books?.length ? (
        empty ?? (
          <EmptyState icon={Headphones} title="Chưa có sách nào" className="mt-12">
            Sách nghe được sẽ hiện ở đây.
          </EmptyState>
        )
      ) : (
        <>
          {listening && (
            <div className="mt-6">
              <ContinueCard book={listening} />
            </div>
          )}
          <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
            <Segmented<Filter>
              label="Lọc sách"
              value={filter}
              onChange={setFilter}
              options={[
                { value: "all", label: "Tất cả" },
                { value: "listening", label: "Đang nghe" },
                { value: "new", label: "Chưa nghe" },
                { value: "finished", label: "Đã xong" },
              ]}
            />
            <label className="relative max-sm:w-full">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-fg-3" />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Tìm sách"
                className="h-9 w-full rounded-lg border border-line bg-panel pl-9 pr-3 text-sm outline-none placeholder:text-fg-3 focus:border-accent sm:w-60"
              />
            </label>
          </div>
          {shown.length ? (
            <div className="mt-6 grid grid-cols-2 gap-x-4 gap-y-7 sm:grid-cols-[repeat(auto-fill,minmax(160px,1fr))] sm:gap-x-6">
              {shown.map((book) => (
                <BookTile key={book.id} book={book} />
              ))}
            </div>
          ) : (
            <EmptyState icon={Search} title="Không có sách khớp" className="mt-4">
              Thử bộ lọc khác hoặc gõ tên khác.
            </EmptyState>
          )}
        </>
      )}
    </div>
  );
}
