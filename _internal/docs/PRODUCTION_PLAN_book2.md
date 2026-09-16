# Kế hoạch chạy cuốn 2: 915 chương, 21 lô (lô 6 lớn gộp ba lô cũ)

Nguồn: `D:/Novels/Ebook Reader/Text_Tmp` — chủ sách chỉ định 2026-09-13 22:5x (*"lấy tài liệu ở đây mà dev"*)
sau khi nguồn cuốn 1 (`D:/Novels/Tools/Text`, 478 chương) vào Thùng rác lúc 22:25. Không chung một byte với
cuốn 1: 478/478 file khác. Đây là một cuốn khác — "Chương 01 - Giàn hỏa thiêu rực cháy".

Gốc sách là tham số (`scripts/book_paths.py`): root `D:/Novels/Audiobooks/book2`, tag `v0.3.0-loNN`,
kế hoạch này. Cuốn 1 giữ nguyên tại `D:/Novels/Audiobooks/_versions` + `_book` (253 chương), quay lại bằng
`source scripts/book1.env`.

## Toàn cảnh

```
915 chương · 2.417.255 từ · 84.211 segment
23 lô, mỗi lô ~8 giờ máy (~3.700 segment)      <- bảng gốc 13-09
21 lô từ 16-09: lô 6 = 6+7+8 cũ, lô 9..23 cũ đánh số lại thành 7..21
tổng ~182 giờ máy  ≈  7,6 ngày chạy liên tục
```

"Giờ máy" trong bảng là mô hình cũ 7,78 giây/đoạn. **Đo thật** trên lô 3–5 (một lô ~3.700 đoạn):
phân tích ~4,5 giờ (cả lô, trước khi đoạn nào được thu) + thu ~5,1 giờ khi máy rảnh ≈ **9,6–9,8 giờ**,
tức ~380 đoạn/giờ. Khi có người dùng máy, bước thu nhường (`yield_heavy`) và chậm còn ~2/3.

Sinh bằng `scripts/plan_batches.py "D:/Novels/Ebook Reader/Text_Tmp" --hours 8` (cân theo giờ máy, cùng
lý do với cuốn 1 — xem PRODUCTION_PLAN.md). `check_sources.py`: 915 chương chia đoạn được hết.

| lô | chương | số chương | segment | giờ máy | |
|---|---|---|---|---|---|
| 1 | 000..048 | 49 | 3.705 | 8,0 | |
| 2 | 049..098 | 50 | 3.749 | 8,1 | |
| 3 | 099..139 | 41 | 3.673 | 7,9 | |
| 4 | 140..179 | 40 | 3.680 | 8,0 | |
| 5 | 180..218 | 39 | 3.717 | 8,0 | |
| 6 | 219..343 | 125 | 11.129 | 24,0 | LỚN: gộp lô 6+7+8 cũ, chủ sách bảo 16-09 |
| 7 | 344..382 | 39 | 3.678 | 7,9 | (lô 9 cũ) |
| 8 | 383..420 | 38 | 3.683 | 8,0 | |
| 9 | 421..458 | 38 | 3.653 | 7,9 | |
| 10 | 459..497 | 39 | 3.705 | 8,0 | |
| 11 | 498..533 | 36 | 3.709 | 8,0 | |
| 12 | 534..569 | 36 | 3.654 | 7,9 | |
| 13 | 570..607 | 38 | 3.650 | 7,9 | |
| 14 | 608..644 | 37 | 3.716 | 8,0 | |
| 15 | 645..683 | 39 | 3.705 | 8,0 | |
| 16 | 684..723 | 40 | 3.663 | 7,9 | |
| 17 | 724..766 | 43 | 3.682 | 8,0 | |
| 18 | 767..810 | 44 | 3.742 | 8,1 | |
| 19 | 811..849 | 39 | 3.718 | 8,0 | |
| 20 | 850..885 | 36 | 3.690 | 8,0 | |
| 21 | 886..914 | 29 | 2.910 | 6,3 | |

## Đang ở đâu (cập nhật 11:40 ngày 2026-09-16)

```
sach da ghep : 180 chuong, 000..179, LIEN MACH (khong con lo nao)
lo 1  000..048  xong  (project lo: 48 completed + 1 failed -> chuong ay da co ban va/duc lai)
lo 2  049..098  xong  (48 + 2 failed, trong do 082 da duoc duc lai thanh cong 16-09 07:51)
lo 3  099..139  xong  (40 + 1 failed)
lo 4  140..179  xong  (40/40, khong chuong nao hong)
lo 5  180..218  DANG CHAY tu 08:04 ngay 16-09
lo 6  219..343  LON (125 chuong, 11.129 doan) - ranh gioi 5 tu tha, muc tieu xong sang thu 6 18-09
```

### Lô 6 lớn (quyết định 16-09 ~18:00)

Chủ sách bỏ nhịp tim (*"thôi dừng luôn không heartbeat gì nữa"*) rồi bảo: *"khởi tạo một lô chạy
thật lớn, căn thời gian xong đến tầm sáng thứ 6"*. Không ai trông thì không ai thả ranh giới giữa
các lô, nên một lô dài ~30 giờ giữ GPU làm việc tới khi có người quay lại.

Cỡ lô chọn bằng **gộp nguyên ba lô của bảng** (6+7+8 cũ = 219..343) chứ không cắt theo đồng hồ: vẫn
cân theo giờ máy như luật chia lô, và phần còn lại của bảng chỉ cần đánh số lại. Ước tính, bằng số đo
thật ở trên:

```
lo 5 thu xong           ~21:00 thu 4  (dang bi nhuong may luc chieu)
ranh gioi 5             ~3-3,5 gio: 12 chuong duc lai lo khac x ~12 phut + auto + va chuong hong
lo 6 bat dau            ~00:30 thu 5
  phan tich 11.129 doan ~13,5 gio   -> ~14:00 thu 5
  thu 11.129 doan       ~15,3 gio neu may ranh      -> ~05:30 thu 6
                        ~18 gio neu chieu toi thu 5 co nguoi dung may -> ~08:30 thu 6
```

**Rủi ro chưa đo:** chưa project nào vượt ~3.800 đoạn (lớn nhất cả hai cuốn: `lo04_b741b9848d`
3.795). Trong một lô 3.700 đoạn, giây/đoạn của 1/3 chương cuối **không** cao hơn 1/3 đầu (lô 3:
4,84 → 5,32; lô 4: 4,50 → 4,58 trung vị), nên không thấy dấu hiệu chi phí tăng theo vị trí — nhưng
11.129 là gấp ba cỡ đã từng chạy.

**Người gác thay nhịp tim:** sau khi ranh giới 5 thả lô 6, `bash scripts/boundary.sh 6 --wait-only`
chạy tiếp trong cùng một lệnh nền: chỉ bước 0 (lô chết giữa chừng thì `run` lại, tối đa hai lần),
ghi bằng chứng, rồi thoát — **không** áp, commit, đúc lại hay thả lô 7. Lệnh đã thả lúc 16-09:

```bash
bash scripts/boundary.sh 5 --recast auto 1:010 1:022 1:027 1:047 2:090 2:094 3:105 3:114 3:136 3:137 3:139 4:167 && bash scripts/boundary.sh 6 --wait-only
```

Danh sách lô khác đo lại lúc ~18:02 ngày 16-09 và **trùng hệt** số đo 13:00 — sách không đổi từ lần
ghép 08:04, nên nó đúng tới bước 7 của ranh giới 5. **Không** `--no-next`: 18 chương cuốn 1
(261..278) lùi lại sau lô 6 — lệnh mới của chủ sách thay kế hoạch dành cửa sổ này cho cuốn 1.

**Sáng thứ 6, trước ranh giới 6 thật:** tính lại danh sách lô khác
(`python scripts/one_person_one_voice.py | tail -1`), rồi `bash scripts/boundary.sh 6 --recast auto
<danh sách>` — bước 0 thấy lô đã xong nên đi thẳng. Lô 6 lớn gấp ba nên `auto` có thể tìm nhiều
chương hơn thường (mỗi chương ~12 phút); nếu cần GPU cho cuốn 1 thì thêm `--no-next`.

Chương `failed` trong project lô **không** có nghĩa là sách thiếu: bước 3/4/4b của ranh giới tạo
project vá / đúc lại riêng cho chúng, và bước 7 lấy bản **mới nhất** đã `completed`. Cách kiểm
đúng là đếm MP3 trên sách (`scripts/assemble_book.py --verify` và đếm khoảng trống), không phải đọc
trạng thái chương của project lô.

Lịch sử ranh giới đã chạy: 1→2, 2→3, 3→4, **4→5** (06:22–08:04 ngày 16-09, 1 giờ 42, bốn bản vá,
2.845 bài test xanh). Log của từng ranh giới ở `runtime/boundary_NN.log`; cách đọc ở
`docs/READING_A_BOUNDARY_LOG.md`.

**Ranh giới 5** (ghi 13:00, trước lệnh lô lớn; lệnh THẬT đã thả ở mục *"Lô 6 lớn"* phía trên, không
còn `--no-next`):

```bash
python scripts/one_person_one_voice.py | tail -1     # LẤY danh sách đúc lại lô khác
bash scripts/boundary.sh 5 --no-next --recast auto 1:010 1:022 ... 4:167   # kế hoạch cũ
```

**`--recast auto` KHÔNG đủ.** `auto` chỉ tìm va chạm cùng chương **trong lô vừa xong**; những chương
của lô **khác** phải gõ tay dạng `B:CCC`, và danh sách ấy do `one_person_one_voice.py` in ra ở dòng
cuối. Đo 13:00 ngày 16-09 nó là 12 chương (`1:010 1:022 1:027 1:047 2:090 2:094 3:105 3:114 3:136
3:137 3:139 4:167`) — **nhưng phải chạy lại đúng lúc thả ranh giới**, vì sách đổi thì danh sách đổi.
Ranh giới 4 đã làm đúng như thế và chữa được 9 người (xem `scripts/measure_did_the_recast_help.py`).

`--no-next` (kế hoạch cũ, đã bỏ 16-09 18:00) để **không** thả lô 6 ngay: cuốn 1 còn 18 chương
(261..278) và luật là không chạy hai cuốn cùng lúc, nên khoảng giữa hai lô là cửa sổ duy nhất của nó. Xem `docs/OPTIMISATION_QUEUE.md`
mục *"Cuốn 1 quay lại sản xuất"* cho hai việc của cuốn 1 và cái giá từng việc.

## Cách chạy

```bash
bash scripts/launch_batch.sh 1 --no-seed        # lô đầu của cuốn: không có lô trước để gieo
bash scripts/boundary.sh 1 --recast auto
```

Từ lô 2 ranh giới tự khởi động lô sau, gieo từ lô liền trước như cuốn 1. Mọi luật của cuốn 1 (ranh giới
8 bước, hàng chờ bản vá, `before_a_batch`, cây git sạch) áp y nguyên; chỉ gốc sách khác.

Ba cờ đáng biết:

- `--no-next`: làm hết mọi bước **nhưng không thả lô kế**. Dùng khi khoảng giữa hai lô phải dành cho
  việc khác — ví dụ 18 chương còn lại của cuốn 1, thứ mà bước 6 sẽ chiếm chỗ nếu không có cờ này.
- `--wait-only`: **chỉ bước 0** — canh lô (chết giữa chừng thì `run` lại, tối đa hai lần), ghi bằng
  chứng, thoát 0. Không áp, commit, đúc lại, thả lô hay ghép sách. Dùng khi không ai trông mà vẫn
  muốn lô không chết oan qua đêm (lô 6 lớn, 16-09).
- `EBOOK_COAUTHOR`: ghi đè dòng `Co-Authored-By` của những commit ranh giới tự tạo. **Không cần** đặt
  nữa; mặc định đã là model của phiên hiện tại (`Claude Opus 5` từ 16-09). Ví dụ cũ ở đây từng ghim
  `Claude Fable 5.1` và nó chỉ đúng cho phiên ngày 13–15/09.
