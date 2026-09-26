import { Headphones, Pause, Play, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { BookCover } from "@/shared/BookCover";
import { cn } from "@/shared/cn";
import { formatClock, formatLength, formatWhen } from "@/shared/format";
import { EmptyState, Progress, Segmented, Skeleton } from "@/shared/ui";
import { foldVietnamese, resumePoint, seriesOf, type ListenBook } from "./model";
import { usePlayer } from "./player";
import { useListenLibrary, useSource } from "./source";

type Filter = "all" | "listening" | "new" | "finished";

function stateOf(book: ListenBook): Filter {
  if (book.progress.finished) return "finished";
  if (book.progress.heardSeconds > 0 || book.state.last) return "listening";
  return "new";
}

/** Dòng trạng thái của một cuốn, cùng một bộ từ ở Thư viện, trang sách và thẻ nghe dở. */
export function bookStatusText(book: ListenBook): string {
  const chapters = `${book.chaptersAvailable}/${book.chaptersTotal} chương`;
  if (book.progress.finished) return "Đã nghe xong";
  if (book.progress.caughtUp) return `Đã nghe hết phần đã có · ${chapters}`;
  if (!book.complete) {
    const lead = book.producing ? "Đang thu âm" : "Chưa hoàn thành";
    return `${lead} · ${chapters}`;
  }
  const left = Math.max(0, book.duration - book.progress.heardSeconds);
  if (book.progress.heardSeconds <= 0) return formatLength(book.duration);
  return `Còn ${formatLength(left)}`;
}

export function usePlayListenBook() {
  const source = useSource();
  const player = usePlayer();
  return async (book: ListenBook, chapterId?: number, at?: number) => {
    // Cuốn đang ở trình phát: tiếp tục đúng chỗ đang phát, không nạp lại (nạp lại là lùi về điểm lưu gần nhất).
    if (chapterId === undefined && player.track?.bookId === book.id) {
      player.resume();
      return;
    }
    const full = book.chapters ? book : await source.book(book.id);
    const chapters = full.chapters ?? [];
    if (chapterId !== undefined) {
      player.play(full, chapters, chapterId, at ?? 0);
      return;
    }
    if (full.progress.caughtUp) {
      toast("Đã nghe hết phần đã có", { description: "Chương tiếp theo sẽ nghe được khi Studio làm xong." });
      return;
    }
    const point = resumePoint(full, chapters);
    if (point) player.play(full, chapters, point.chapter.id, point.at);
  };
}

/** Mở lại app: thanh phát có sẵn cuốn đang nghe dở (đang dừng) - bấm Space là nghe tiếp, khỏi đi tìm. */
export function useRestoreLastListening() {
  const { data: books } = useListenLibrary();
  const player = usePlayer();
  const source = useSource();
  const tried = useRef(false);
  useEffect(() => {
    if (tried.current || !books || player.track) return;
    tried.current = true;
    const recent = books
      .filter((book) => book.state.last && !book.progress.finished)
      .sort((a, b) => (b.state.last?.at ?? 0) - (a.state.last?.at ?? 0))[0];
    if (!recent?.state.last || Date.now() / 1000 - recent.state.last.at > 30 * 86_400) return;
    void source
      .book(recent.id)
      .then((book) => {
        const point = resumePoint(book, book.chapters ?? []);
        if (point) player.prepare(book, book.chapters ?? [], point.chapter.id, point.at);
      })
      .catch(() => undefined);
  }, [books, player, source]);
}

function BookTile({ book }: { book: ListenBook }) {
  const navigate = useNavigate();
  const playBook = usePlayListenBook();
  const player = usePlayer();
  const current = player.track?.bookId === book.id;
  const playingHere = current && player.playing;
  return (
    <div className="group">
      <div className="relative">
        <button type="button" onClick={() => navigate(`/book/${book.id}`)} className="block w-full rounded-lg" aria-label={`Mở ${book.title}`}>
          <BookCover title={book.title} size="md" playing={playingHere} className="w-full" />
        </button>
        <button
          type="button"
          aria-label={playingHere ? `Tạm dừng ${book.title}` : `Nghe ${book.title}`}
          onClick={() => (current ? player.toggle() : void playBook(book))}
          className={cn(
            "absolute bottom-2.5 right-2.5 grid size-10 place-items-center rounded-full bg-accent text-accent-ink shadow-float transition-opacity duration-150 group-hover:opacity-100 focus-visible:opacity-100 max-md:opacity-100",
            current ? "opacity-100" : "opacity-0",
          )}
        >
          {playingHere ? (
            <Pause className="size-4" fill="currentColor" strokeWidth={0} />
          ) : (
            <Play className="size-4 translate-x-[1px]" fill="currentColor" strokeWidth={0} />
          )}
        </button>
        {book.progress.fraction > 0 && !book.progress.finished && (
          <div className="absolute inset-x-0 bottom-0 h-1 overflow-hidden rounded-b-lg bg-black/40">
            <div className="h-full bg-accent" style={{ width: `${book.progress.fraction * 100}%` }} />
          </div>
        )}
      </div>
      <button type="button" onClick={() => navigate(`/book/${book.id}`)} className="mt-2.5 block w-full text-left">
        <div className={cn("line-clamp-2 text-sm font-semibold leading-snug", current && "text-accent-text")}>{book.title}</div>
        <div className="mt-1 text-xs text-fg-2">{bookStatusText(book)}</div>
      </button>
    </div>
  );
}

function ContinueCard({ book }: { book: ListenBook }) {
  const navigate = useNavigate();
  const playBook = usePlayListenBook();
  const player = usePlayer();
  const current = player.track?.bookId === book.id;
  const playingHere = current && player.playing;
  const last = book.state.last;
  const chapter = (current ? player.track?.chapterTitle : undefined) || book.lastChapterTitle;
  const where = last ? `${chapter ? `${chapter} · ` : ""}${formatClock(last.seconds)}` : "";
  return (
    <section className="flex items-center gap-4 rounded-2xl border border-line bg-panel p-4 shadow-card sm:gap-5 sm:p-5">
      <button type="button" onClick={() => navigate(`/book/${book.id}`)} aria-label={`Mở ${book.title}`}>
        <BookCover title={book.title} size="md" playing={playingHere} className="w-20 sm:w-28" />
      </button>
      <div className="min-w-0 flex-1">
        <div className="text-xs font-semibold uppercase tracking-[0.08em] text-accent-text">Đang nghe dở</div>
        <h2 className="mt-1 line-clamp-2 text-base font-semibold sm:text-lg">{book.title}</h2>
        <p className="tabular mt-0.5 text-sm text-fg-2">
          {where}
          {last ? ` · nghe lần cuối ${formatWhen(last.at)}` : ""}
        </p>
        <p className="mt-0.5 text-sm text-fg-2">{bookStatusText(book)}</p>
        <Progress value={book.progress.fraction} size="xs" className="mt-3 max-w-md" label="Đã nghe" />
      </div>
      <button
        type="button"
        onClick={() => (current ? player.toggle() : void playBook(book))}
        aria-label={playingHere ? `Tạm dừng ${book.title}` : `Nghe tiếp ${book.title}${where ? `, ${where}` : ""}`}
        className="grid size-14 shrink-0 place-items-center rounded-full bg-accent text-accent-ink shadow-card transition-transform hover:scale-105"
      >
        {playingHere ? (
          <Pause className="size-6" fill="currentColor" strokeWidth={0} />
        ) : (
          <Play className="size-6 translate-x-[1px]" fill="currentColor" strokeWidth={0} />
        )}
      </button>
    </section>
  );
}

/** Tập kế tiếp của cùng bộ trong thư viện (nghe xong Tập 16 thì mời Tập 17). */
export function useNextVolume(bookId: string | undefined, title: string | undefined): ListenBook | null {
  const { data: books } = useListenLibrary();
  if (!bookId || !title || !books) return null;
  const { series, volume } = seriesOf(title);
  if (volume === null) return null;
  return (
    books
      .filter((book) => book.id !== bookId && book.chaptersAvailable > 0)
      .map((book) => ({ book, ...seriesOf(book.title) }))
      .filter((item) => item.series === series && item.volume !== null && item.volume > volume)
      .sort((a, b) => (a.volume ?? 0) - (b.volume ?? 0))[0]?.book ?? null
  );
}

function UpcomingCard({ book, onOpen }: { book: ListenBook; onOpen?: (book: ListenBook) => void }) {
  const eta = book.eta && book.eta.phase === "analysis" ? `chương đầu nghe được sau khoảng ${formatLength(book.eta.seconds + 600)}` : "đang chuẩn bị";
  return (
    <button
      type="button"
      onClick={() => onOpen?.(book)}
      disabled={!onOpen}
      className="flex items-center gap-3 rounded-xl border border-dashed border-line-strong bg-panel p-3 text-left hover:border-accent disabled:hover:border-line-strong"
    >
      <BookCover title={book.title} size="sm" className="size-12 opacity-80" />
      <span className="min-w-0">
        <span className="block truncate text-sm font-semibold">{book.title}</span>
        <span className="block text-xs text-fg-2">Đang làm · {eta}</span>
      </span>
    </button>
  );
}

function Shelf({ books }: { books: ListenBook[] }) {
  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-7 sm:grid-cols-[repeat(auto-fill,minmax(160px,1fr))] sm:gap-x-6">
      {books.map((book) => (
        <BookTile key={book.id} book={book} />
      ))}
    </div>
  );
}

/** Sách cùng bộ đứng cạnh nhau theo số tập; sách lẻ ở cuối. Chỉ gom khi không lọc, không tìm. */
function SeriesShelves({ books }: { books: ListenBook[] }) {
  const groups = new Map<string, { book: ListenBook; volume: number | null }[]>();
  for (const book of books) {
    const { series, volume } = seriesOf(book.title);
    const key = volume === null ? `\u0000${book.id}` : series;
    groups.set(key, [...(groups.get(key) ?? []), { book, volume }]);
  }
  const series = [...groups.entries()].filter(([key, items]) => !key.startsWith("\u0000") && items.length > 1);
  const singles = books.filter((book) => !series.some(([, items]) => items.some((item) => item.book.id === book.id)));
  return (
    <div className="mt-6 space-y-10">
      {series.map(([name, items]) => (
        <section key={name} aria-label={name}>
          <h2 className="mb-3 flex items-baseline gap-2 text-base font-semibold">
            {name} <span className="text-sm font-normal text-fg-2">· {items.length} tập</span>
          </h2>
          <Shelf books={items.sort((a, b) => (a.volume ?? 0) - (b.volume ?? 0)).map((item) => item.book)} />
        </section>
      ))}
      {singles.length > 0 && (
        <section aria-label="Sách lẻ">
          {series.length > 0 && <h2 className="mb-3 text-base font-semibold">Sách khác</h2>}
          <Shelf books={singles} />
        </section>
      )}
    </div>
  );
}

const EMPTY_TEXT: Record<Filter, string> = {
  all: "Thư viện chưa có sách nào.",
  listening: "Bạn chưa nghe dở cuốn nào - chọn một cuốn để bắt đầu.",
  new: "Cuốn nào cũng đã được nghe ít nhất một đoạn.",
  finished: "Chưa có cuốn nào nghe xong.",
};

export function LibraryScreen({
  empty,
  header,
  recap,
  onOpenUpcoming,
}: {
  empty?: ReactNode;
  header?: ReactNode;
  recap?: ReactNode;
  /** Máy tính: sách đang làm dở mà chưa có chương nào - mở Studio để xem tiến trình. */
  onOpenUpcoming?: (book: ListenBook) => void;
}) {
  const { data: allBooks, isLoading } = useListenLibrary();
  const books = useMemo(() => allBooks?.filter((book) => book.chaptersAvailable > 0), [allBooks]);
  const upcoming = useMemo(() => allBooks?.filter((book) => book.chaptersAvailable === 0) ?? [], [allBooks]);
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const listening = useMemo(
    () => (books ?? []).filter((book) => book.state.last && !book.progress.finished)
      .sort((a, b) => (b.state.last?.at ?? 0) - (a.state.last?.at ?? 0))[0],
    [books],
  );
  const folded = foldVietnamese(query.trim());
  const shown = (books ?? []).filter(
    (book) => (filter === "all" || stateOf(book) === filter) && (!folded || foldVietnamese(book.title).includes(folded)),
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
      {recap}
      {upcoming.length > 0 && (
        <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {upcoming.map((book) => (
            <UpcomingCard key={book.id} book={book} onOpen={onOpenUpcoming} />
          ))}
        </div>
      )}
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
        upcoming.length ? null : empty ?? (
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
                { value: "finished", label: "Nghe xong" },
              ]}
            />
            <label className="relative max-sm:w-full">
              <span className="sr-only">Tìm sách</span>
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-fg-3" />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Tìm sách (gõ không dấu cũng được)"
                className="h-9 w-full rounded-lg border border-line bg-panel pl-9 pr-3 text-sm outline-none placeholder:text-fg-3 focus:border-accent sm:w-72"
              />
            </label>
          </div>
          {shown.length ? (
            filter === "all" && !folded ? (
              <SeriesShelves books={shown} />
            ) : (
              <div className="mt-6">
                <Shelf books={shown} />
              </div>
            )
          ) : (
            <EmptyState icon={Search} title={query ? `Không có sách nào tên “${query}”` : "Không có sách ở đây"} className="mt-4">
              {query ? "Thử gõ một phần tên khác." : EMPTY_TEXT[filter]}
            </EmptyState>
          )}
        </>
      )}
    </div>
  );
}
