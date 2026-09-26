import { Clapperboard, Library, Plus, Settings } from "lucide-react";
import type { ReactNode } from "react";
import { NavLink, useNavigate } from "react-router";
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
      <div className="mb-1.5 px-2.5 text-[11px] font-semibold uppercase tracking-wider text-fg-3">{title}</div>
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}

function NavItem({ to, icon: Icon, end, children }: { to: string; icon: typeof Library; end?: boolean; children: ReactNode }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        cn(
          "flex h-9 items-center gap-3 rounded-lg px-2.5 text-sm font-medium transition-colors",
          isActive ? "bg-hover text-fg" : "text-fg-2 hover:bg-hover hover:text-fg",
        )
      }
    >
      <Icon className="size-[18px]" />
      {children}
    </NavLink>
  );
}

function Producing() {
  const { data } = useLibrary();
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
            <div className="flex items-center gap-1.5 truncate text-[12px] font-medium">
              <Vu className="h-2 text-accent" />
              <span className="truncate">{book.title}</span>
            </div>
            <div className="mt-1 flex items-center gap-2">
              <Progress value={book.progress.overall} running size="xs" className="flex-1" />
              <span className="tabular text-[10px] text-fg-3">{book.starting ? "…" : formatPercent(book.progress.overall)}</span>
            </div>
          </div>
        </button>
      ))}
    </div>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  return (
    <div className="flex h-full">
      <aside className="flex w-[236px] shrink-0 flex-col border-r border-line bg-sunken px-3 pb-4 pt-5">
        <Brand />
        <Section title="Nghe">
          <NavItem to="/" icon={Library} end>
            Thư viện
          </NavItem>
        </Section>
        <Section title="Studio">
          <NavItem to="/studio" icon={Clapperboard} end>
            Dự án
          </NavItem>
          <button
            type="button"
            onClick={() => navigate("/studio/new")}
            className="flex h-9 w-full items-center gap-3 rounded-lg px-2.5 text-sm font-medium text-fg-2 transition-colors hover:bg-hover hover:text-fg"
          >
            <Plus className="size-[18px]" />
            Tạo sách nói
          </button>
          <Producing />
        </Section>
        <div className="mt-auto">
          <NavItem to="/settings" icon={Settings}>
            Cài đặt
          </NavItem>
        </div>
      </aside>
      <div className="relative flex min-w-0 flex-1 flex-col">
        <main className="min-h-0 flex-1 overflow-y-auto">{children}</main>
        <PlayerBar />
        <NowPlaying />
      </div>
    </div>
  );
}
