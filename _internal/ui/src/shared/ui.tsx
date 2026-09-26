import * as DialogPrimitive from "@radix-ui/react-dialog";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { Loader2, X } from "lucide-react";
import type { ButtonHTMLAttributes, ComponentType, ReactNode } from "react";
import { cn } from "@/shared/cn";

type IconType = ComponentType<{ className?: string; strokeWidth?: number }>;

// ---- Nút --------------------------------------------------------------------------------------------------

type Variant = "primary" | "secondary" | "ghost" | "danger" | "outline";
type Size = "sm" | "md" | "lg";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-accent-ink hover:bg-accent-hover shadow-[0_1px_0_rgb(255_255_255/0.25)_inset]",
  secondary: "bg-panel-2 text-fg border border-line hover:bg-hover hover:border-line-strong",
  outline: "text-fg border border-line-strong hover:bg-hover",
  ghost: "text-fg-2 hover:bg-hover hover:text-fg",
  danger: "bg-danger-soft text-danger hover:bg-danger hover:text-white",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-[13px] gap-1.5 rounded-lg",
  md: "h-9 px-3.5 text-sm gap-2 rounded-lg",
  lg: "h-11 px-5 text-[15px] gap-2 rounded-xl",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  icon?: IconType;
  loading?: boolean;
}

export function Button({
  variant = "secondary",
  size = "md",
  icon: Icon,
  loading,
  className,
  children,
  disabled,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      className={cn(
        "inline-flex select-none items-center justify-center whitespace-nowrap font-medium transition-[background-color,color,border-color,transform] duration-150 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-45",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...rest}
    >
      {loading ? (
        <Loader2 className="size-4 animate-spin" />
      ) : Icon ? (
        <Icon className={size === "lg" ? "size-[18px]" : "size-4"} strokeWidth={2} />
      ) : null}
      {children}
    </button>
  );
}

export function IconButton({
  label,
  icon: Icon,
  className,
  size = "md",
  tone = "ghost",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string;
  icon: IconType;
  size?: "sm" | "md" | "lg";
  tone?: "ghost" | "solid";
}) {
  const box = size === "sm" ? "size-8" : size === "lg" ? "size-11" : "size-9";
  const glyph = size === "lg" ? "size-5" : "size-[18px]";
  return (
    <Tooltip label={label}>
      <button
        type="button"
        aria-label={label}
        className={cn(
          "inline-flex shrink-0 items-center justify-center rounded-lg transition-colors disabled:pointer-events-none disabled:opacity-40",
          tone === "ghost" ? "text-fg-2 hover:bg-hover hover:text-fg" : "bg-panel-2 text-fg hover:bg-hover",
          box,
          className,
        )}
        {...rest}
      >
        <Icon className={glyph} strokeWidth={2} />
      </button>
    </Tooltip>
  );
}

// ---- Tooltip ----------------------------------------------------------------------------------------------

export const TooltipProvider = TooltipPrimitive.Provider;

export function Tooltip({ label, children, side = "top" }: { label: ReactNode; children: ReactNode; side?: "top" | "bottom" | "left" | "right" }) {
  if (!label) return <>{children}</>;
  return (
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side={side}
          sideOffset={6}
          className="z-50 max-w-72 rounded-md bg-fg px-2.5 py-1.5 text-xs font-medium text-bg shadow-float data-[state=delayed-open]:animate-in"
        >
          {label}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}

// ---- Tiến độ ----------------------------------------------------------------------------------------------

export type Tone = "accent" | "success" | "danger" | "warning" | "muted";
const BAR: Record<Tone, string> = {
  accent: "bg-accent",
  success: "bg-success",
  danger: "bg-danger",
  warning: "bg-warning",
  muted: "bg-fg-3",
};

export function Progress({
  value,
  tone = "accent",
  running = false,
  size = "md",
  className,
  label,
}: {
  value: number;
  tone?: Tone;
  running?: boolean;
  size?: "xs" | "sm" | "md" | "lg";
  className?: string;
  label?: string;
}) {
  const height = { xs: "h-1", sm: "h-1.5", md: "h-2", lg: "h-2.5" }[size];
  const clamped = Math.max(0, Math.min(1, value));
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(clamped * 100)}
      className={cn("relative w-full overflow-hidden rounded-full bg-line", height, className)}
    >
      <div
        className={cn("relative h-full overflow-hidden rounded-full transition-[width] duration-700 ease-out", BAR[tone], running && "sheen")}
        style={{ width: `${clamped * 100}%` }}
      />
    </div>
  );
}

// ---- Trạng thái -------------------------------------------------------------------------------------------

export function Vu({ className }: { className?: string }) {
  return (
    <span className={cn("vu inline-flex h-3 items-end gap-[2px]", className)} aria-hidden>
      <span className="h-full w-[3px] rounded-sm bg-current" />
      <span className="h-full w-[3px] rounded-sm bg-current" />
      <span className="h-full w-[3px] rounded-sm bg-current" />
      <span className="h-full w-[3px] rounded-sm bg-current" />
    </span>
  );
}

const PILL: Record<Tone, string> = {
  accent: "bg-accent-soft text-accent-text",
  success: "bg-success-soft text-success",
  danger: "bg-danger-soft text-danger",
  warning: "bg-warning-soft text-warning",
  muted: "bg-hover text-fg-2",
};

export function StatusPill({
  label,
  tone,
  live = false,
  className,
}: {
  label: string;
  tone: Tone;
  live?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 text-xs font-medium",
        PILL[tone],
        className,
      )}
    >
      {live ? <Vu className="h-2.5" /> : <span className="size-1.5 rounded-full bg-current" />}
      {label}
    </span>
  );
}

// ---- Tab --------------------------------------------------------------------------------------------------

export const Tabs = TabsPrimitive.Root;
export const TabsContent = TabsPrimitive.Content;

export function TabsList({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <TabsPrimitive.List className={cn("flex gap-1 border-b border-line", className)}>{children}</TabsPrimitive.List>
  );
}

export function TabsTrigger({ value, children, count }: { value: string; children: ReactNode; count?: number }) {
  return (
    <TabsPrimitive.Trigger
      value={value}
      className="relative -mb-px inline-flex h-11 items-center gap-2 border-b-2 border-transparent px-3 text-sm font-medium text-fg-2 transition-colors hover:text-fg data-[state=active]:border-accent data-[state=active]:text-fg"
    >
      {children}
      {count !== undefined && (
        <span className="tabular rounded-full bg-hover px-1.5 py-px text-[11px] font-semibold text-fg-2">{count}</span>
      )}
    </TabsPrimitive.Trigger>
  );
}

// ---- Hộp thoại --------------------------------------------------------------------------------------------

export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  width = "max-w-lg",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  width?: string;
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-scrim backdrop-blur-[2px]" />
        <DialogPrimitive.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-line bg-panel p-6 shadow-float focus:outline-none",
            width,
          )}
        >
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <DialogPrimitive.Title className="text-lg font-semibold">{title}</DialogPrimitive.Title>
              {description && (
                <DialogPrimitive.Description className="mt-1 text-sm text-fg-2">{description}</DialogPrimitive.Description>
              )}
            </div>
            <DialogPrimitive.Close asChild>
              <button aria-label="Đóng" className="-m-1 rounded-md p-1 text-fg-3 hover:bg-hover hover:text-fg">
                <X className="size-5" />
              </button>
            </DialogPrimitive.Close>
          </div>
          {children}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

// ---- Khác -------------------------------------------------------------------------------------------------

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-hover", className)} />;
}

export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
  className,
}: {
  icon: IconType;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center px-6 py-14 text-center", className)}>
      <div className="mb-4 grid size-14 place-items-center rounded-2xl bg-accent-soft text-accent-text">
        <Icon className="size-7" strokeWidth={1.75} />
      </div>
      <h3 className="text-base font-semibold">{title}</h3>
      {children && <p className="mt-1.5 max-w-md text-sm leading-relaxed text-fg-2">{children}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex h-5 min-w-5 items-center justify-center rounded border border-line-strong bg-panel-2 px-1 font-sans text-[11px] font-medium text-fg-2">
      {children}
    </kbd>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="text-xs font-medium text-fg-3">{label}</div>
      <div className="tabular mt-1 truncate text-xl font-semibold tracking-tight">{value}</div>
      {hint && <div className="mt-0.5 truncate text-xs text-fg-2">{hint}</div>}
    </div>
  );
}

export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
}: {
  value: T;
  onChange: (value: T) => void;
  options: { value: T; label: string }[];
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-lg border border-line bg-panel-2 p-0.5">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          onClick={() => onChange(option.value)}
          className={cn(
            "h-7 rounded-md px-3 text-[13px] font-medium transition-colors",
            value === option.value ? "bg-panel text-fg shadow-card" : "text-fg-2 hover:text-fg",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
