import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, AudioLines, BookOpen, BookOpenText, Check, CheckCheck, CircleDashed, History, Loader2, MoreHorizontal, Pause, Play, RotateCcw } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";
import { BookCover } from "@/shared/BookCover";
import { cn } from "@/shared/cn";
import { formatClock, formatLength, formatNumber } from "@/shared/format";
import { Button, EmptyState, IconButton, Progress, Skeleton, Tabs, TabsContent, TabsList, TabsTrigger, Tooltip, Vu } from "@/shared/ui";
import { useClip } from "./clip";
import { bookStatusText, usePlayListenBook } from "./LibraryScreen";
import { chapterHeard, resumePoint, type CastMember, type ListenBook, type ListenChapter } from "./model";
import { usePlayer } from "./player";
import { BookmarkList, chapterStatusLabel } from "./PlayerViews";
import { useCast, useListenBook, useListenMutations, useSource } from "./source";

const MENU_ITEM = "flex h-9 cursor-default items-center gap-2 rounded-lg px-2 text-sm outline-none data-[highlighted]:bg-hover";

function ChapterRow({
  book,
  chapter,
  onDone,
}: {
  book: ListenBook;
  chapter: ListenChapter;
  onDone: (chapterId: number, done: boolean) => void;
}) {
  const player = usePlayer();
  const playBook = usePlayListenBook();
  const navigate = useNavigate();
  const current = player.track?.bookId === book.id && player.track.chapterId === chapter.id;
  const heard = chapterHeard(book.state, chapter);
  const done = heard >= 1;
  const onPlay = () => {
    if (!chapter.available) return;
    if (current) player.toggle();
    else void playBook(book, chapter.id, heard > 0 && heard < 1 ? (book.state.chapters[String(chapter.id)]?.heard ?? 0) : 0);
  };
  const name = chapter.subtitle || chapter.title;
  return (
    <div
      className={cn(
        "group flex items-center gap-3 rounded-xl px-2 py-2.5 sm:px-3",
        current ? "bg-accent-soft" : chapter.available && "hover:bg-hover",
      )}
    >
      <button
        type="button"
        onClick={onPlay}
        disabled={!chapter.available}
        aria-label={current && player.playing ? `Tạm dừng ${chapter.fullTitle}` : `Nghe ${chapter.fullTitle}`}
        className="grid size-9 shrink-0 place-items-center rounded-full text-fg-2 hover:bg-panel hover:text-fg disabled:text-fg-3 disabled:hover:bg-transparent"
      >
        {current && player.playing ? (
          <Vu className="h-3 text-accent" />
        ) : done ? (
          <Check className="size-4 text-success" strokeWidth={3} aria-label="Đã nghe" />
        ) : chapter.available ? (
          <Play className="size-4 translate-x-[1px]" fill="currentColor" strokeWidth={0} />
        ) : (
          <CircleDashed className="size-4" />
        )}
      </button>
      <button type="button" onClick={onPlay} disabled={!chapter.available} className="min-w-0 flex-1 text-left">
        <div className={cn("truncate text-sm font-medium", current && "text-accent-text", (done || !chapter.available) && !current && "text-fg-2")}>
          {name}
        </div>
        <div className="tabular truncate text-xs text-fg-2">
          {chapter.subtitle ? `${chapter.title} · ` : ""}
          {chapter.available ? formatLength(chapter.duration) : chapterStatusLabel(book.producing)}
        </div>
        {heard > 0 && heard < 1 && (
          <div className="mt-1.5 h-[3px] w-24 overflow-hidden rounded-full bg-line-strong">
            <div className="h-full bg-accent" style={{ width: `${heard * 100}%` }} />
          </div>
        )}
      </button>
      <div className="size-8 shrink-0">
        {(
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <button
                type="button"
                aria-label={`Tuỳ chọn ${chapter.fullTitle}`}
                className="grid size-8 place-items-center rounded-md text-fg-2 opacity-0 hover:bg-panel hover:text-fg group-hover:opacity-100 focus-visible:opacity-100 data-[state=open]:opacity-100 max-md:opacity-100"
              >
                <MoreHorizontal className="size-4" />
              </button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content align="end" sideOffset={4} className="z-50 min-w-52 rounded-xl border border-line bg-panel p-1.5 shadow-float">
                {chapter.available && (
                  <DropdownMenu.Item onSelect={() => void playBook(book, chapter.id, 0)} className={MENU_ITEM}>
                    <Play className="size-4" /> Nghe từ đầu chương
                  </DropdownMenu.Item>
                )}
                <DropdownMenu.Item onSelect={() => navigate(`/book/${book.id}/read/${chapter.id}`)} className={MENU_ITEM}>
                  <BookOpen className="size-4" /> Đọc chương này
                </DropdownMenu.Item>
                {chapter.available && (
                  <DropdownMenu.Item onSelect={() => onDone(chapter.id, !done)} className={MENU_ITEM}>
                    {done ? <CircleDashed className="size-4" /> : <CheckCheck className="size-4" />}
                    {done ? "Đánh dấu chưa nghe" : "Đánh dấu đã nghe xong"}
                  </DropdownMenu.Item>
                )}
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
        )}
      </div>
    </div>
  );
}

function BookmarksTab({ book }: { book: ListenBook }) {
  const playBook = usePlayListenBook();
  if (!book.state.bookmarks.length) {
    return (
      <EmptyState icon={BookOpenText} title="Chưa có dấu trang" className="mt-2">
        Khi đang nghe, bấm biểu tượng dấu trang (hoặc phím B) để đánh dấu đoạn muốn quay lại.
      </EmptyState>
    );
  }
  return (
    <div className="mt-3 -mx-3">
      <BookmarkList
        bookId={book.id}
        chapters={book.chapters ?? []}
        marks={book.state.bookmarks}
        onJump={(mark) => void playBook(book, mark.chapterId, mark.seconds)}
      />
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

/** Tên hiển thị không lộ dữ liệu thô: gạch dưới thành dấu cách. */
function cleanName(name: string): string {
  return name.replace(/_/g, " ").replace(/\s+/g, " ").trim();
}

export function PersonRow({ bookId, person }: { bookId: string; person: CastMember; top?: number }) {
  const source = useSource();
  const name = cleanName(person.displayName);
  const initials = name
    .split(/\s+/)
    .filter((word) => !/^[IVXLCDM]+$/.test(word))
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase();
  return (
    <div className="flex items-center gap-3 rounded-xl border border-line bg-panel p-3">
      <div
        className="avatar grid size-10 shrink-0 place-items-center rounded-full text-sm font-bold"
        style={{ ["--hue" as string]: hueOf(person.voice?.preset ?? person.name) }}
        aria-hidden
      >
        {initials}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="truncate font-semibold">{name}</span>
          {person.gender && <span className="shrink-0 text-xs text-fg-2">{person.gender}</span>}
        </div>
        <div className="mt-0.5 truncate text-xs text-fg-2">
          <AudioLines className="mr-1 inline size-3.5 -translate-y-px text-fg-3" />
          {person.voice ? `${person.voice.preset}${person.voice.tone ? ` · ${person.voice.tone}` : ""}` : "Chưa có giọng"}
        </div>
        <div className="tabular mt-1 text-xs text-fg-2">
          {formatNumber(person.lines)} câu
          {person.seconds > 0 ? ` · ${formatLength(person.seconds)}` : ""}
          {person.firstChapter ? ` · từ ${person.firstChapter}` : ""}
        </div>
      </div>
      {person.sampleId ? <SampleButton id={`sample-${bookId}-${person.sampleId}`} url={source.sampleUrl(bookId, person.sampleId)} label={`Nghe ${name} nói`} /> : null}
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
  return (
    <div className="mt-4">
      <div className="flex items-center gap-3 rounded-2xl border border-line bg-panel p-4">
        <div className="grid size-11 place-items-center rounded-full bg-accent-soft text-accent-text">
          <BookOpenText className="size-5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-xs font-semibold uppercase tracking-[0.08em] text-fg-2">Người kể chuyện</div>
          <div className="mt-0.5 font-semibold">{cast.narrator.voice || "Mặc định"}</div>
          <div className="tabular text-xs text-fg-2">{formatNumber(cast.narrator.lines)} câu dẫn truyện · {formatLength(cast.narrator.seconds)}</div>
        </div>
        {cast.narrator.voice && <SampleButton id={`voice-${cast.narrator.voice}`} url={source.voiceUrl(cast.narrator.voice)} label={`Nghe giọng ${cast.narrator.voice}`} />}
      </div>
      <h3 className="mb-3 mt-6 text-sm font-semibold">
        Nhân vật <span className="font-normal text-fg-2">· {cast.characters.length} người có lời thoại</span>
      </h3>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {cast.characters.map((person) => <PersonRow key={person.name} bookId={bookId} person={person} />)}
      </div>
      {cast.extras.length > 0 && (
        <div className="mt-6">
          <button type="button" onClick={() => setExtras((value) => !value)} className="text-sm font-medium text-fg-2 hover:text-fg">
            {extras ? "Ẩn" : "Hiện"} {cast.extras.length} vai phụ chỉ xuất hiện trong một cảnh
          </button>
          {extras && <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{cast.extras.map((person) => <PersonRow key={person.name} bookId={bookId} person={person} />)}</div>}
        </div>
      )}
    </div>
  );
}

const TABS = ["chapters", "bookmarks", "history", "cast"] as const;

function dayLabel(epoch: number): string {
  const date = new Date(epoch * 1000);
  const today = new Date();
  const days = Math.round(
    (new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime() - new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()) /
      86_400_000,
  );
  if (days === 0) return "Hôm nay";
  if (days === 1) return "Hôm qua";
  return date.toLocaleDateString("vi-VN", { weekday: "long", day: "numeric", month: "numeric" });
}

function clockOf(epoch: number): string {
  return new Date(epoch * 1000).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

/** Lịch sử nghe: mỗi phiên một dòng, gom theo ngày; bấm để nghe tiếp từ cuối phiên ấy. */
function HistoryTab({ book }: { book: ListenBook }) {
  const source = useSource();
  const playBook = usePlayListenBook();
  const { data: sessions } = useQuery({
    queryKey: ["listen", "sessions", book.id],
    queryFn: () => source.sessions!(book.id),
    enabled: Boolean(source.sessions),
  });
  const titleOf = (chapterId: number) => {
    const chapter = book.chapters?.find((item) => item.id === chapterId);
    return chapter ? chapter.title : "chương đã gỡ";
  };
  if (!sessions?.length) {
    return (
      <EmptyState icon={History} title="Chưa có lịch sử nghe" className="mt-2">
        Mỗi lần nghe (bấm phát tới lúc dừng) sẽ hiện ở đây - để biết hôm nào nghe tới đâu.
      </EmptyState>
    );
  }
  const week = sessions.filter((item) => Date.now() / 1000 - item.startedAt < 7 * 86_400).reduce((sum, item) => sum + item.listened, 0);
  const groups = new Map<string, typeof sessions>();
  [...sessions].reverse().forEach((item) => {
    const key = dayLabel(item.startedAt);
    groups.set(key, [...(groups.get(key) ?? []), item]);
  });
  return (
    <div className="mt-3">
      <p className="text-sm text-fg-2">
        7 ngày qua: <span className="font-semibold text-fg">{formatLength(week)}</span> nghe cuốn này.
      </p>
      {[...groups.entries()].map(([day, items]) => (
        <section key={day} className="mt-5">
          <h3 className="text-xs font-semibold uppercase tracking-[0.08em] text-fg-2">{day}</h3>
          <ul className="mt-2 divide-y divide-line">
            {items.map((item) => (
              <li key={item.id} className="flex items-center gap-3 py-2.5">
                <div className="min-w-0 flex-1">
                  <div className="tabular text-sm font-medium">
                    {clockOf(item.startedAt)}-{clockOf(item.endedAt)} · {formatLength(item.listened)}
                  </div>
                  <div className="tabular truncate text-xs text-fg-2">
                    {titleOf(item.from.chapterId)} {formatClock(item.from.seconds)} → {titleOf(item.to.chapterId)} {formatClock(item.to.seconds)}
                  </div>
                </div>
                <Button size="sm" variant="ghost" icon={Play} onClick={() => void playBook(book, item.to.chapterId, item.to.seconds)}>
                  Nghe từ đây
                </Button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

export function BookScreen({
  extraActions,
  studioLink,
}: {
  extraActions?: (book: ListenBook) => ReactNode;
  /** Máy tính: lối sang Studio ngay trên dòng trạng thái của sách đang làm. */
  studioLink?: (book: ListenBook) => ReactNode;
}) {
  const { id } = useParams();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const requested = params.get("tab");
  const tab = TABS.includes(requested as (typeof TABS)[number]) ? (requested as string) : "chapters";
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
      <EmptyState icon={BookOpenText} title="Không tìm thấy sách này" className="mt-20" action={<Button onClick={() => navigate("/")}>Về thư viện</Button>}>
        Sách có thể đã bị chuyển sang thư mục khác hoặc bị xoá khỏi thư viện.
      </EmptyState>
    );
  }
  const chapters = book.chapters ?? [];
  const point = resumePoint(book, chapters);
  const listening = player.track?.bookId === book.id;
  const heard = book.progress.heardSeconds;
  const left = Math.max(0, book.duration - heard);
  const caughtUp = Boolean(book.progress.caughtUp) && !listening;
  const primaryLabel = listening
    ? player.playing ? "Tạm dừng" : "Tiếp tục"
    : point && point.at > 0 ? `Nghe tiếp · ${point.chapter.title}` : heard > 0 ? "Nghe tiếp" : "Bắt đầu nghe";
  const restart = () => {
    const first = chapters.find((chapter) => chapter.available);
    if (!first) return;
    const before = point;
    void playBook(book, first.id, 0);
    if (before && (before.chapter.id !== first.id || before.at > 30)) {
      toast("Đang nghe lại từ đầu", {
        description: `Chỗ cũ: ${before.chapter.title}`,
        action: { label: "Quay lại chỗ cũ", onClick: () => void playBook(book, before.chapter.id, before.at) },
      });
    }
  };

  return (
    <div className="mx-auto max-w-[1180px] px-4 pb-16 pt-5 sm:px-10 sm:pt-7">
      <button type="button" onClick={() => navigate("/")} className="inline-flex items-center gap-1.5 text-sm text-fg-2 hover:text-fg">
        <ArrowLeft className="size-4" /> Thư viện
      </button>
      <header className="mt-5 flex flex-col gap-5 sm:flex-row sm:gap-7">
        <BookCover title={book.title} size="lg" playing={listening && player.playing} className="w-40 max-sm:mx-auto sm:w-44" />
        <div className="min-w-0 flex-1 max-sm:text-center">
          <h1 className="text-2xl font-bold leading-tight tracking-tight sm:text-[30px]">{book.title}</h1>
          <p className="tabular mt-2 text-sm text-fg-2">
            {book.narrator && `Giọng kể ${book.narrator} · `}
            {book.complete
              ? `${book.chaptersTotal} chương · ${formatLength(book.duration)}`
              : `${book.chaptersAvailable}/${book.chaptersTotal} chương có audio · ${formatLength(book.duration)} phần đã có`}
          </p>
          {!book.complete && (
            <p className="mt-2 inline-flex flex-wrap items-center gap-2 rounded-full bg-accent-soft px-3 py-1 text-xs font-medium text-accent-text">
              {book.producing && <Vu className="h-2.5" />}
              {book.producing ? "Đang thu âm - chương mới tự hiện ra khi xong" : "Chưa hoàn thành - Studio đang dừng"}
              {studioLink?.(book)}
            </p>
          )}
          <div className="mt-4 max-w-md max-sm:mx-auto">
            <Progress value={book.progress.fraction} tone={book.progress.finished ? "success" : "accent"} size="sm" label="Đã nghe" />
            <div className="tabular mt-1.5 flex justify-between text-xs text-fg-2">
              <span>{book.progress.finished || book.progress.caughtUp ? bookStatusText(book) : heard > 0 ? `Đã nghe ${formatLength(heard)}` : "Chưa nghe"}</span>
              {!book.progress.finished && !book.progress.caughtUp && heard > 0 && <span>còn {formatLength(left)}</span>}
            </div>
          </div>
          <div className="mt-5 flex flex-wrap items-center gap-2 max-sm:justify-center">
            {point && !caughtUp && (
              <Button
                variant="primary"
                size="lg"
                icon={listening && player.playing ? Pause : Play}
                onClick={() => (listening ? player.toggle() : void playBook(book))}
              >
                {primaryLabel}
              </Button>
            )}
            {caughtUp && (
              <p className="rounded-xl bg-hover px-4 py-2.5 text-sm text-fg-2">Bạn đã nghe hết phần đã có. Chương mới sẽ hiện ở đây khi làm xong.</p>
            )}
            <Tooltip label="Đọc bằng mắt - đọc được cả chương chưa thu âm; “Nghe từ đây” chuyển sang nghe đúng câu đang đọc">
              <Button
                variant="outline"
                size="lg"
                icon={BookOpen}
                onClick={() => navigate(`/book/${book.id}/read/${book.state.reading?.chapterId ?? point?.chapter.id ?? chapters[0]?.id ?? ""}`)}
              >
                {book.state.reading ? "Đọc tiếp" : "Đọc"}
              </Button>
            </Tooltip>
            {heard > 0 && point && (
              <Tooltip label="Nghe lại từ chương đầu tiên">
                <Button variant="ghost" size="lg" icon={RotateCcw} onClick={restart}>
                  Từ đầu
                </Button>
              </Tooltip>
            )}
            <DropdownMenu.Root>
              <DropdownMenu.Trigger asChild>
                <IconButton label="Tuỳ chọn khác" icon={MoreHorizontal} size="lg" />
              </DropdownMenu.Trigger>
              <DropdownMenu.Portal>
                <DropdownMenu.Content align="start" sideOffset={6} className="z-50 min-w-56 rounded-xl border border-line bg-panel p-1.5 shadow-float">
                  <DropdownMenu.Item onSelect={() => mutations.finished.mutate(!book.progress.finished)} className={MENU_ITEM}>
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
          <TabsTrigger value="history">Lịch sử</TabsTrigger>
          <TabsTrigger value="cast">Nhân vật</TabsTrigger>
        </TabsList>
        <TabsContent value="chapters" className="mt-2">
          {chapters.map((chapter) => (
            <ChapterRow
              key={chapter.id}
              book={book}
              chapter={chapter}
              onDone={(chapterId, done) => mutations.chapterDone.mutate({ chapterId, done })}
            />
          ))}
        </TabsContent>
        <TabsContent value="bookmarks">
          <BookmarksTab book={book} />
        </TabsContent>
        <TabsContent value="history">
          <HistoryTab book={book} />
        </TabsContent>
        <TabsContent value="cast">
          <CastList bookId={book.id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
