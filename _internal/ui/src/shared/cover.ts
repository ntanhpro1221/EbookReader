// Bìa sách tự sinh: sách TXT không có ảnh bìa, nên mỗi cuốn nhận một cặp màu cố định băm từ tên (cùng tên,
// cùng bìa, mọi lần mở). Bảng màu là các tông đá quý đậm, đủ tương phản với chữ trắng ở mọi cặp.

const PALETTES: [string, string, string][] = [
  ["#1f3b57", "#0f1f30", "#f2a93f"],
  ["#4a2345", "#241124", "#f7b9c4"],
  ["#1d4a43", "#0d2622", "#8fe0c6"],
  ["#50301c", "#28170c", "#f2c078"],
  ["#2d2f5c", "#15162e", "#b7b9ff"],
  ["#5a2626", "#2d1111", "#ffb199"],
  ["#1f4d2c", "#0e2615", "#b8e986"],
  ["#3d3d46", "#1b1b20", "#e8d5a3"],
  ["#123f5c", "#081f2e", "#7fd1ff"],
  ["#4b3a14", "#241b07", "#ffd76a"],
];

function hash(text: string): number {
  let value = 2166136261;
  for (let index = 0; index < text.length; index += 1) {
    value ^= text.charCodeAt(index);
    value = Math.imul(value, 16777619);
  }
  return value >>> 0;
}

export interface CoverStyle {
  from: string;
  to: string;
  ink: string;
  seed: number;
}

export function coverStyle(title: string): CoverStyle {
  const seed = hash(title.trim().toLowerCase());
  const [from, to, ink] = PALETTES[seed % PALETTES.length];
  return { from, to, ink, seed };
}

/** Tên sách tách phần chính và phần phụ ("Throne of Magical Arcana · Tập 16" -> ["Throne of Magical Arcana", "Tập 16"]). */
export function splitTitle(title: string): [string, string] {
  const match = title.match(/^(.*?)\s*[·|:—–-]\s*(Tập|Quyển|Phần|Vol\.?|Book)\s*(.+)$/i);
  if (match) return [match[1].trim(), `${match[2]} ${match[3]}`.trim()];
  return [title.trim(), ""];
}

const STOPWORDS = new Set(["the", "and", "của", "và", "những", "các", "một"]);

/** Chữ trên bìa nhỏ: số tập nếu là sách trong một bộ ("16"), không thì hai chữ cái đầu. */
export function coverLabel(title: string): string {
  const [main, sub] = splitTitle(title);
  const volume = sub.match(/(\d+)/);
  if (volume) return volume[1];
  return main
    .split(/\s+/)
    .filter((word) => word.length > 2 && !STOPWORDS.has(word.toLowerCase()))
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase() ?? "")
    .join("");
}

const artworkCache = new Map<string, string>();

/** Ảnh bìa PNG 512 px cho điều khiển media của hệ điều hành (Windows, màn hình khoá) - vẽ cùng kiểu với BookCover. */
export function coverArtwork(title: string): string | undefined {
  const cached = artworkCache.get(title);
  if (cached) return cached;
  if (typeof document === "undefined") return undefined;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 512;
  const context = canvas.getContext("2d");
  if (!context) return undefined;
  const style = coverStyle(title);
  const [main, sub] = splitTitle(title);
  const gradient = context.createLinearGradient(0, 0, 512 * 0.42, 512);
  gradient.addColorStop(0, style.from);
  gradient.addColorStop(1, style.to);
  context.fillStyle = gradient;
  context.fillRect(0, 0, 512, 512);
  context.strokeStyle = style.ink;
  context.lineWidth = 3;
  [0.28, 0.46, 0.64, 0.82, 1.0].forEach((radius, index) => {
    context.globalAlpha = 0.09 + index * 0.025;
    context.beginPath();
    context.arc(style.seed % 2 ? 512 : 0, 512, radius * 512, 0, Math.PI * 2);
    context.stroke();
  });
  context.globalAlpha = 1;
  context.fillStyle = "#ffffff";
  context.font = '700 58px "Be Vietnam Pro", "Segoe UI", sans-serif';
  const words = main.split(/\s+/);
  const lines: string[] = [];
  let line = "";
  for (const word of words) {
    const attempt = line ? `${line} ${word}` : word;
    if (context.measureText(attempt).width > 432 && line) {
      lines.push(line);
      line = word;
    } else {
      line = attempt;
    }
  }
  if (line) lines.push(line);
  lines.slice(0, 5).forEach((text, index) => context.fillText(text, 40, 96 + index * 66));
  if (sub) {
    context.font = '600 34px "Be Vietnam Pro", "Segoe UI", sans-serif';
    const width = context.measureText(sub.toUpperCase()).width;
    context.fillStyle = "rgb(0 0 0 / 0.28)";
    context.fillRect(36, 430, width + 24, 50);
    context.fillStyle = style.ink;
    context.fillText(sub.toUpperCase(), 48, 467);
  }
  try {
    const url = canvas.toDataURL("image/png");
    artworkCache.set(title, url);
    return url;
  } catch {
    return undefined;
  }
}
