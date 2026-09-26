import { EbookPlayer } from "./plugins";

// Tuỳ chọn của trình phát trên điện thoại. Lưu trong WebView (localStorage) và đẩy phần native cần biết xuống
// lõi phát mỗi lần mở app và mỗi lần đổi.

export interface PlayerSettings {
  theme: "system" | "light" | "dark";
  sleepExtendMinutes: number;
  sleepFadeSeconds: number;
  shakeToExtend: boolean;
  rewindSeconds: number;
  rewindAfterMinutes: number;
  /** Phát liên tục chừng này giờ không ai chạm máy thì tự nhỏ dần rồi dừng (0 = tắt). */
  safetyStopHours: number;
  /** Lịch đêm tự hẹn giờ. */
  sleepSchedule: { from: string; to: string; minutes: number } | null;
}

export const DEFAULT_SETTINGS: PlayerSettings = {
  theme: "system",
  sleepExtendMinutes: 10,
  sleepFadeSeconds: 30,
  shakeToExtend: true,
  rewindSeconds: 5,
  rewindAfterMinutes: 5,
  safetyStopHours: 2,
  sleepSchedule: null,
};

const KEY = "ebook-reader-player-settings";

export function loadSettings(): PlayerSettings {
  try {
    return { ...DEFAULT_SETTINGS, ...JSON.parse(localStorage.getItem(KEY) ?? "{}") };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export function saveSettings(settings: PlayerSettings): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(settings));
  } catch {
    /* bộ nhớ WebView bị chặn: vẫn áp dụng cho phiên này */
  }
  void pushSettings(settings);
}

export async function pushSettings(settings: PlayerSettings): Promise<void> {
  await EbookPlayer.configure({
    sleepExtendMinutes: settings.sleepExtendMinutes,
    sleepFadeSeconds: settings.sleepFadeSeconds,
    shakeToExtend: settings.shakeToExtend,
    rewindSeconds: settings.rewindSeconds,
    rewindAfterMinutes: settings.rewindAfterMinutes,
    safetyStopHours: settings.safetyStopHours,
    schedule: settings.sleepSchedule,
  }).catch(() => undefined);
}

export function applyTheme(theme: PlayerSettings["theme"]): void {
  const dark = theme === "dark" || (theme !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}
