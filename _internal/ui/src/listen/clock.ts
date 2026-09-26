import { createContext, useContext, useSyncExternalStore } from "react";

// Đồng hồ phát nằm NGOÀI context của trình phát.
//
// Đo 26-09: `time` đổi ~4 lần/giây, và khi nó nằm chung context với mọi thứ khác thì 210-630 component render lại
// mỗi nhịp (8-30 ms ở bản dev, giật khi cuộn trong lúc phát) - suốt nhiều giờ nghe, trên cả điện thoại. Giờ chỉ
// những chỗ thật sự cần (thanh tua, nhãn giờ, câu đang đọc) đăng ký, và mỗi chỗ chỉ render khi GIÁ TRỊ NÓ CHỌN đổi:
// nhãn giờ theo giây, câu đang đọc theo câu.

export class Clock {
  time = 0;
  duration = 0;
  private listeners = new Set<() => void>();

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  set(time: number, duration: number = this.duration): void {
    if (time === this.time && duration === this.duration) return;
    this.time = time;
    this.duration = duration;
    this.listeners.forEach((listener) => listener());
  }
}

export const ClockContext = createContext<Clock | null>(null);

function useClockInstance(): Clock {
  const clock = useContext(ClockContext);
  if (!clock) throw new Error("useClock ngoài PlayerProvider");
  return clock;
}

/** Giá trị suy ra từ đồng hồ; component chỉ render lại khi giá trị này đổi. Chỉ trả về kiểu nguyên thuỷ. */
export function useClock<T extends number | string | boolean>(select: (time: number, duration: number) => T): T {
  const clock = useClockInstance();
  return useSyncExternalStore(clock.subscribe, () => select(clock.time, clock.duration));
}

/** Giây đang phát (làm tròn xuống) - cho nhãn giờ. */
export function usePlaybackSecond(): number {
  return useClock((time) => Math.floor(time));
}

export function useDuration(): number {
  return useClock((_time, duration) => duration);
}

/** Đọc giờ hiện tại trong một hàm xử lý sự kiện mà không đăng ký render. */
export function useClockReader(): () => { time: number; duration: number } {
  const clock = useClockInstance();
  return () => ({ time: clock.time, duration: clock.duration });
}
