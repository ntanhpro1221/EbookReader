import type { NightEvent, NightPosition, NightSession } from "./model";

// Nhật ký đêm của bộ máy phát web (máy tính). Lõi Android có bản native của nó (Bedtime.kt) cùng hình dạng.
//
// Không ai biết chính xác lúc người nghe thiếp đi, nhưng có những mốc chắc chắn: lúc hẹn giờ, lần cuối còn chạm
// vào máy (bấm phím, rê chuột, tua, gia hạn) - chắc chắn còn thức - và lúc tự dừng. Sáng dậy, thẻ "Tối qua"
// (MorningRecap) đặt câu văn ở từng mốc cạnh nhau để người nghe nhận ra đoạn cuối mình còn nhớ.

const CHECKPOINT_MS = 30_000;
const TOUCH_EVERY_MS = 20_000;
const SAVE_AFTER_MS = 2_000;
const MAX_EVENTS = 200;
const MAX_POINTS = 480;
/** Hẹn giờ lại trong vòng chừng này sau lúc tự dừng (tỉnh giấc, nghe thêm) vẫn là cùng một đêm. */
const SAME_NIGHT_MS = 45 * 60_000;

function newId(): string {
  return Math.random().toString(16).slice(2, 14).padEnd(12, "0");
}

export class NightRecorder {
  private session: NightSession | null = null;
  private bookId = "";
  private lastTouch = 0;
  private lastPoint = 0;
  private fadingLogged = false;
  private saveTimer: number | undefined;

  constructor(private readonly persist?: (bookId: string, night: NightSession) => Promise<void>) {}

  get active(): boolean {
    return Boolean(this.session && !this.session.endedAt);
  }

  start(book: { id: string; title: string }, minutes: number | null, position: NightPosition): void {
    const now = Date.now();
    const current = this.session;
    const reusable =
      current &&
      this.bookId === book.id &&
      (!current.endedAt || now - current.endedAt * 1000 < SAME_NIGHT_MS);
    if (!reusable) {
      this.flush();
      this.session = {
        id: newId(),
        device: "desktop",
        bookId: book.id,
        bookTitle: book.title,
        startedAt: now / 1000,
        endedAt: null,
        events: [],
        timeline: [],
      };
      this.bookId = book.id;
    } else if (current) {
      current.endedAt = null;
    }
    this.fadingLogged = false;
    this.push({ type: "timer", at: now / 1000, minutes: minutes ?? undefined, position });
  }

  /** Người nghe còn thức: một thao tác trên trình phát hay trên máy. Ghi thưa (20 giây một lần) trừ khi `force`. */
  touch(action: string, position: NightPosition, force = false): void {
    if (!this.active) return;
    const now = Date.now();
    if (!force && now - this.lastTouch < TOUCH_EVERY_MS) return;
    this.lastTouch = now;
    this.push({ type: "touch", action, at: now / 1000, position });
  }

  extend(minutes: number, position: NightPosition): void {
    if (!this.active) return;
    this.fadingLogged = false;
    this.lastTouch = Date.now();
    this.push({ type: "extend", minutes, at: Date.now() / 1000, position });
  }

  fading(position: NightPosition): void {
    if (!this.active || this.fadingLogged) return;
    this.fadingLogged = true;
    this.push({ type: "fading", at: Date.now() / 1000, position });
  }

  checkpoint(position: NightPosition): void {
    if (!this.active || !this.session) return;
    const now = Date.now();
    if (now - this.lastPoint < CHECKPOINT_MS) return;
    this.lastPoint = now;
    this.session.timeline.push({ ...position, at: now / 1000 });
    if (this.session.timeline.length > MAX_POINTS) this.session.timeline.splice(0, this.session.timeline.length - MAX_POINTS);
    this.schedule();
  }

  /** Hẹn giờ đã dừng phát: mốc quan trọng nhất cho buổi sáng. */
  stop(position: NightPosition): void {
    if (!this.active || !this.session) return;
    this.push({ type: "stopped", at: Date.now() / 1000, position });
    this.session.endedAt = Date.now() / 1000;
    this.flush();
  }

  /** Người nghe tự tắt hẹn giờ: họ đang thức, đêm này không cần thẻ buổi sáng. */
  cancel(position: NightPosition): void {
    if (!this.active || !this.session) return;
    this.push({ type: "touch", action: "timer-off", at: Date.now() / 1000, position });
    this.session.endedAt = Date.now() / 1000;
    this.flush();
  }

  flush(): void {
    window.clearTimeout(this.saveTimer);
    this.saveTimer = undefined;
    if (this.session && this.bookId && this.persist) {
      void this.persist(this.bookId, JSON.parse(JSON.stringify(this.session)) as NightSession).catch(() => undefined);
    }
  }

  private push(event: NightEvent): void {
    if (!this.session) return;
    this.session.events.push(event);
    if (this.session.events.length > MAX_EVENTS) this.session.events.splice(1, this.session.events.length - MAX_EVENTS);
    this.schedule();
  }

  private schedule(): void {
    if (this.saveTimer !== undefined) return;
    this.saveTimer = window.setTimeout(() => this.flush(), SAVE_AFTER_MS);
  }
}
