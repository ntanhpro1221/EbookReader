import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { ArrowLeft, AudioLines, BookOpenText, Check, CheckCheck, CircleDashed, Loader2, MoreHorizontal, Pause, Play, RotateCcw } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { BookCover } from "@/shared/BookCover";
import { cn } from "@/shared/cn";
import { formatClock, formatLength, formatNumber, formatRelative } from "@/shared/format";
import { Button, EmptyState, IconButton, Progress, Skeleton, Tabs, TabsContent, TabsList, TabsTrigger, Tooltip, Vu } from "@/shared/ui";
import { useClip } from "./clip";
import { usePlayListenBook } from "./LibraryScreen";
import { chapterHeard, resumePoint, type CastMember, type ListenBook, type ListenChapter } from "./model";
import { usePlayer } from "./player";
import { useCast, useListenBook, useListenMutations, useSource } from "./source";

function ChapterRow({ book, chapter }: { book: ListenBook; chapter: ListenChapter }) {
  const player = usePlayer();
  const playBook = usePlayListenBook();
  const mutations = useListenMutations(book.id);
  const current = player.track?.bookId === book.id && player.track.chapterId === chapter.id;
  const heard = chapterHeard(book.state, chapter);
  const done = heard >= 1;
  const onPlay = () => {
    if (!chapter.available) return;
    if (current) player.toggle();
    else void playBook(book, chapter.id, 0);
  };
  return (
    <div
      className={cn(
        "group flex items-center gap-3 rounded-xl px-2 py-2.5 sm:px-3",
        current ? "bg-accent-soft" : "hover:bg-hover",
        !chapter.available && "opacity-50",
      )}
    >
      <button
        type="button"
        onClick={onPlay}
        disabled={!chapter.available}
        aria-label={current && player.playing ? `Tạm dừng ${chapter.fullTitle}` : `Nghe ${chapter.fullTitle}`}
        className="grid size-9 shrink-0 place-items-center rounded-full text-fg-2 hover:bg-panel hover:text-fg disabled:hover:bg-transparent"
      >
        {current && player.playing ? (
          <Vu className="h-3 text-accent" />
        ) : done ? (
          <Check className="size-4 text-success" strokeWidth={3} />
        ) : (
          <Play className="size-4 translate-x-[1px]" fill="currentColor" strokeWidth={0} />
        )}
      </button>
      <button type="button" onClick={onPlay} disabled={!chapter.available} className="min-w-0 flex-1 text-left">
        <div className={cn("truncate text-sm font-medium", current && "text-accent-text", done && !current && "text-fg-2")}>
          {chapter.title}
        </div>
        {chapter.subtitle && <div className="truncate text-xs text-fg-2">{chapter.subtitle}</div>}
        {heard > 0 && heard < 1 && (
          <div className="mt-1.5 h-[3px] w-24 overflow-hidden rounded-full bg-line">
            <div className="h-full bg-accent" style={{ width: `${heard * 100}%` }} />
          </div>
        )}
      </button>
      <span className="tabular shrink-0 text-xs text-fg-3">{chapter.available ? formatLength(chapter.duration) : "đang làm"}</span>
      {chapter.available && (
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button type="button" aria-label={`Tuỳ chọn ${chapter.fullTitle}`} className="grid size-8 place-items-center rounded-md text-fg-3 opacity-0 hover:bg-panel hover:text-fg group-hover:opacity-100 focus-visible:opacity-100 data-[state=open]:opacity-100 max-md:opacity-100">
              <MoreHorizontal className="size-4" />
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content align="end" sideOffset={4} className="z-50 min-w-48 rounded-xl border border-line bg-panel p-1.5 shadow-float">
              <DropdownMenu.Item
                onSelect={() => mutations.chapterDone.mutate({ chapterId: chapter.id, done: !done })}
                className="flex h-9 cursor-default items-center gap-2 rounded-lg px-2 text-sm outline-none data-[highlighted]:bg-hover"
              >
                {done ? <CircleDashed className="size-4" /> : <CheckCheck className="size-4" />}
                {done ? "Đánh dấu chưa nghe" : "Đánh dấu đã nghe"}
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      )}
    </div>
  );
}

function BookmarksTab({ book }: { book: ListenBook }) {
  const playBook = usePlayListenBook();
  const mutations = useListenMutations(book.id);
  const marks = [...book.state.bookmarks].sort((a, b) => a.chapterId - b.chapterId || a.seconds - b.seconds);
  const titleOf = (chapterId: number) => book.chapters?.find((chapter) => chapter.id === chapterId)?.fullTitle ?? "";
  if (!marks.length) {
    return (
      <EmptyState icon={BookOpenText} title="Chưa có dấu trang" className="mt-2">
        Khi đang nghe, bấm biểu tượng dấu trang để đánh dấu đoạn muốn quay lại.
      </EmptyState>
    );
  }
  return (
    <div className="mt-3 divide-y divide-line">
      {marks.map((mark) => (
        <div key={mark.id} className="group flex items-center gap-3 py-3">
          <button
            type="button"
            onClick={() => void playBook(book, mark.chapterId, mark.seconds)}
            aria-label={`Nghe từ dấu trang ${formatClock(mark.seconds)}`}
            className="grid size-9 shrink-0 place-items-center rounded-full bg-hover text-fg hover:bg-line"
          >
            <Play className="size-4 translate-x-[1px]" fill="currentColor" strokeWidth={0} />
          </button>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium">{titleOf(mark.chapterId)}</div>
            <div className="tabular text-xs text-fg-2">
              {formatClock(mark.seconds)} · {formatRelative(mark.at)}
              {mark.note && <span className="text-fg"> · {mark.note}</span>}
            </div>
          </div>
          <Button size="sm" variant="ghost" onClick={() => mutations.deleteBookmark.mutate(mark.id)} className="opacity-0 group-hover:opacity-100 max-md:opacity-100">
            Xoá
          </Button>
        </div>
      ))}
    </div>
  );
}

function SampleButton({ id, url, label }: { id: string; url: string; label: string }) {
  const clip = useClip();
  const active = clip.current === id;
  return (
    <Tooltip label={active ? "Dừng" : label}>
      <button
        type="button"
        aria-label={active ? "Dừng nghe thử" : label}
        onClick={() => clip.toggle(id, url)}
        className={cn(
          "grid size-9 shrink-0 place-items-center rounded-full border transition-colors",
          active ? "border-accent bg-accent text-accent-ink" : "border-line text-fg-2 hover:border-line-strong hover:text-fg",
        )}
      >
        {active && clip.loading ? <Loader2 className="size-4 animate-spin" /> : active ? <Vu className="h-3" /> : <Play className="size-3.5 translate-x-[1px]" fill="currentColor" strokeWidth={0} />}
      </button>
    </Tooltip>
  );
}

function hueOf(text: string): number {
  let value = 0;
  for (const char of text) value = (value * 31 + char.charCodeAt(0)) % 360;
  return value;
}

export function PersonRow({ bookId, person, top }: { bookId: string; person: CastMember; top: number }) {
  const source = useSource();
  const hue = hueOf(person.voice?.preset ?? person.name);
  const initials = person.displayName.split(/\s+/).slice(0, 2).map((word) => word[0]).join("").toUpperCase();
  return (
    <div className="flex items-center gap-3 rounded-xl border border-line bg-panel p-3">
      <div className="grid size-10 shrink-0 place-items-center rounded-full text-sm font-bold" style={{ background: `hsl(${hue} 45% 45% / 0.18)`, color: `hsl(${hue} 60% 62%)` }}>
        {initials}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="truncate font-semibold">{person.displayName}</span>
          {person.gender && <span className="shrink-0 text-xs text-fg-3">{person.gender}</span>}
        </div>
        <div className="mt-0.5 truncate text-xs text-fg-2">
          <AudioLines className="mr-1 inline size-3.5 -translate-y-px text-fg-3" />
          {person.voice ? `${person.voice.preset}${person.voice.tone ? ` · ${person.voice.tone}` : ""}` : "Chưa có giọng"}
        </div>
        <div className="mt-2 flex items-center gap-2">
          <div className="h-1 flex-1 overflow-hidden rounded-full bg-line">
            <div className="h-full rounded-full bg-fg-3" style={{ width: `${Math.max(3, (person.lines / top) * 100)}%` }} />
          </div>
          <span className="tabular text-[11px] text-fg-3">{formatNumber(person.lines)} câu</span>
        </div>
      </div>
      {person.sampleId ? <SampleButton id={`sample-${bookId}-${person.sampleId}`} url={source.sampleUrl(bookId, person.sampleId)} label={`Nghe ${person.displayName} nói`} /> : null}
    </div>
  );
}

export function CastList({ bookId }: { bookId: string }) {
  const source = useSource();
  const { data: cast, isLoading } = useCast(bookId);
  const [extras, setExtras] = useState(false);
  if (isLoading) return <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{Array.from({ length: 6 }, (_, index) => <Skeleton key={index} className="h-[84px] rounded-xl" />)}</div>;
  if (!cast || (!cast.characters.length && !cast.extras.length)) {
    return (
      <EmptyState icon={AudioLines} title="Chưa có dàn nhân vật" className="mt-2">
        Dàn nhân vật hiện ra khi truyện đã được phân vai.
      </EmptyState>
    );
  }
  const top = Math.max(1, ...cast.characters.map((person) => person.lines));
  return (
    <div className="mt-4">
      <div className="flex items-center gap-3 rounded-2xl border border-line bg-panel p-4">
        <div className="grid size-11 place-items-center rounded-full bg-accent-soft text-accent-text">
          <BookOpenText className="size-5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-fg-3">Người kể chuyện</div>
          <div className="mt-0.5 font-semibold">{cast.narrator.voice || "Mặc định"}</div>
          <div className="text-xs text-fg-2">{formatNumber(cast.narrator.lines)} câu dẫn truyện · {formatLength(cast.narrator.seconds)}</div>
        </div>
        {cast.narrator.voice && <SampleButton id={`voice-${cast.narrator.voice}`} url={source.voiceUrl(cast.narrator.voice)} label={`Nghe giọng ${cast.narrator.voice}`} />}
      </div>
      <h3 className="mb-3 mt-6 text-sm font-semibold">
        Nhân vật <span className="font-normal text-fg-3">· {cast.characters.length} người có lời thoại</span>
      </h3>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {cast.characters.map((person) => <PersonRow key={person.name} bookId={bookId} person={person} top={top} />)}
      </div>
      {cast.extras.length > 0 && (
        <div className="mt-6">
          <button type="button" onClick={() => setExtras((value) => !value)} className="text-sm font-medium text-fg-2 hover:text-fg">
            {extras ? "Ẩn" : "Hiện"} {cast.extras.length} vai phụ chỉ xuất hiện trong một cảnh
          </button>
          {extras && <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{cast.extras.map((person) => <PersonRow key={person.name} bookId={bookId} person={person} top={top} />)}</div>}
        </div>
      )}
    </div>
  );
}

export function BookScreen({ extraActions }: { extraActions?: (book: ListenBook) => ReactNode }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "chapters";
  const { data: book, isLoading, error } = useListenBook(id);
  const player = usePlayer();
  const playBook = usePlayListenBook();
  const mutations = useListenMutations(id ?? "");

  if (isLoading) {
    return (
      <div className="mx-auto max-w-[1180px] px-4 pt-6 sm:px-10">
        <Skeleton className="h-5 w-24" />
        <div className="mt-6 flex gap-6"><Skeleton className="size-36 rounded-lg" /><div className="flex-1 space-y-3 pt-3"><Skeleton className="h-7 w-2/3" /><Skeleton className="h-4 w-1/3" /></div></div>
      </div>
    );
  }
  if (error || !book) {
    return (
      <EmptyState icon={BookOpenText} title="Không mở được sách" className="mt-20" action={<Button onClick={() => navigate("/")}>Về thư viện</Button>}>
        {(error as Error | null)?.message ?? "Sách có thể đã bị chuyển hoặc xoá."}
      </EmptyState>
    );
  }
  const chapters = book.chapters ?? [];
  const point = resumePoint(book, chapters);
  const listening = player.track?.bookId === book.id;
  const heard = book.progress.heardSeconds;
  const left = Math.max(0, book.duration - heard);
  const primaryLabel = listening
    ? player.playing ? "Tạm dừng" : "Tiếp tục"
    : point && point.at > 0 ? `Nghe tiếp · ${point.chapter.title}` : heard > 0 ? "Nghe tiếp" : "Bắt đầu nghe";

  return (
    <div className="mx-auto max-w-[1180px] px-4 pb-16 pt-5 sm:px-10 sm:pt-7">
      <button type="button" onClick={() => navigate("/")} className="inline-flex items-center gap-1.5 text-sm text-fg-2 hover:text-fg">
        <ArrowLeft className="size-4" /> Thư viện
      </button>
      <header className="mt-5 flex flex-col gap-5 sm:flex-row sm:gap-7">
        <BookCover title={book.title} size="lg" className="w-40 max-sm:mx-auto sm:w-44" />
        <div className="min-w-0 flex-1 max-sm:text-center">
          <h1 className="text-2xl font-bold leading-tight tracking-tight sm:text-[30px]">{book.title}</h1>
          <p className="mt-2 text-sm text-fg-2">
            {book.narrator && `Giọng kể ${book.narrator} · `}
            {book.chaptersTotal} chương · {formatLength(book.duration)}
          </p>
          {book.producing && (
            <p className="mt-2 inline-flex items-center gap-2 rounded-full bg-accent-soft px-3 py-1 text-xs font-medium text-accent-text">
              <Vu className="h-2.5" /> Đang sản xuất · {book.chaptersAvailable}/{book.chaptersTotal} chương nghe được
            </p>
          )}
          <div className="mt-4 max-w-md max-sm:mx-auto">
            <Progress value={book.progress.fraction} tone={book.progress.finished ? "success" : "accent"} size="sm" label="Đã nghe" />
            <div className="tabular mt-1.5 flex justify-between text-xs text-fg-2">
              <span>{book.progress.finished ? "Đã nghe xong" : heard > 0 ? `Đã nghe ${formatLength(heard)}` : "Chưa nghe"}</span>
              {!book.progress.finished && heard > 0 && <span>còn {formatLength(left)}</span>}
            </div>
          </div>
          <div className="mt-5 flex flex-wrap items-center gap-2 max-sm:justify-center">
            {point && (
              <Button
                variant="primary"
                size="lg"
                icon={listening && player.playing ? Pause : Play}
                onClick={() => (listening ? player.toggle() : void playBook(book))}
              >
                {primaryLabel}
              </Button>
            )}
            {heard > 0 && !listening && point && (
              <Tooltip label="Nghe lại từ chương đầu tiên">
                <Button variant="ghost" size="lg" icon={RotateCcw} onClick={() => { const first = chapters.find((chapter) => chapter.available); if (first) void playBook(book, first.id, 0); }}>
                  Từ đầu
                </Button>
              </Tooltip>
            )}
            <DropdownMenu.Root>
              <DropdownMenu.Trigger asChild>
                <span><IconButton label="Tuỳ chọn khác" icon={MoreHorizontal} size="lg" /></span>
              </DropdownMenu.Trigger>
              <DropdownMenu.Portal>
                <DropdownMenu.Content align="start" sideOffset={6} className="z-50 min-w-56 rounded-xl border border-line bg-panel p-1.5 shadow-float">
                  <DropdownMenu.Item
                    onSelect={() => mutations.finished.mutate(!book.progress.finished)}
                    className="flex h-9 cursor-default items-center gap-2 rounded-lg px-2 text-sm outline-none data-[highlighted]:bg-hover"
                  >
                    <CheckCheck className="size-4" />
                    {book.progress.finished ? "Đánh dấu chưa nghe xong" : "Đánh dấu đã nghe xong"}
                  </DropdownMenu.Item>
                  {extraActions?.(book)}
                </DropdownMenu.Content>
              </DropdownMenu.Portal>
            </DropdownMenu.Root>
          </div>
        </div>
      </header>
      <Tabs value={tab} onValueChange={(value) => setParams({ tab: value }, { replace: true })} className="mt-8">
        <TabsList>
          <TabsTrigger value="chapters" count={chapters.length}>Chương</TabsTrigger>
          <TabsTrigger value="bookmarks" count={book.state.bookmarks.length || undefined}>Dấu trang</TabsTrigger>
          <TabsTrigger value="cast">Nhân vật</TabsTrigger>
        </TabsList>
        <TabsContent value="chapters" className="mt-2">
          {chapters.map((chapter) => <ChapterRow key={chapter.id} book={book} chapter={chapter} />)}
        </TabsContent>
        <TabsContent value="bookmarks">
          <BookmarksTab book={book} />
        </TabsContent>
        <TabsContent value="cast">
          <CastList bookId={book.id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
