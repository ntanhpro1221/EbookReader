import { BookPlus, Headphones } from "lucide-react";
import { useEffect, useMemo, type ReactNode } from "react";
import { HashRouter, Route, Routes, useNavigate } from "react-router";
import { Toaster } from "sonner";
import { BookScreen } from "@/listen/BookScreen";
import { ClipProvider } from "@/listen/clip";
import { WebAudioEngine } from "@/listen/engine";
import { LibraryScreen } from "@/listen/LibraryScreen";
import { PlayerProvider, usePlayer } from "@/listen/player";
import { SourceProvider } from "@/listen/source";
import { Button, EmptyState, TooltipProvider } from "@/shared/ui";
import { useAppInfo, usePreferences } from "@/studio/data";
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

function StudioLink({ id }: { id: string }) {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      onClick={() => navigate(`/studio/${id}`)}
      className="flex h-9 w-full cursor-default items-center gap-2 rounded-lg px-2 text-left text-sm outline-none hover:bg-hover"
    >
      Mở trong Studio
    </button>
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
        <PlayerProvider engine={engine} defaultRate={info.playbackRate} defaultVolume={info.volume}>
          <ClipBridge>
            <HashRouter>
              <Shell>
                <Routes>
                  <Route path="/" element={<LibraryScreen empty={<EmptyLibrary />} />} />
                  <Route path="/book/:id" element={<BookScreen extraActions={(book) => <StudioLink id={book.id} />} />} />
                  <Route path="/studio" element={<ProjectsScreen />} />
                  <Route path="/studio/new" element={<NewProjectScreen />} />
                  <Route path="/studio/:id" element={<ProjectScreen />} />
                  <Route path="/settings" element={<SettingsScreen />} />
                </Routes>
              </Shell>
            </HashRouter>
          </ClipBridge>
        </PlayerProvider>
      </SourceProvider>
      <Toaster
        position="bottom-right"
        offset={96}
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
