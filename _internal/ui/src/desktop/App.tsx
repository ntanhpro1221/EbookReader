import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { BookPlus, Clapperboard, Compass, FolderDown, Headphones } from "lucide-react";
import { useEffect, useMemo, type ReactNode } from "react";
import { HashRouter, Route, Routes, useNavigate } from "react-router";
import { Toaster, toast } from "sonner";
import { BookScreen } from "@/listen/BookScreen";
import { ClipProvider } from "@/listen/clip";
import { WebAudioEngine } from "@/listen/engine";
import { LibraryScreen } from "@/listen/LibraryScreen";
import { MorningRecap } from "@/listen/MorningRecap";
import { PlayerProvider, usePlayer } from "@/listen/player";
import { SourceProvider } from "@/listen/source";
import { Button, EmptyState, TooltipProvider } from "@/shared/ui";
import type { ListenBook } from "@/listen/model";
import { coverArtwork } from "@/shared/cover";
import { api } from "@/studio/api";
import { pickFolder, useAppInfo, usePreferences } from "@/studio/data";
import { NewProjectScreen } from "@/studio/NewProjectScreen";
import { ProjectScreen } from "@/studio/ProjectScreen";
import { ProjectsScreen } from "@/studio/ProjectsScreen";
import { httpSource } from "./httpSource";
import { SettingsScreen } from "./SettingsScreen";
import { Shell } from "./Shell";

function useTheme(theme: string | undefined) {
  useEffect(() => {
    const root = document.documentElement;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      root.dataset.theme = theme === "dark" || (theme !== "light" && media.matches) ? "dark" : "light";
    };
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [theme]);
}

function ClipBridge({ children }: { children: ReactNode }) {
  const player = usePlayer();
  return <ClipProvider onStart={() => player.playing && player.toggle()}>{children}</ClipProvider>;
}

function EmptyLibrary() {
  const navigate = useNavigate();
  return (
    <EmptyState
      icon={Headphones}
      title="Chưa có sách để nghe"
      className="mt-12 rounded-2xl border border-dashed border-line"
      action={
        <Button variant="primary" size="lg" icon={BookPlus} onClick={() => navigate("/studio/new")}>
          Tạo sách nói đầu tiên
        </Button>
      }
    >
      Sách xuất hiện ở đây ngay khi chương đầu tiên thu xong - không cần chờ cả cuốn.
    </EmptyState>
  );
}

function StudioMenuItem({ id }: { id: string }) {
  const navigate = useNavigate();
  return (
    <DropdownMenu.Item
      onSelect={() => navigate(`/studio/${id}`)}
      className="flex h-9 cursor-default items-center gap-2 rounded-lg px-2 text-sm outline-none data-[highlighted]:bg-hover"
    >
      <Clapperboard className="size-4" /> Mở trong Studio
    </DropdownMenu.Item>
  );
}

/** Xuất thư mục MP3 có tên sách, tên chương, bìa - nghe được bằng mọi trình phát khác. */
function ExportMenuItem({ book }: { book: ListenBook }) {
  const { data: info } = useAppInfo();
  const run = async () => {
    let target = "";
    if (info?.dialogs) {
      const picked = await pickFolder("Chọn nơi lưu bản xuất", "").catch(() => null);
      if (!picked) return;
      target = picked;
    }
    const pending = toast.loading("Đang xuất sách…", { description: `${book.chaptersAvailable} chương` });
    try {
      const result = await api<{ folder: string; files: number; chaptersTotal: number }>(`/api/books/${book.id}/export`, {
        method: "POST",
        body: { target, cover: coverArtwork(book.title) },
      });
      toast.success(`Đã xuất ${result.files} chương`, {
        id: pending,
        description: result.files < result.chaptersTotal ? "Các chương chưa làm xong sẽ không có trong bản xuất." : result.folder,
        action: {
          label: "Mở thư mục",
          onClick: () => void api("/api/reveal-export", { method: "POST", body: { folder: result.folder } }),
        },
      });
    } catch (error) {
      toast.error("Không xuất được", { id: pending, description: (error as Error).message });
    }
  };
  return (
    <DropdownMenu.Item
      onSelect={() => void run()}
      className="flex h-9 cursor-default items-center gap-2 rounded-lg px-2 text-sm outline-none data-[highlighted]:bg-hover"
    >
      <FolderDown className="size-4" /> Xuất MP3 để nghe ở app khác
    </DropdownMenu.Item>
  );
}

function StudioChipLink({ id }: { id: string }) {
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => navigate(`/studio/${id}`)} className="font-semibold underline underline-offset-2 hover:no-underline">
      Mở Studio
    </button>
  );
}

function LibraryRoute() {
  const navigate = useNavigate();
  return (
    <LibraryScreen
      empty={<EmptyLibrary />}
      recap={<MorningRecap className="mt-6" />}
      onOpenUpcoming={(book) => navigate(`/studio/${book.id}`)}
    />
  );
}

function NotFound() {
  const navigate = useNavigate();
  return (
    <EmptyState
      icon={Compass}
      title="Không có trang này"
      className="mt-24"
      action={<Button onClick={() => navigate("/")}>Về Thư viện</Button>}
    >
      Đường dẫn có thể đã cũ hoặc gõ nhầm.
    </EmptyState>
  );
}

export function App() {
  const { data: info } = useAppInfo();
  const { data: preferences } = usePreferences();
  useTheme(preferences?.theme ?? info?.theme);
  const engine = useMemo(() => new WebAudioEngine(), []);
  if (!info) return <div className="grid h-full place-items-center text-fg-3">Đang mở Ebook Reader…</div>;
  return (
    <TooltipProvider delayDuration={350} skipDelayDuration={150}>
      <SourceProvider source={httpSource}>
        <PlayerProvider
          engine={engine}
          defaultRate={info.playbackRate}
          defaultVolume={info.volume}
          fadeSeconds={preferences?.sleepFadeSeconds ?? info.sleepFadeSeconds}
          extendMinutes={preferences?.sleepExtendMinutes ?? info.sleepExtendMinutes}
          safetyStopHours={preferences?.safetyStopHours ?? info.safetyStopHours}
          sleepSchedule={preferences ? preferences.sleepSchedule : info.sleepSchedule}
        >
          <ClipBridge>
            <HashRouter>
              <Shell>
                <Routes>
                  <Route path="/" element={<LibraryRoute />} />
                  <Route
                    path="/book/:id"
                    element={
                      <BookScreen
                        extraActions={(book) => (
                          <>
                            <ExportMenuItem book={book} />
                            <StudioMenuItem id={book.id} />
                          </>
                        )}
                        studioLink={(book) => <StudioChipLink id={book.id} />}
                      />
                    }
                  />
                  <Route path="/studio" element={<ProjectsScreen />} />
                  <Route path="/studio/new" element={<NewProjectScreen />} />
                  <Route path="/studio/:id" element={<ProjectScreen />} />
                  <Route path="/settings" element={<SettingsScreen />} />
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </Shell>
            </HashRouter>
          </ClipBridge>
        </PlayerProvider>
      </SourceProvider>
      <Toaster
        position="bottom-right"
        offset={96}
        containerAriaLabel="Thông báo"
        toastOptions={{
          classNames: {
            toast: "!bg-panel !border !border-line !text-fg !shadow-float !rounded-xl",
            description: "!text-fg-2",
          },
        }}
      />
    </TooltipProvider>
  );
}
