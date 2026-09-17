# Kế hoạch chạy cuốn 2: 915 chương, 22 lô (lô 6 lớn gộp hai lô cũ)

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
22 lô từ 17-09: lô 6 = 6+7 cũ, lô 8..23 cũ đánh số lại thành 7..22
               (16-09 từng là 21 lô với lô 6 = 6+7+8 cũ; máy tắt 12 giờ nên thu lại)
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
| 6 | 219..303 | 85 | 7.410 | 16,0 | LỚN: gộp lô 6+7 cũ (17-09, sau khi máy tắt; bản 16-09 là 219..343) |
| 7 | 304..343 | 40 | 3.719 | 8,0 | (lô 8 cũ) |
| 8 | 344..382 | 39 | 3.678 | 7,9 | |
| 9 | 383..420 | 38 | 3.683 | 8,0 | |
| 10 | 421..458 | 38 | 3.653 | 7,9 | |
| 11 | 459..497 | 39 | 3.705 | 8,0 | |
| 12 | 498..533 | 36 | 3.709 | 8,0 | |
| 13 | 534..569 | 36 | 3.654 | 7,9 | |
| 14 | 570..607 | 38 | 3.650 | 7,9 | |
| 15 | 608..644 | 37 | 3.716 | 8,0 | |
| 16 | 645..683 | 39 | 3.705 | 8,0 | |
| 17 | 684..723 | 40 | 3.663 | 7,9 | |
| 18 | 724..766 | 43 | 3.682 | 8,0 | |
| 19 | 767..810 | 44 | 3.742 | 8,1 | |
| 20 | 811..849 | 39 | 3.718 | 8,0 | |
| 21 | 850..885 | 36 | 3.690 | 8,0 | |
| 22 | 886..914 | 29 | 2.910 | 6,3 | |

## Đang ở đâu (cập nhật 11:40 ngày 2026-09-16)

```
sach da ghep : 180 chuong, 000..179, LIEN MACH (khong con lo nao)
lo 1  000..048  xong  (project lo: 48 completed + 1 failed -> chuong ay da co ban va/duc lai)
lo 2  049..098  xong  (48 + 2 failed, trong do 082 da duoc duc lai thanh cong 16-09 07:51)
lo 3  099..139  xong  (40 + 1 failed)
lo 4  140..179  xong  (40/40, khong chuong nao hong)
lo 5  180..218  xong 20:33 ngay 16-09 (39/39, khong chuong nao hong, auto 0 va cham)
lo 6  219..303  LON (85 chuong, 7.410 doan) - tha lai 17-09 ~10:30, muc tieu xong sang thu 6 18-09
```

### 17-09: máy tắt giữa ranh giới 5, và các bản đúc lại tối ấy ra TỆ HƠN

Máy tắt 22:46 ngày 16-09 (chủ sách tắt nhầm), bật lại 09:20 ngày 17-09. Ranh giới 5 đang ở bước 4b.
Watchdog lúc khởi động đã tự chạy nốt `lo03r_136`, còn chuỗi `boundary.sh` thì chết theo máy.

Đọc log thì thấy một lỗi khác, nặng hơn: `pin_the_book_cast.py --apply` **nổ ở mọi chương đúc lại**
(`ValueError: canonical_name and voice_key are both required`). Bước "bỏ pin nhãn không có trong nguồn"
(36f4db5, 16-09 10:22) gọi `set_locked_character_voice(name, "")`, mà hàm ấy từ chối giọng rỗng. Nó nổ
**trước** vòng ghim giọng đa số, và `launch_repair.sh` vẫn đi tiếp. Đo bằng
`measure_did_the_recast_help.py`:

```
010  tot 0 | xau 2 | khong ro 1      -> cat ra
027  0 nguoi doi giong               -> cat ra (khong giup ai)
094  tot 1 | xau 5 | khong ro 1      -> cat ra
105  tot 1 | xau 0 | khong ro 1      -> GIU
136  tot 0 | xau 1 | khong ro 5      -> cat ra
```

Luật dùng: **bản đúc lại chỉ lên sách khi nó giúp nhiều hơn nó hại.** Bốn project bị cắt được **dời**
(không xoá) sang `D:/Novels/Audiobooks/book2/_quarantine_2026-09-17/`, ra ngoài `_versions` để
`assemble_book` và `seed_chain` không thấy chúng. Sách giữ bản cũ của 010, 027, 094, 136.

Đã sửa: `pin_the_book_cast.unpin_character` ghi thẳng `locked_voice_key=''`. Bài test mới chạy đường
`--apply` trên `ProjectDB` thật, và đã thử đột biến (trả lại lời gọi cũ thì bài test đỏ đúng
`ValueError`). Chạy thử (không ghi) bản đã sửa trên `lo02r_094`: ANDRE, WOLF, MEKANZI, JULIAN được ghim
đúng giọng đa số. Nhưng CHRISTOPHER, LOTT, HERODOTUS, MAG vẫn **không ghim được**, vì người đang giữ
giọng ấy có cùng chương với họ ở đâu đó trong sách. Đó là giới hạn cũ: pin giữ chỗ trên cả cuốn, trong
khi luật chỉ cấm trùng giọng trong cùng một chương. Nên kể cả khi hết lỗi, đúc lại 094 cũng chưa chắc có lãi.

**Lô 6 thu lại còn 219..303** (6+7 cũ, 7.410 đoạn): mất 12 giờ thì 11.129 đoạn sẽ xong chiều tối thứ 6,
không phải sáng. Ước tính, lô bắt đầu ~10:50 thứ 5: phân tích ~9 giờ (→ ~20:00), thu ~10,2 giờ nếu máy rảnh
(→ ~06:00 thứ 6), ~11 giờ nếu tối thứ 5 có người dùng máy (→ ~07:00).

**Ranh giới 5 thả lại KHÔNG có danh sách lô khác.** 137, 139, 167 (chưa chạy) và 010, 027, 094, 136 (đã
cắt) để sáng thứ 6, **đo** bằng `measure_did_the_recast_help.py` rồi mới cho lên sách. Từ 21:34 ngày 17-09,
đúc lại đi qua `keep_the_chapter_cast.py`, tức chỉ đổi người cần đổi. Mô phỏng 8 chương ấy: về đa số 15,
giữ 34, không ghim 6 (người một chương). Xem trước bằng
`python scripts/keep_the_chapter_cast.py --chapters 010 027 094 136 137 139 167`. Bước 7 của ranh
giới 5 không có ai trông, nên không được ghép một bản đúc lại chưa đo. Lệnh đã thả 17-09:

```bash
bash scripts/boundary.sh 5 --recast auto && bash scripts/boundary.sh 6 --wait-only
```

### Lô 6 lớn (quyết định 16-09 ~18:00; cỡ lô sửa 17-09, xem mục trên)

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
