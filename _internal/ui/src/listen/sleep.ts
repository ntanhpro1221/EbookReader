// Hẹn giờ ngủ - phần tính toán, chung cho máy tính và giao diện Android (lõi native tự đếm trên Android).
//
// Ba điều người nghe lúc buồn ngủ cần, rút ra từ đánh giá 26-09:
//  - thời gian chỉ trôi khi ĐANG PHÁT: tự tạm dừng rồi quay lại không bị tắt ngay lập tức, và con số trên nút
//    không bao giờ treo ở "1′" sau khi hết giờ;
//  - nhỏ dần theo thang dB (tai nghe âm lượng theo logarit): giảm đều theo biên độ thì mấy bậc cuối tụt như bị cắt;
//  - nghe thêm được bằng một thao tác (trên điện thoại là lắc máy; trên máy tính là chạm phím/chuột lúc đang nhỏ dần).

export type SleepRequest = { kind: "off" } | { kind: "minutes"; minutes: number } | { kind: "chapter" };

/** `leftMs` là thời gian còn lại tính tới mốc `since`; `since` = lúc bắt đầu đếm (đang phát), null khi đang dừng. */
export type SleepMode =
  | { kind: "off" }
  | { kind: "minutes"; minutes: number; leftMs: number; since: number | null }
  | { kind: "chapter" };

export const SLEEP_CHOICES = [5, 10, 15, 30, 45, 60, 90];
export const DEFAULT_FADE_SECONDS = 30;
export const DEFAULT_EXTEND_MINUTES = 10;
const FADE_FLOOR_DB = -40;

export function sleepFrom(request: SleepRequest, playing: boolean, now: number): SleepMode {
  if (request.kind !== "minutes") return request;
  return { kind: "minutes", minutes: request.minutes, leftMs: request.minutes * 60_000, since: playing ? now : null };
}

export function sleepLeftMs(mode: SleepMode, now: number): number | null {
  if (mode.kind !== "minutes") return null;
  return Math.max(0, mode.since === null ? mode.leftMs : mode.leftMs - Math.max(0, now - mode.since));
}

/** Đồng hồ ngừng khi tạm dừng, chạy tiếp khi phát. */
export function sleepPaused(mode: SleepMode, now: number): SleepMode {
  if (mode.kind !== "minutes" || mode.since === null) return mode;
  return { ...mode, leftMs: sleepLeftMs(mode, now) ?? 0, since: null };
}

export function sleepResumed(mode: SleepMode, now: number): SleepMode {
  if (mode.kind !== "minutes" || mode.since !== null) return mode;
  return { ...mode, since: now };
}

/** Nghe thêm: cộng vào thời gian còn lại. Đang "hết chương" thì chuyển thành đếm phút kể từ bây giờ. */
export function sleepExtended(mode: SleepMode, minutes: number, playing: boolean, now: number): SleepMode {
  if (mode.kind === "minutes") {
    const left = sleepLeftMs(mode, now) ?? 0;
    return { kind: "minutes", minutes: mode.minutes, leftMs: left + minutes * 60_000, since: playing ? now : null };
  }
  return sleepFrom({ kind: "minutes", minutes }, playing, now);
}

/** Hệ số âm lượng khi còn `leftMs` trong đoạn nhỏ dần dài `fadeMs`: tuyến tính theo dB từ 0 xuống -40 dB. */
export function fadeGain(leftMs: number, fadeMs: number): number {
  if (fadeMs <= 0 || leftMs >= fadeMs) return 1;
  const progress = 1 - Math.max(0, leftMs) / fadeMs;
  return 10 ** ((FADE_FLOOR_DB * progress) / 20);
}

/** Nhãn trên nút: "14:59", phút cuối vẫn đếm từng giây; "Hết chương". */
export function sleepLabel(mode: SleepMode, now: number): string {
  if (mode.kind === "chapter") return "Hết chương";
  const left = sleepLeftMs(mode, now);
  if (left === null) return "";
  const seconds = Math.ceil(left / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export function sleepSpoken(mode: SleepMode, now: number): string {
  if (mode.kind === "chapter") return "Hẹn giờ tắt: dừng khi hết chương này";
  const left = sleepLeftMs(mode, now);
  if (left === null) return "Hẹn giờ tắt";
  const minutes = Math.ceil(left / 60_000);
  return left < 60_000 ? `Hẹn giờ tắt: còn ${Math.ceil(left / 1000)} giây` : `Hẹn giờ tắt: còn ${minutes} phút`;
}

/** Tự lùi khi nghe lại, theo độ dài lần dừng: vừa dừng thì thôi; vài phút thì lùi một câu; ngủ dậy thì lùi hẳn. */
export function rewindAfter(pausedMs: number): number {
  if (pausedMs < 5 * 60_000) return 0;
  if (pausedMs < 60 * 60_000) return 10;
  return 30;
}
