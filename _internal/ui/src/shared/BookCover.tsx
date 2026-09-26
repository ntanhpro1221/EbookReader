import { cn } from "@/shared/cn";
import { coverStyle, splitTitle } from "@/shared/cover";

// Bìa vuông kiểu album sách nói. Hoạ tiết là các vòng sóng âm lan ra từ góc - thứ duy nhất sách TXT
// "có" là giọng đọc, nên bìa vẽ giọng đọc.

const STOPWORDS = new Set(["the", "and", "của", "và", "những", "các", "một"]);

export function BookCover({
  title,
  size = "md",
  className,
}: {
  title: string;
  size?: "xs" | "sm" | "md" | "lg" | "xl";
  className?: string;
}) {
  const style = coverStyle(title);
  const [main, sub] = splitTitle(title);
  const text = {
    xs: "hidden",
    sm: "hidden",
    md: "text-[15px] leading-[1.15]",
    lg: "text-[19px] leading-[1.12]",
    xl: "text-[24px] leading-[1.1]",
  }[size];
  const pad = { xs: "p-1", sm: "p-1.5", md: "p-3.5", lg: "p-4", xl: "p-5" }[size];
  const rings = [0.28, 0.46, 0.64, 0.82, 1.0];
  const initials = main
    .split(/\s+/)
    .filter((word) => word.length > 2 && !STOPWORDS.has(word.toLowerCase()))
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase() ?? "")
    .join("");
  return (
    <div
      className={cn("relative aspect-square shrink-0 overflow-hidden rounded-lg shadow-card", className)}
      style={{ background: `linear-gradient(155deg, ${style.from} 0%, ${style.to} 100%)` }}
      aria-hidden
    >
      <svg className="absolute inset-0 size-full" viewBox="0 0 100 100" preserveAspectRatio="none">
        {rings.map((radius, index) => (
          <circle
            key={radius}
            cx={style.seed % 2 ? 100 : 0}
            cy={100}
            r={radius * 100}
            fill="none"
            stroke={style.ink}
            strokeOpacity={0.09 + index * 0.025}
            strokeWidth={0.6}
          />
        ))}
      </svg>
      <div className={cn("relative flex h-full flex-col justify-between", pad)}>
        {size === "xs" || size === "sm" ? (
          <span className="m-auto font-bold tracking-tight" style={{ color: style.ink, fontSize: size === "xs" ? 11 : 14 }}>
            {initials}
          </span>
        ) : (
          <>
            <span className={cn("line-clamp-4 font-bold tracking-tight text-white", text)}>{main}</span>
            <div className="flex items-end justify-between gap-2">
              {sub ? (
                <span
                  className="rounded-md px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider"
                  style={{ color: style.ink, background: "rgb(0 0 0 / 0.28)" }}
                >
                  {sub}
                </span>
              ) : (
                <span />
              )}
              <span className="flex h-4 items-end gap-[2px] opacity-80" style={{ color: style.ink }}>
                <span className="h-2 w-[3px] rounded-sm bg-current" />
                <span className="h-4 w-[3px] rounded-sm bg-current" />
                <span className="h-3 w-[3px] rounded-sm bg-current" />
              </span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
