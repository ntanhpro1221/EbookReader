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

## Đang ở đâu (cập nhật 11:40 ngày 2026-09-16)

```
sach da ghep : 180 chuong, 000..179, LIEN MACH (khong con lo nao)
lo 1  000..048  xong  (project lo: 48 completed + 1 failed -> chuong ay da co ban va/duc lai)
lo 2  049..098  xong  (48 + 2 failed, trong do 082 da duoc duc lai thanh cong 16-09 07:51)
lo 3  099..139  xong  (40 + 1 failed)
lo 4  140..179  xong  (40/40, khong chuong nao hong)
lo 5  180..218  DANG CHAY tu 08:04 ngay 16-09
```

Chương `failed` trong project lô **không** có nghĩa là sách thiếu: bước 3/4/4b của ranh giới tạo
project vá / đúc lại riêng cho chúng, và bước 7 lấy bản **mới nhất** đã `completed`. Cách kiểm
đúng là đếm MP3 trên sách (`scripts/assemble_book.py --verify` và đếm khoảng trống), không phải đọc
trạng thái chương của project lô.

Lịch sử ranh giới đã chạy: 1→2, 2→3, 3→4, **4→5** (06:22–08:04 ngày 16-09, 1 giờ 42, bốn bản vá,
2.845 bài test xanh). Log của từng ranh giới ở `runtime/boundary_NN.log`; cách đọc ở
`docs/READING_A_BOUNDARY_LOG.md`.

**Việc đang chờ ở ranh giới 5** (khoảng 22:10 ngày 16-09, khi lô 5 thu xong):

```bash
python scripts/one_person_one_voice.py | tail -1     # LẤY danh sách đúc lại lô khác
bash scripts/boundary.sh 5 --no-next --recast auto 1:010 1:022 ... 4:167
```

**`--recast auto` KHÔNG đủ.** `auto` chỉ tìm va chạm cùng chương **trong lô vừa xong**; những chương
của lô **khác** phải gõ tay dạng `B:CCC`, và danh sách ấy do `one_person_one_voice.py` in ra ở dòng
cuối. Đo 13:00 ngày 16-09 nó là 12 chương (`1:010 1:022 1:027 1:047 2:090 2:094 3:105 3:114 3:136
3:137 3:139 4:167`) — **nhưng phải chạy lại đúng lúc thả ranh giới**, vì sách đổi thì danh sách đổi.
Ranh giới 4 đã làm đúng như thế và chữa được 9 người (xem `scripts/measure_did_the_recast_help.py`).

`--no-next` để **không** thả lô 6 ngay: cuốn 1 còn 18 chương (261..278) và luật là không chạy hai
cuốn cùng lúc, nên khoảng giữa hai lô là cửa sổ duy nhất của nó. Xem `docs/OPTIMISATION_QUEUE.md`
mục *"Cuốn 1 quay lại sản xuất"* cho hai việc của cuốn 1 và cái giá từng việc.

## Cách chạy

```bash
bash scripts/launch_batch.sh 1 --no-seed        # lô đầu của cuốn: không có lô trước để gieo
bash scripts/boundary.sh 1 --recast auto
```

Từ lô 2 ranh giới tự khởi động lô sau, gieo từ lô liền trước như cuốn 1. Mọi luật của cuốn 1 (ranh giới
8 bước, hàng chờ bản vá, `before_a_batch`, cây git sạch) áp y nguyên; chỉ gốc sách khác.

Hai cờ đáng biết:

- `--no-next`: làm hết mọi bước **nhưng không thả lô kế**. Dùng khi khoảng giữa hai lô phải dành cho
  việc khác — ví dụ 18 chương còn lại của cuốn 1, thứ mà bước 6 sẽ chiếm chỗ nếu không có cờ này.
- `EBOOK_COAUTHOR`: ghi đè dòng `Co-Authored-By` của những commit ranh giới tự tạo. **Không cần** đặt
  nữa; mặc định đã là model của phiên hiện tại (`Claude Opus 5` từ 16-09). Ví dụ cũ ở đây từng ghim
  `Claude Fable 5.1` và nó chỉ đúng cho phiên ngày 13–15/09.
