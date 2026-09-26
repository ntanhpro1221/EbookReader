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
