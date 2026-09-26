import * as Switch from "@radix-ui/react-switch";
import { useState, type ReactNode } from "react";
import { Segmented } from "@/shared/ui";
import { applyTheme, loadSettings, saveSettings, type PlayerSettings } from "./settings";

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-7">
      <h2 className="mb-2 px-1 text-xs font-semibold uppercase tracking-wider text-fg-3">{title}</h2>
      <div className="divide-y divide-line rounded-2xl border border-line bg-panel">{children}</div>
    </section>
  );
}

function Row({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 px-4 py-3.5">
      <div className="min-w-0">
        <div className="text-[15px] font-medium">{label}</div>
        {hint && <div className="mt-0.5 text-xs leading-snug text-fg-2">{hint}</div>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

export function SettingsScreen() {
  const [settings, setSettings] = useState<PlayerSettings>(loadSettings);
  const change = (patch: Partial<PlayerSettings>) => {
    const next = { ...settings, ...patch };
    setSettings(next);
    saveSettings(next);
    if (patch.theme) applyTheme(patch.theme);
  };
  return (
    <div className="px-4 pb-10 pt-4">
      <h1 className="text-2xl font-bold tracking-tight">Cài đặt</h1>

      <Group title="Hẹn giờ ngủ">
        <Row label="Lắc máy để nghe thêm" hint="Khi đang hẹn giờ, lắc nhẹ điện thoại hai lần - máy rung báo đã thêm giờ.">
          <Switch.Root
            checked={settings.shakeToExtend}
            onCheckedChange={(value) => change({ shakeToExtend: value })}
            aria-label="Lắc máy để nghe thêm"
            className="relative h-7 w-12 rounded-full bg-line-strong transition-colors data-[state=checked]:bg-accent"
          >
            <Switch.Thumb className="block size-6 translate-x-0.5 rounded-full bg-white shadow transition-transform data-[state=checked]:translate-x-[22px]" />
          </Switch.Root>
        </Row>
        <Row label="Mỗi lần thêm">
          <Segmented
            label="Mỗi lần thêm"
            value={String(settings.sleepExtendMinutes)}
            onChange={(value) => change({ sleepExtendMinutes: Number(value) })}
            options={[5, 10, 15].map((value) => ({ value: String(value), label: `${value}′` }))}
          />
        </Row>
        <Row label="Nhỏ dần trước khi tắt">
          <Segmented
            label="Nhỏ dần trước khi tắt"
            value={String(settings.sleepFadeSeconds)}
            onChange={(value) => change({ sleepFadeSeconds: Number(value) })}
            options={[10, 30, 60].map((value) => ({ value: String(value), label: `${value}s` }))}
          />
        </Row>
      </Group>

      <Group title="Nghe">
        <Row label="Tự lùi khi nghe lại" hint={`Tạm dừng quá ${settings.rewindAfterMinutes} phút rồi nghe tiếp thì lùi lại một chút để bắt mạch truyện.`}>
          <Segmented
            label="Tự lùi"
            value={String(settings.rewindSeconds)}
            onChange={(value) => change({ rewindSeconds: Number(value) })}
            options={[
              { value: "0", label: "Tắt" },
              { value: "5", label: "5s" },
              { value: "15", label: "15s" },
            ]}
          />
        </Row>
      </Group>

      <Group title="Giao diện">
        <Row label="Màu">
          <Segmented
            label="Màu"
            value={settings.theme}
            onChange={(value) => change({ theme: value })}
            options={[
              { value: "system", label: "Tự động" },
              { value: "light", label: "Sáng" },
              { value: "dark", label: "Tối" },
            ]}
          />
        </Row>
      </Group>

      <p className="mt-10 text-center text-xs text-fg-3">Ebook Reader · trình nghe sách nói</p>
    </div>
  );
}
