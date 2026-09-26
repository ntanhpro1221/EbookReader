import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

// Trình phát clip ngắn: nghe thử giọng kể, nghe câu mẫu của một nhân vật. Tách khỏi trình phát chương để
// không làm mất vị trí đang nghe; bấm clip thì tạm dừng chương, clip hết thì thôi (không tự phát lại chương -
// người dùng đang so giọng, tự bật lại tiếng chương giữa chừng là làm phiền).

interface ClipContextValue {
  current: string | null;
  loading: boolean;
  toggle: (id: string, url: string) => void;
  stop: () => void;
}

const ClipContext = createContext<ClipContextValue | null>(null);

export function useClip(): ClipContextValue {
  const value = useContext(ClipContext);
  if (!value) throw new Error("useClip ngoài ClipProvider");
  return value;
}

export function ClipProvider({ children, onStart }: { children: ReactNode; onStart?: () => void }) {
  const audio = useRef<HTMLAudioElement | null>(null);
  if (audio.current === null && typeof Audio !== "undefined") audio.current = new Audio();
  const [current, setCurrent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const stop = useCallback(() => {
    audio.current?.pause();
    setCurrent(null);
    setLoading(false);
  }, []);

  const toggle = useCallback((id: string, url: string) => {
    const element = audio.current;
    if (!element) return;
    if (current === id) {
      stop();
      return;
    }
    onStart?.();
    element.pause();
    element.src = url;
    element.currentTime = 0;
    setCurrent(id);
    setLoading(true);
    void element.play().catch(() => {
      setCurrent(null);
      setLoading(false);
    });
  }, [current, onStart, stop]);

  useEffect(() => {
    const element = audio.current;
    if (!element) return;
    const ended = () => {
      setCurrent(null);
      setLoading(false);
    };
    const playing = () => setLoading(false);
    element.addEventListener("ended", ended);
    element.addEventListener("error", ended);
    element.addEventListener("playing", playing);
    return () => {
      element.removeEventListener("ended", ended);
      element.removeEventListener("error", ended);
      element.removeEventListener("playing", playing);
    };
  }, []);

  const value = useMemo(() => ({ current, loading, toggle, stop }), [current, loading, toggle, stop]);
  return <ClipContext.Provider value={value}>{children}</ClipContext.Provider>;
}
