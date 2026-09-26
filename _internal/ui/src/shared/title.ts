import { useEffect } from "react";

export const APP_TITLE = "Ebook Reader";

/** Tên trang cụ thể (tên sách, tên chương...) cho thanh tiêu đề và thanh tác vụ.
 *
 * Vỏ ứng dụng đặt tên chung theo đường dẫn bằng `useLayoutEffect`; hook này dùng `useEffect` nên luôn chạy SAU và
 * thắng, kể cả khi dữ liệu đã có sẵn trong cache và cả hai chạy trong cùng một lần commit. Chưa có tên thì để nguyên
 * tên chung. */
export function usePageTitle(title: string | null | undefined) {
  useEffect(() => {
    if (title) document.title = `${title} · ${APP_TITLE}`;
  }, [title]);
}
