import { FolderOpen, Monitor, Moon, Sun } from "lucide-react";
import type { ReactNode } from "react";
import { toast } from "sonner";
import { Button, Kbd, Segmented } from "@/shared/ui";
import { cn } from "@/shared/cn";
import { pickFolder, useAppInfo, usePreferences } from "@/studio/data";
import { PhoneSync, Switch } from "./PhoneSync";

function Section({ id, title, description, children }: { id?: string; title: string; description?: string; children: ReactNode }) {
  return (
    <section id={id} className="grid gap-4 border-b border-line py-7 last:border-b-0 lg:grid-cols-[260px_minmax(0,1fr)] lg:gap-8">
      <div>
        <h2 className="text-base font-semibold">{title}</h2>
        {description && <p className="mt-1 text-[13px] leading-relaxed text-fg-2 text-pretty">{description}</p>}
      </div>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 py-2">
      <div className="min-w-0">
        <div className="text-sm font-medium">{label}</div>
        {hint && <div className="mt-0.5 text-[13px] text-fg-2">{hint}</div>}
      </div>
      {children}
    </div>
  );
}

const THEMES = [
  { value: "system", label: "Theo Windows", icon: Monitor },
  { value: "light", label: "Sáng", icon: Sun },
  { value: "dark", label: "Tối", icon: Moon },
] as const;

const SHORTCUTS: [ReactNode, string][] = [
  [<Kbd key="space">Space</Kbd>, "Phát / tạm dừng"],
  [<><Kbd>←</Kbd> <Kbd>→</Kbd></>, "Lùi / tới 15 giây"],
  [<><Kbd>Shift</Kbd> + <Kbd>←</Kbd> <Kbd>→</Kbd></>, "Chương trước / sau"],
  [<Kbd key="b">B</Kbd>, "Thêm dấu trang"],
  [<Kbd key="m">M</Kbd>, "Tắt / bật tiếng"],
  [<><Kbd>[</Kbd> <Kbd>]</Kbd></>, "Giảm / tăng tốc độ đọc"],
  [<Kbd key="esc">Esc</Kbd>, "Thu nhỏ màn hình đang nghe"],
];

export function SettingsScreen() {
  const { data: info } = useAppInfo();
  const { data: preferences, update } = usePreferences();
  const changeLibrary = async () => {
    try {
      const path = await pickFolder("Chọn thư mục thư viện", preferences?.libraryRoot ?? "");
      if (path) {
        update({ libraryRoot: path });
        toast.success("Đã đổi thư mục thư viện");
      }
    } catch (error) {
      toast.error((error as Error).message);
    }
  };
  const fade = String(preferences?.sleepFadeSeconds ?? 30) as "10" | "30" | "60";
  const extend = String(preferences?.sleepExtendMinutes ?? 10) as "5" | "10" | "15";
  return (
    <div className="mx-auto max-w-[1180px] px-4 pb-16 pt-6 sm:px-10 sm:pt-9">
      <h1 className="text-2xl font-bold tracking-tight sm:text-[28px]">Cài đặt</h1>
      <div className="mt-2 max-w-[980px]">
        <Section title="Thư viện" description="Thư mục chứa các sách. Sách mới được tạo trong thư mục này.">
          <div className="flex items-center gap-2">
            <div className="flex h-10 min-w-0 flex-1 items-center gap-2 rounded-lg bg-sunken px-3 text-sm text-fg-2">
              <FolderOpen className="size-4 shrink-0" />
              <span className="truncate" title={preferences?.libraryRoot}>{preferences?.libraryRoot}</span>
            </div>
            {info?.dialogs && (
              <Button icon={FolderOpen} onClick={() => void changeLibrary()}>
                Đổi thư mục
              </Button>
            )}
          </div>
        </Section>
        <Section title="Giao diện" description="Màu sáng hay tối. Theo Windows sẽ tự đổi cùng hệ thống.">
          <div role="radiogroup" aria-label="Giao diện" className="grid max-w-md grid-cols-3 gap-2">
            {THEMES.map((theme) => {
              const selected = (preferences?.theme ?? "system") === theme.value;
              const Icon = theme.icon;
              return (
                <button
                  key={theme.value}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => update({ theme: theme.value })}
                  className={cn(
                    "flex flex-col items-center gap-2 rounded-xl border bg-panel py-4 text-sm font-medium transition-colors",
                    selected ? "border-accent ring-1 ring-accent" : "border-line hover:border-line-strong",
                  )}
                >
                  <Icon className="size-5" />
                  {theme.label}
                </button>
              );
            })}
          </div>
        </Section>
        <Section
          title="Nghe"
          description="Trình phát nhớ vị trí và tốc độ của từng cuốn. Hết một chương tự sang chương kế tiếp (nếu đã có audio)."
        >
          <div className="divide-y divide-line">
            <Field label="Nhỏ dần trước khi hẹn giờ tắt" hint="Tiếng giảm êm để không giật mình tỉnh giấc.">
              <Segmented<"10" | "30" | "60">
                label="Độ dài nhỏ dần"
                value={fade}
                onChange={(value) => update({ sleepFadeSeconds: Number(value) })}
                options={[
                  { value: "10", label: "10 giây" },
                  { value: "30", label: "30 giây" },
                  { value: "60", label: "1 phút" },
                ]}
              />
            </Field>
            <Field label="Mỗi lần nghe thêm" hint="Lúc đang nhỏ dần, chạm phím hoặc chuột là được nghe thêm chừng này.">
              <Segmented<"5" | "10" | "15">
                label="Số phút nghe thêm"
                value={extend}
                onChange={(value) => update({ sleepExtendMinutes: Number(value) })}
                options={[
                  { value: "5", label: "5 phút" },
                  { value: "10", label: "10 phút" },
                  { value: "15", label: "15 phút" },
                ]}
              />
            </Field>
            <Field
              label="Tự tắt khi ngủ quên"
              hint="Phát liên tục mà không ai chạm máy chừng này thì nhỏ dần rồi dừng, và ghi lại chỗ đang nghe cho thẻ “Tối qua”."
            >
              <Segmented<"0" | "1" | "2" | "3">
                label="Tự tắt khi ngủ quên"
                value={String(preferences?.safetyStopHours ?? 2) as "0" | "1" | "2" | "3"}
                onChange={(value) => update({ safetyStopHours: Number(value) })}
                options={[
                  { value: "0", label: "Không" },
                  { value: "1", label: "1 giờ" },
                  { value: "2", label: "2 giờ" },
                  { value: "3", label: "3 giờ" },
                ]}
              />
            </Field>
            <Field
              label="Lịch đêm"
              hint="Bấm nghe trong khung giờ này thì tự hẹn giờ ngủ - khỏi phải nhớ bấm lúc buồn ngủ."
            >
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <Switch
                  id="sleep-schedule"
                  checked={Boolean(preferences?.sleepSchedule)}
                  onCheckedChange={(on) => update({ sleepSchedule: on ? { from: "22:00", to: "06:00", minutes: 30 } : null })}
                />
                {preferences?.sleepSchedule && (
                  <>
                    <input
                      type="time"
                      aria-label="Từ"
                      value={preferences.sleepSchedule.from}
                      onChange={(event) => event.target.value && update({ sleepSchedule: { ...preferences.sleepSchedule!, from: event.target.value } })}
                      className="tabular h-9 rounded-lg border border-line bg-panel px-2"
                    />
                    <span className="text-fg-2">đến</span>
                    <input
                      type="time"
                      aria-label="Đến"
                      value={preferences.sleepSchedule.to}
                      onChange={(event) => event.target.value && update({ sleepSchedule: { ...preferences.sleepSchedule!, to: event.target.value } })}
                      className="tabular h-9 rounded-lg border border-line bg-panel px-2"
                    />
                    <span className="text-fg-2">hẹn</span>
                    <select
                      aria-label="Số phút hẹn"
                      value={preferences.sleepSchedule.minutes}
                      onChange={(event) => update({ sleepSchedule: { ...preferences.sleepSchedule!, minutes: Number(event.target.value) } })}
                      className="h-9 rounded-lg border border-line bg-panel px-2"
                    >
                      {[15, 30, 45, 60].map((minutes) => (
                        <option key={minutes} value={minutes}>
                          {minutes} phút
                        </option>
                      ))}
                    </select>
                  </>
                )}
              </div>
            </Field>
            <Field
              label="Tự lùi khi nghe lại"
              hint="Dừng dưới 5 phút: không lùi. Từ 5 phút tới 1 giờ: lùi 10 giây. Lâu hơn (ngủ dậy): lùi 30 giây."
            >
              <span className="text-[13px] text-fg-2">Tự động</span>
            </Field>
          </div>
        </Section>
        <Section
          id="phone"
          title="Điện thoại"
          description="Nghe tiếp trên điện thoại Android: tải sách về để nghe không cần mạng, chỗ đang nghe và dấu trang tự đồng bộ hai chiều."
        >
          <PhoneSync />
        </Section>
        <Section title="Phím tắt" description="Dùng được ở mọi màn hình, trừ khi đang gõ chữ.">
          <dl className="max-w-md space-y-2.5 text-sm">
            {SHORTCUTS.map(([keys, label]) => (
              <div key={label} className="flex items-center justify-between gap-4">
                <dt className="text-fg-2">{label}</dt>
                <dd className="flex items-center gap-1 text-fg-2">{keys}</dd>
              </div>
            ))}
          </dl>
        </Section>
        <Section title="Giới thiệu">
          <p className="text-sm text-fg-2 text-pretty">
            Ebook Reader {info?.version} - studio sách nói tiếng Việt chạy hoàn toàn trên máy của bạn: phân tích truyện, phân vai, thu âm và
            kiểm tra từng câu.
          </p>
        </Section>
      </div>
    </div>
  );
}
