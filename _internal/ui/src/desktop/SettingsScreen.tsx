import { FolderOpen, Monitor, Moon, Sun } from "lucide-react";
import type { ReactNode } from "react";
import { toast } from "sonner";
import { Button, Kbd } from "@/shared/ui";
import { cn } from "@/shared/cn";
import { pickFolder, useAppInfo, usePreferences } from "@/studio/data";

function Section({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <section className="grid grid-cols-[260px_minmax(0,1fr)] gap-8 border-b border-line py-7 last:border-b-0">
      <div>
        <h2 className="text-sm font-semibold">{title}</h2>
        {description && <p className="mt-1 text-xs leading-relaxed text-fg-2">{description}</p>}
      </div>
      <div>{children}</div>
    </section>
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
  return (
    <div className="mx-auto max-w-[920px] px-10 pb-16 pt-9">
      <h1 className="text-[28px] font-bold tracking-tight">Cài đặt</h1>
      <div className="mt-4">
        <Section title="Thư viện" description="Thư mục chứa các sách. Sách mới được tạo trong thư mục này.">
          <div className="flex items-center gap-2">
            <div className="flex h-10 min-w-0 flex-1 items-center rounded-lg border border-line bg-panel px-3 text-sm">
              <span className="truncate">{preferences?.libraryRoot}</span>
            </div>
            {info?.dialogs && (
              <Button icon={FolderOpen} onClick={() => void changeLibrary()}>
                Đổi
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
        <Section title="Nghe" description="Trình phát nhớ vị trí của từng cuốn và tốc độ bạn chọn lần gần nhất.">
          <ul className="space-y-2 text-sm text-fg-2">
            <li>Nghe lại sau hơn 5 phút tạm dừng: tự lùi 5 giây để bắt lại mạch truyện.</li>
            <li>Hẹn giờ tắt: tiếng nhỏ dần 10 giây trước khi dừng.</li>
            <li>Hết một chương tự sang chương kế đã nghe được.</li>
          </ul>
        </Section>
        <Section title="Phím tắt">
          <dl className="space-y-2.5 text-sm">
            {SHORTCUTS.map(([keys, label]) => (
              <div key={label} className="flex items-center justify-between">
                <dt className="text-fg-2">{label}</dt>
                <dd className="flex items-center gap-1 text-fg-3">{keys}</dd>
              </div>
            ))}
          </dl>
        </Section>
        <Section title="Giới thiệu">
          <p className="text-sm text-fg-2">
            Ebook Reader {info?.version} - studio sách nói tiếng Việt chạy hoàn toàn trên máy của bạn: phân tích truyện,
            phân vai, thu âm và kiểm tra từng câu.
          </p>
        </Section>
      </div>
    </div>
  );
}
