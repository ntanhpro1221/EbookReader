import { Clapperboard, Library, Plus, Settings } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { NavLink, useLocation, useNavigate } from "react-router";
import { useRestoreLastListening } from "@/listen/LibraryScreen";
import { useNowPlaying } from "@/listen/player";
import { NowPlaying, PlayerBar } from "@/listen/PlayerViews";
import { BookCover } from "@/shared/BookCover";
import { cn } from "@/shared/cn";
import { formatPercent } from "@/shared/format";
import { Progress, Vu } from "@/shared/ui";
import { useLibrary } from "@/studio/data";

// Máy tính = phía Nghe (giống hệt trình phát Android) + Studio sản xuất. Thanh bên tách hai khu rõ ràng.

function Brand() {
  return (
    <div className="flex items-center gap-2.5 px-2">
      <div className="grid size-9 place-items-center rounded-xl bg-accent text-accent-ink shadow-card">
        <span className="flex h-4 items-end gap-[3px]">
          <span className="h-2 w-[3px] rounded-sm bg-current" />
          <span className="h-4 w-[3px] rounded-sm bg-current" />
          <span className="h-3 w-[3px] rounded-sm bg-current" />
          <span className="h-[10px] w-[3px] rounded-sm bg-current" />
        </span>
      </div>
      <div className="text-[15px] font-bold tracking-tight">Ebook Reader</div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mt-6">
      <div className="mb-1.5 px-2.5 text-xs font-semibold uppercase tracking-[0.08em] text-fg-2">{title}</div>
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}

const NAV = "flex h-9 items-center gap-3 rounded-lg px-2.5 text-sm transition-colors";
const NAV_ACTIVE = "bg-nav-active font-semibold text-fg shadow-[0_0_0_1px_var(--nav-active-ring)] [&>svg]:text-accent-text";
const NAV_IDLE = "font-medium text-fg-2 hover:bg-hover hover:text-fg";

/** Mục thanh bên sáng cả khi đang ở trang con của nó (trang sách thuộc Thư viện, trang dự án thuộc Dự án). */
function NavItem({ to, icon: Icon, match, children }: { to: string; icon: typeof Library; match: (path: string) => boolean; children: ReactNode }) {
  const { pathname } = useLocation();
  const active = match(pathname);
  return (
    <NavLink to={to} aria-current={active ? "page" : undefined} className={cn(NAV, active ? NAV_ACTIVE : NAV_IDLE)}>
      <Icon className="size-[18px]" />
      {children}
    </NavLink>
  );
}

function Producing() {
  const { pathname } = useLocation();
  const { data } = useLibrary({ live: pathname.startsWith("/studio") });
  const navigate = useNavigate();
  const live = (data?.books ?? []).filter((book) => book.running || book.starting);
  if (!live.length) return null;
  return (
    <div className="mt-2 space-y-1">
      {live.map((book) => (
        <button
          key={book.id}
          type="button"
          onClick={() => navigate(`/studio/${book.id}`)}
          className="flex w-full items-center gap-2.5 rounded-lg p-2 text-left hover:bg-hover"
        >
          <BookCover title={book.title} size="xs" className="size-8 rounded-md" />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5 truncate text-xs font-medium">
              <Vu className="h-2 text-accent" />
              <span className="truncate">{book.title}</span>
            </div>
            <div className="mt-1 flex items-center gap-2">
              <Progress value={book.progress.overall} running size="xs" className="flex-1" />
              <span className="tabular text-[11px] text-fg-2">{book.starting ? "…" : formatPercent(book.progress.overall)}</span>
            </div>
          </div>
        </button>
      ))}
    </div>
  );
}

const TITLES: [RegExp, string][] = [
  [/^\/$/, "Thư viện"],
  [/^\/book\//, "Sách"],
  [/^\/studio\/new/, "Tạo sách nói"],
  [/^\/studio\/.+/, "Dự án"],
  [/^\/studio$/, "Studio"],
  [/^\/settings/, "Cài đặt"],
];

export function Shell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const { expanded, setExpanded } = useNowPlaying();
  useRestoreLastListening();

  // Bấm mục thanh bên khi màn "Đang nghe" đang mở: trang mới phải hiện ra, không bị lớp phủ che.
  useEffect(() => {
    setExpanded(false);
    const title = TITLES.find(([pattern]) => pattern.test(pathname))?.[1];
    document.title = title ? `${title} · Ebook Reader` : "Ebook Reader";
  }, [pathname, setExpanded]);

  return (
    <div className="flex h-full">
      <aside className="flex w-[236px] shrink-0 flex-col border-r border-line bg-sunken px-3 pb-4 pt-5">
        <Brand />
        <nav aria-label="Điều hướng">
          <Section title="Nghe">
            <NavItem to="/" icon={Library} match={(path) => path === "/" || path.startsWith("/book/")}>
              Thư viện
            </NavItem>
          </Section>
          <Section title="Studio">
            <NavItem to="/studio" icon={Clapperboard} match={(path) => path.startsWith("/studio") && path !== "/studio/new"}>
              Dự án
            </NavItem>
            <NavItem to="/studio/new" icon={Plus} match={(path) => path === "/studio/new"}>
              Tạo sách nói
            </NavItem>
            <Producing />
          </Section>
        </nav>
        <div className="mt-auto">
          <NavItem to="/settings" icon={Settings} match={(path) => path.startsWith("/settings")}>
            Cài đặt
          </NavItem>
        </div>
      </aside>
      <div className="relative flex min-w-0 flex-1 flex-col">
        <main className="min-h-0 flex-1 overflow-y-auto" inert={expanded}>
          {children}
        </main>
        <PlayerBar />
        <NowPlaying />
      </div>
    </div>
  );
}
