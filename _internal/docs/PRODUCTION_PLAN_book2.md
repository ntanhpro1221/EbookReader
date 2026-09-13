# Kế hoạch chạy cuốn 2: 915 chương, 23 lô

Nguồn: `D:/Novels/Ebook Reader/Text_Tmp` — chủ sách chỉ định 2026-09-13 22:5x (*"lấy tài liệu ở đây mà dev"*)
sau khi nguồn cuốn 1 (`D:/Novels/Tools/Text`, 478 chương) vào Thùng rác lúc 22:25. Không chung một byte với
cuốn 1: 478/478 file khác. Đây là một cuốn khác — "Chương 01 - Giàn hỏa thiêu rực cháy".

Gốc sách là tham số (`scripts/book_paths.py`): root `D:/Novels/Audiobooks/book2`, tag `v0.3.0-loNN`,
kế hoạch này. Cuốn 1 giữ nguyên tại `D:/Novels/Audiobooks/_versions` + `_book` (253 chương), quay lại bằng
`source scripts/book1.env`.

## Toàn cảnh

```
915 chương · 2.417.255 từ · 84.211 segment
23 lô, mỗi lô ~8 giờ máy (~3.700 segment)
tổng ~182 giờ máy  ≈  7,6 ngày chạy liên tục
```

Sinh bằng `scripts/plan_batches.py "D:/Novels/Ebook Reader/Text_Tmp" --hours 8` (cân theo giờ máy, cùng
lý do với cuốn 1 — xem PRODUCTION_PLAN.md). `check_sources.py`: 915 chương chia đoạn được hết.

| lô | chương | số chương | segment | giờ máy | |
|---|---|---|---|---|---|
| 1 | 000..048 | 49 | 3.705 | 8,0 | |
| 2 | 049..098 | 50 | 3.749 | 8,1 | |
| 3 | 099..139 | 41 | 3.673 | 7,9 | |
| 4 | 140..179 | 40 | 3.680 | 8,0 | |
| 5 | 180..218 | 39 | 3.717 | 8,0 | |
| 6 | 219..261 | 43 | 3.694 | 8,0 | |
| 7 | 262..303 | 42 | 3.716 | 8,0 | |
| 8 | 304..343 | 40 | 3.719 | 8,0 | |
| 9 | 344..382 | 39 | 3.678 | 7,9 | |
| 10 | 383..420 | 38 | 3.683 | 8,0 | |
| 11 | 421..458 | 38 | 3.653 | 7,9 | |
| 12 | 459..497 | 39 | 3.705 | 8,0 | |
| 13 | 498..533 | 36 | 3.709 | 8,0 | |
| 14 | 534..569 | 36 | 3.654 | 7,9 | |
| 15 | 570..607 | 38 | 3.650 | 7,9 | |
| 16 | 608..644 | 37 | 3.716 | 8,0 | |
| 17 | 645..683 | 39 | 3.705 | 8,0 | |
| 18 | 684..723 | 40 | 3.663 | 7,9 | |
| 19 | 724..766 | 43 | 3.682 | 8,0 | |
| 20 | 767..810 | 44 | 3.742 | 8,1 | |
| 21 | 811..849 | 39 | 3.718 | 8,0 | |
| 22 | 850..885 | 36 | 3.690 | 8,0 | |
| 23 | 886..914 | 29 | 2.910 | 6,3 | |

## Cách chạy

```bash
bash scripts/launch_batch.sh 1 --no-seed        # lô đầu của cuốn: không có lô trước để gieo
EBOOK_COAUTHOR="Claude Fable 5.1 <noreply@anthropic.com>" bash scripts/boundary.sh 1 --recast auto
```

Từ lô 2 ranh giới tự khởi động lô sau, gieo từ lô liền trước như cuốn 1. Mọi luật của cuốn 1 (ranh giới
8 bước, hàng chờ bản vá, `before_a_batch`, cây git sạch) áp y nguyên; chỉ gốc sách khác.
