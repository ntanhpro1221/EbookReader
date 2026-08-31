# Phép đo tốc độ đọc: trừ chỗ nghỉ ra trước đã

## Vấn đề

Cổng chất lượng chặn segment vì "đọc quá chậm", nhưng nó **không đo tốc độ đọc** — nó đo
**mật độ dấu câu**.

`speakable_chars / duration` đếm ký tự chữ-số ở tử số, còn mẫu số là toàn bộ thời lượng
**kể cả những chỗ nghỉ mà dấu câu bắt buộc phải có**. Nên `( ) - : / .` cộng vào mẫu số mà
không cộng vào tử số.

Đo trên 3781 segment thật đã commit:

| mật độ dấu câu | chars/s trung vị | % bị chấm "quá chậm" |
|---|---|---|
| 0–4% | 14,83 | **0,1%** |
| 4–7% | 13,11 | 3,0% |
| 7–10% | 12,10 | **14,2%** |
| 10–15% | 11,22 | **26,1%** |

Tương quan **−0,62**. Một câu dày dấu câu có xác suất bị chặn cao gấp **260 lần** một câu
thưa dấu — vì nó **ngắt nghỉ đúng**.

Hậu quả thật: segment `'Rare (Hiếm - B): Mạnh hơn / khó tìm hơn.'` đo được 9,77 chars/s,
trượt sàn 10,5, bị sinh lại, không chia nhỏ được, fail, và **chặn cả chương không xuất
được MP3**.

## Hệ số lấy từ dữ liệu, không bịa

Hồi quy `duration ~ (số ký tự đọc được, số chỗ nghỉ)` trên chính corpus:

```
thời lượng ≈ 0,060 s/ký tự + 0,281 s/chỗ nghỉ
           => tốc độ nói thuần 16,7 ký tự/giây
```

## Đếm NHÓM, không đếm từng dấu — và vì sao R² không phải mục tiêu

Ba mô hình được khớp và so bằng **tương quan còn lại với mật độ dấu câu**, tức mức nhiễu còn
sót:

| mô hình | R² | tương quan còn lại |
|---|---|---|
| phẳng, mỗi dấu câu | 0,976 | +0,32 |
| **nhóm dấu liền nhau** | 0,974 | **+0,12** |
| 3 lớp (cuối câu / mệnh đề / khác) | **0,977** | +0,38 |

Mô hình **khớp tốt nhất theo R² lại là mô hình tệ nhì ở việc khử nhiễu**. Ghi lại rõ vì đây
là cái bẫy: R² đo "giải thích được bao nhiêu phương sai", còn thứ cần ở đây là "còn lệch
theo dấu câu bao nhiêu". Chọn nhầm tiêu chí thì chọn nhầm mô hình.

Nhóm thắng vì đúng vật lý: `):` hay ` — ` là **một** khoảng lặng, dù viết bằng mấy ký tự.

## Biên phải dịch theo, nếu không chỉ đổi chỗ lỗi oan

Bù nghỉ làm cả thang đo dịch lên:

| | p1 | trung vị | p99 |
|---|---|---|---|
| thô | 9,95 | 14,50 | 17,50 |
| đã bù | 12,49 | 16,90 | 22,43 |

Biên trên cũ 22,0 **chưa từng kích hoạt** (p99 thô chỉ 17,5). Giữ nguyên nó sau khi bù thì
nó bắt đầu bắt từ khoảng phân vị 98 — tức đổi lỗi oan ở đáy lấy lỗi oan mới ở đỉnh.

Biên mới đặt ở **cùng mức nghiêm ngặt**, không nới lỏng: 10,5 nằm ở phân vị 2 của phân bố
thô, 12,5 nằm ở phân vị 2 của phân bố đã bù. `slow` và `fast` scale theo cùng tỉ lệ vì
không đủ mẫu để khớp riêng (chỉ 10 và 12 mẫu).

## Kết quả

| mật độ dấu câu | CŨ | MỚI |
|---|---|---|
| 0–4% | 0,07% | 0,36% |
| 7–10% | 14,42% | **5,12%** |
| 10–15% | 25,29% | **8,05%** |

Segment làm hỏng chương: 9,77 (**chặn**) → 21,67 (**đạt**).

**Chưa sạch hẳn.** Câu dày dấu vẫn dễ bị chặn hơn câu thưa dấu khoảng **22 lần**, thay vì
260 lần. Đó chính là phần tương quan dư +0,12. Ai muốn đi tiếp có thể thử khớp chi phí nghỉ
riêng cho từng **lớp nhóm** (mô hình 3 lớp mới chỉ được thử trên từng dấu, chưa thử trên
nhóm).

## Trần tỉ lệ nghỉ

`MAX_PAUSE_FRACTION = 0.60`. Trên 3803 segment đủ dài để bị kiểm, ngân sách nghỉ đạt tối đa
**58,5%** thời lượng (p99,9 = 52%), nên trần này nằm trên mọi thứ tiếng nói thật tạo ra.

Nó tồn tại vì **audio không phải tiếng nói thật**: không có trần, một segment gần như toàn
im lặng sẽ bị trừ gần hết thời lượng, phần dư tí xíu biến một đoạn đọc chậm thành tốc độ
khổng lồ, và cổng sẽ báo "đọc quá nhanh" cho một segment mà lỗi thật là **gần như không
nói gì**.

## Việc này còn lộ ra: audio giả trong test chưa từng hợp lệ

Test mock dựng audio dài cố định (1,0 s / 1,92 s / 96000 mẫu) cho mọi độ dài văn bản. Một
câu 191 ký tự thành ra **nhanh gấp 6 lần người thật** — và không có gì phàn nàn, vì trần
cứng cũ đủ rộng để nó lọt.

Phép đo mới đẩy nó qua ngưỡng, làm lộ ra thứ vốn đã sai từ đầu. Đã sửa bằng cách suy thời
lượng từ văn bản (`_plausible_duration`); test nào cần thời lượng riêng thì vẫn tự truyền.

Bài học: **một stand-in vi phạm vật lý là một quả bom hẹn giờ.** Nó không tố cáo gì cho tới
khi có ai đó siết phép đo, rồi hỏng ở một chỗ chẳng liên quan gì đến thay đổi đó.
