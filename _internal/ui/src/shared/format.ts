// Định dạng kiểu Việt: "1.234" cho số, "9 giờ 12 phút" cho thời lượng dài, "13:05" cho đồng hồ phát.

const numberFormat = new Intl.NumberFormat("vi-VN");

export function formatNumber(value: number): string {
  return numberFormat.format(Math.round(value));
}

export function formatPercent(fraction: number): string {
  const value = Math.max(0, Math.min(1, fraction)) * 100;
  if (value > 0 && value < 1) return "<1%";
  if (value < 100 && value > 99) return "99%";
  return `${Math.floor(value)}%`;
}

/** Đồng hồ phát: 3:07, 13:05, 1:02:05 */
export function formatClock(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) seconds = 0;
  const whole = Math.floor(seconds);
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const secs = whole % 60;
  const mm = hours ? String(minutes).padStart(2, "0") : String(minutes);
  return `${hours ? `${hours}:` : ""}${mm}:${String(secs).padStart(2, "0")}`;
}

/** Thời lượng cho con người: "45 phút", "9 giờ 12 phút", "2 giờ". */
export function formatLength(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "0 phút";
  const minutes = Math.round(seconds / 60);
  if (minutes < 1) return "dưới 1 phút";
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (!hours) return `${minutes} phút`;
  return rest ? `${hours} giờ ${rest} phút` : `${hours} giờ`;
}

export function formatEta(seconds: number): string {
  if (seconds < 90) return "sắp xong";
  return `còn khoảng ${formatLength(seconds)}`;
}

export function formatRelative(epochSeconds: number | null | undefined): string {
  if (!epochSeconds) return "";
  const delta = Date.now() / 1000 - epochSeconds;
  if (delta < 60) return "vừa xong";
  if (delta < 3600) return `${Math.floor(delta / 60)} phút trước`;
  if (delta < 86400) return `${Math.floor(delta / 3600)} giờ trước`;
  const days = Math.floor(delta / 86400);
  if (days === 1) return "hôm qua";
  if (days < 7) return `${days} ngày trước`;
  return formatDate(epochSeconds);
}

export function formatDate(epochSeconds: number): string {
  const date = new Date(epochSeconds * 1000);
  return date.toLocaleDateString("vi-VN", { day: "numeric", month: "numeric", year: "numeric" });
}

export function formatTime(epochSeconds: number): string {
  const date = new Date(epochSeconds * 1000);
  const today = new Date();
  const sameDay = date.toDateString() === today.toDateString();
  const time = date.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
  return sameDay ? time : `${time} · ${date.toLocaleDateString("vi-VN", { day: "numeric", month: "numeric" })}`;
}
