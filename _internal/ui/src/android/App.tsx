import { App as CapacitorApp } from "@capacitor/app";
import { Download, Library, Settings } from "lucide-react";
import { useEffect, useMemo, type ReactNode } from "react";
import { HashRouter, NavLink, Route, Routes, useLocation, useNavigate } from "react-router";
import { Toaster } from "sonner";
import { BookScreen } from "@/listen/BookScreen";
import { ClipProvider } from "@/listen/clip";
import { LibraryScreen, useRestoreLastListening } from "@/listen/LibraryScreen";
import { ReaderScreen } from "@/listen/ReaderScreen";
import { NowPlaying, PlayerBar } from "@/listen/PlayerViews";
import { PlayerProvider, useNowPlaying, usePlayer } from "@/listen/player";
import { SourceProvider } from "@/listen/source";
import { cn } from "@/shared/cn";
import { Button, EmptyState, TooltipProvider } from "@/shared/ui";
import { androidSource } from "./androidSource";
import { DevicesScreen } from "./DevicesScreen";
import { MorningRecap } from "@/listen/MorningRecap";
import { NativeAudioEngine } from "./nativeEngine";
import { SettingsScreen } from "./SettingsScreen";
import { applyTheme, loadSettings, pushSettings } from "./settings";

// Vỏ Android: cùng các màn hình Nghe với máy tính, bố cục một tay - điều hướng dưới đáy, trình phát thu nhỏ ngay
// trên thanh điều hướng, nút Back của máy đóng màn hình đang nghe trước rồi mới lùi trang.

function BackButton() {
  const navigate = useNavigate();
  const location = useLocation();
  const { expanded, setExpanded } = useNowPlaying();
  useEffect(() => {
    const handle = CapacitorApp.addListener("backButton", () => {
      if (expanded) setExpanded(false);
      else if (location.pathname !== "/") navigate(-1);
      else void CapacitorApp.minimizeApp();
    });
    return () => void handle.then((listener) => listener.remove());
  }, [navigate, location.pathname, expanded, setExpanded]);
  return null;
}

function Tab({ to, icon: Icon, label }: { to: string; icon: typeof Library; label: string }) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      className={({ isActive }) =>
        cn("flex flex-1 flex-col items-center justify-center gap-1 text-[11px] font-medium", isActive ? "text-accent-text" : "text-fg-3")
      }
    >
      <Icon className="size-[22px]" strokeWidth={1.9} />
      {label}
    </NavLink>
  );
}

function MobileShell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const { setExpanded } = useNowPlaying();
  useRestoreLastListening();
  useEffect(() => setExpanded(false), [pathname, setExpanded]);
  return (
    <div className="relative flex h-full flex-col" style={{ paddingTop: "env(safe-area-inset-top)" }}>
      <main className="min-h-0 flex-1 overflow-y-auto overscroll-contain">{children}</main>
      <PlayerBar compact />
      <nav
        className="flex h-16 shrink-0 border-t border-line bg-panel"
        style={{ paddingBottom: "env(safe-area-inset-bottom)", boxSizing: "content-box" }}
        aria-label="Điều hướng"
      >
        <Tab to="/" icon={Library} label="Thư viện" />
        <Tab to="/devices" icon={Download} label="Tải sách" />
        <Tab to="/settings" icon={Settings} label="Cài đặt" />
      </nav>
      <NowPlaying mobile />
    </div>
  );
}

function EmptyLibrary() {
  const navigate = useNavigate();
  return (
    <EmptyState
      icon={Download}
      title="Chưa có sách trên máy"
      className="mt-10"
      action={
        <Button variant="primary" size="lg" icon={Download} onClick={() => navigate("/devices")}>
          Tải sách từ máy tính
        </Button>
      }
    >
      Kết nối với Ebook Reader trên máy tính qua Wi-Fi rồi tải sách về - nghe được cả khi không có mạng.
    </EmptyState>
  );
}

function LibraryPage() {
  return <LibraryScreen empty={<EmptyLibrary />} recap={<MorningRecap className="mt-5" />} />;
}

function ClipBridge({ children }: { children: ReactNode }) {
  const player = usePlayer();
  return <ClipProvider onStart={() => player.playing && player.toggle()}>{children}</ClipProvider>;
}

export function AndroidApp() {
  const engine = useMemo(() => new NativeAudioEngine(), []);
  useEffect(() => {
    const settings = loadSettings();
    applyTheme(settings.theme);
    void pushSettings(settings);
  }, []);
  return (
    <TooltipProvider delayDuration={500}>
      <SourceProvider source={androidSource}>
        <PlayerProvider engine={engine} keyboard={false} fadeSeconds={loadSettings().sleepFadeSeconds} extendMinutes={loadSettings().sleepExtendMinutes}>
          <ClipBridge>
            <HashRouter>
              <BackButton />
              <MobileShell>
                <Routes>
                  <Route path="/" element={<LibraryPage />} />
                  <Route path="/book/:id" element={<BookScreen />} />
                  <Route path="/book/:id/read/:chapterId?" element={<ReaderScreen />} />
                  <Route path="/devices" element={<DevicesScreen />} />
                  <Route path="/settings" element={<SettingsScreen />} />
                </Routes>
              </MobileShell>
            </HashRouter>
          </ClipBridge>
        </PlayerProvider>
      </SourceProvider>
      <Toaster position="top-center" containerAriaLabel="Thông báo" toastOptions={{ classNames: { toast: "!bg-panel !border !border-line !text-fg !rounded-xl", description: "!text-fg-2" } }} />
    </TooltipProvider>
  );
}
