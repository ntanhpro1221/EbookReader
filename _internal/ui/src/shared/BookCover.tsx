import { cn } from "@/shared/cn";
import { coverLabel, coverStyle, splitTitle } from "@/shared/cover";
import { Vu } from "@/shared/ui";

// Bìa vuông kiểu album sách nói. Hoạ tiết là các vòng sóng âm lan ra từ góc - thứ duy nhất sách TXT
// "có" là giọng đọc, nên bìa vẽ giọng đọc.
//
// Bìa nhỏ (thanh phát, danh sách) không đủ chỗ cho tên: sách trong một bộ thì số tập là thứ phân biệt được các
// cuốn ("16", "18"), không phải hai chữ cái đầu giống hệt nhau của tên bộ.

export function BookCover({
  title,
  size = "md",
  playing = false,
  className,
}: {
  title: string;
  size?: "xs" | "sm" | "md" | "lg" | "xl";
  playing?: boolean;
  className?: string;
}) {
  const style = coverStyle(title);
  const [main, sub] = splitTitle(title);
  const small = size === "xs" || size === "sm";
  const text = {
    xs: "",
    sm: "",
    md: "text-[15px] leading-[1.15]",
    lg: "text-[19px] leading-[1.12]",
    xl: "text-[24px] leading-[1.1]",
  }[size];
  const pad = { xs: "p-1", sm: "p-1.5", md: "p-3.5", lg: "p-4", xl: "p-5" }[size];
  const rings = [0.28, 0.46, 0.64, 0.82, 1.0];
  return (
    <div
      className={cn("relative aspect-square shrink-0 overflow-hidden rounded-lg text-left shadow-card", className)}
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
        {small ? (
          <span
            className="m-auto font-bold leading-none tracking-tight"
            style={{ color: style.ink, fontSize: size === "xs" ? 12 : 17 }}
          >
            {coverLabel(title)}
          </span>
        ) : (
          <>
            <span className={cn("line-clamp-4 font-bold tracking-tight text-white", text)}>{main}</span>
            {sub ? (
              <span
                className="self-start rounded-md px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider"
                style={{ color: style.ink, background: "rgb(0 0 0 / 0.28)" }}
              >
                {sub}
              </span>
            ) : (
              <span />
            )}
          </>
        )}
      </div>
      {playing && (
        <span className="absolute bottom-1.5 right-1.5 grid place-items-center rounded-md bg-black/45 px-1 py-0.5" style={{ color: style.ink }}>
          <Vu className="h-3" />
        </span>
      )}
    </div>
  );
}
