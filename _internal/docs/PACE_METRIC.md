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

**Chưa sạch hẳn**, và đã tìm hết cách rồi. Câu dày dấu vẫn dễ bị chặn hơn câu thưa dấu
khoảng **22 lần**, thay vì 260 lần. Phần tương quan dư là +0,12.

### Đã thử năm cấu trúc mô hình để khử nốt phần dư — đều thất bại

| mô hình | R² | còn lệch |
|---|---|---|
| phẳng, mỗi dấu câu | 0,976 | +0,32 |
| 3 lớp, mỗi dấu câu | 0,977 | +0,38 |
| 3 lớp, theo **nhóm** | 0,976 | +0,28 |
| **nhóm, một giá (đang dùng)** | 0,974 | **+0,119** |
| nhóm + căn bậc hai độ dài | 0,974 | +0,102 |
| nhóm + hằng số mỗi phát ngôn | 0,974 | +0,097 |

Hai kết luận:

1. **Mô hình 3 lớp bị bác hai lần** — trên từng dấu và trên nhóm. Cả hai lần nó khớp tốt
   hơn theo R² và lệch tệ hơn. Nếu ai đó định thử lại vì "chắc phải phân biệt dấu chấm với
   dấu phẩy chứ", thì đã thử rồi, hai lần, và sai cả hai.
2. **Không có chi phí cố định mỗi phát ngôn.** Giả thuyết "câu dày dấu thường ngắn nên bị
   im lặng đầu/cuối thổi phồng" nghe rất hợp lý, nhưng khớp ra hệ số **âm** (−0,052 s),
   tức vô nghĩa về vật lý, và chỉ đổi được +0,119 thành +0,097.

Phần dư +0,12 **không phải một số hạng nghỉ còn thiếu**. Nhiều khả năng văn bản dày dấu
câu — danh sách, tiêu đề, thoại bị ngắt — thật sự được đọc hơi khác, chứ không chỉ nghỉ
khác. Muốn đi tiếp thì phải có tai người nghe phân xử, không phải hồi quy thêm.

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

---

## Kiểm hằng số ngắt bằng khoảng lặng đo thật (2026-09-03)

`PAUSE_GROUP_SECONDS = 0.276` chưa bao giờ được đối chiếu với **khoảng lặng thật trong bản
thu**. Đo trên **1.289 bản thu khác nhau** (bỏ trùng theo `wav_sha256`), lặng đo bằng năng
lượng khung 20ms dưới -45 dB so với đỉnh:

| nhóm ngắt | n | lặng đo | mỗi nhóm | mô hình |
|---|---|---|---|---|
| 1 | 167 | 0,36s | 0,360 | 0,28 |
| 2 | 349 | 0,56s | 0,280 | 0,55 |
| 3 | 230 | 1,00s | 0,333 | 0,83 |
| 4 | 229 | 1,42s | 0,355 | 1,10 |
| 5 | 153 | 1,62s | 0,324 | 1,38 |
| 6 | 80 | 2,17s | 0,362 | 1,66 |
| 8 | 22 | 2,52s | 0,315 | 2,21 |

**Mô hình tuyến tính là đúng** — chi phí mỗi nhóm gần như hằng số trong vùng có dữ liệu dày.
(Ca "lệch 3×" thấy lúc đầu là một segment 25 nhóm với **n=1**; nhiễu, không phải quy luật.)

Hằng số thì hơi **nhỏ**: đo được 0,315–0,36s so với 0,276.

### Nhưng nâng nó lên làm mọi thứ tệ hơn

| hằng số | quá chậm | quá nhanh | tổng |
|---|---|---|---|
| **0,276** | 5 | 2 | **7** |
| 0,315 | 3 | 11 | 14 |
| 0,330 | 0 | 13 | 13 |

Trừ nhiều hơn thì "thời gian nói" còn lại của segment ngắn nhiều dấu câu bé đi, và nhịp vọt
lên: `Rare (Hiếm - B)` nhảy 21,19 → 25,38, từ đạt thành **quá nhanh**.

Hằng số và ngưỡng `pace_chars_per_second` là **một cặp đã khớp cùng nhau** khi bù ngắt được
đưa vào (tài liệu ở trên: trung vị dịch từ 14,50 lên 16,90 và ngưỡng trên phải nâng theo).
Đổi một nửa của cặp thì hỏng. **Giữ 0,276.**

## Chương không trôi đều — nhưng không phải do dấu câu

Công cụ `audit_audiobook.py` báo `CHAPTER_RATE_SPREAD` p05=3,30 p95=5,22 âm tiết/giây. Câu
hỏi là: chậm vì **đọc chậm** hay vì **ngắt nhiều**?

Đo bằng khoảng lặng thật, trên 64 segment của một chương:

| | p05 | trung vị | p95 | tản |
|---|---|---|---|---|
| nhịp thô (gồm ngắt) | 10,83 | 13,02 | 14,87 | 1,37× |
| nhịp nói (bỏ lặng đo) | 12,96 | 15,75 | 18,18 | **1,40×** |

Gần như không đổi. **Dấu câu không phải nguồn của độ tản** — chính giọng đọc nhanh chậm khác
nhau giữa các câu. `Rare (Hiếm - B)` ngắt 15% và nhịp nói 10,50 (chậm thật), trong khi mô
hình dự đoán nó ngắt 49,3%.

Lặng đo thật: trung vị **17,3%** mỗi segment, cao nhất 26,7% — thấp hơn nhiều so với mô hình.

## Ba segment không có audio: không phải một lớp, và "thử thêm" chỉ đúng với hai (đo 2026-09-04)

Ghi chép trước nói ba segment ấy là một lớp, bị cổng nhịp từ chối sau "5 đến 15 lần thử",
và cách chữa là "thử thêm hoặc đổi seed". Đọc log thì cả ba mệnh đề đều sai ở mức độ khác
nhau.

**Ngân sách là 4, không phải 5-15.** `tts.max_retries` = 4. Chúng cũng chưa từng vào đường
sửa candidate - bảng `segment_candidates` trống trơn cho cả ba - vì đường ấy dành cho lỗi
ASR và perceptual, còn nhịp thì hỏng ngay ở vòng tổng hợp chính.

**Các lần thử có khác nhau thật.** Seed lấy từ `stable_int("segment::...::{seed_salt}")` và
salt đổi theo vòng, nên bốn lần là bốn bản thu khác nhau - thấy rõ qua nhịp đo được.

**Và chúng không cùng một lớp:**

| segment | bốn lần thử | tốt nhất | cách cận 12.5 |
|---|---|---|---|
| c00010_s0000017 | 11.81 10.44 **12.47** 12.13 | 12.47 | **0.03** - trượt 0,24% |
| c00005_s0000013 | 11.05 11.82 12.25 12.25 | 12.25 | 2% |
| c00009_s0000008 | 9.22 10.51 10.70 9.36 | 10.70 | 17% |

Lấy độ lệch chuẩn của chính bốn lần ấy mà ước lượng (bốn mẫu là mỏng, con số này để phân
biệt "nửa sigma" với "ba sigma" chứ không phải để đặt cược):

| segment | xác suất mỗi lần | ngân sách 4 | 10 | 16 |
|---|---|---|---|---|
| c00010_s0000017 | 18,8% | 57% | **88%** | 96% |
| c00005_s0000013 | 12,3% | 41% | **73%** | 88% |
| c00009_s0000008 | ~0% | 0% | **0%** | 1% |

**Hai segment đầu trượt vì hết lượt, không phải vì giọng không đọc nổi.** Nâng
`tts.max_retries` từ 4 lên 10 chỉ tốn thêm lượt cho đúng những segment đang hỏng: cả sách
chỉ có 3 segment chạm tới ngân sách, 8 segment khác chạm cổng rồi qua ngay lần sau. Giá
phải trả là ~18 lượt tổng hợp thêm cho một quyển sách 948 segment.

**Segment thứ ba là một vấn đề khác hẳn.** Văn bản của nó là một thang bậc:

    Cấp Linh Hồn được phân loại theo hệ thống như sau: C » B » A » S » SS » SSS.

Giọng đọc *tên chữ cái*, không đọc văn xuôi. Thước đo ký tự/giây được hiệu chỉnh trên văn
xuôi nên định giá sai loại văn bản này theo đúng cấu tạo của nó - và không ngân sách nào
cứu được. Nới cận dưới thì vẫn sai, vì lý do đã đo ở trên: trong 807 segment đã nhận, không
segment nào rơi xuống dưới 12.5. Đây là một lớp văn bản mà cổng cần nhận ra, không phải một
cái cận cần nới.

`scripts/pace_retry_reachability.py` dựng lại bảng này từ log của bất kỳ lần chạy nào. Nó
chỉ tính những segment thực sự hết lượt, và biết cổng có hai cận - phiên bản đầu đọc mọi
lần từ chối thành "quá chậm" và biến một segment bị từ chối vì đọc *quá nhanh* (25.30,
27.51 so với cận trên 24.5) thành một segment luôn vượt cận dưới.

## Tổng hợp là tất định, nên "chạy lại" không bao giờ cứu được (xác nhận 2026-09-04)

alpha.43 hỏng chương 5 đúng trên `c00005_s0000013`, cùng segment đã chặn chương 5 của
alpha.32. Seed lấy từ `stable_int("segment::{stable_id}::{voice_key}::{seed_salt}")` — hoàn
toàn tất định — nên có một dự đoán kiểm được: bốn lần thử của alpha.43 phải ra **đúng** bốn
bản thu của alpha.32.

    alpha.32 :  11,05   11,82   12,25   12,25
    alpha.43 :  11,05   11,82   12,25   12,25

Giống đến từng chữ số thập phân, qua hai lần chạy khác engine ASR và khác `num_ctx`.

### Hai hệ quả

**1. Chạy lại quyển sách không bao giờ cứu những segment này.** Cùng bốn bản thu ấy hiện ra
mỗi lần. Đó là một tính chất tốt — kết quả tái lập được — nhưng nó xoá sổ "thử chạy lại xem
sao" khỏi danh sách cách chữa.

**2. Con số "88% / 73%" là một *tiên nghiệm*, không phải xác suất lặp lại được.** Nâng
`tts.max_retries` không phải là "quay xúc xắc thêm sáu lần"; nó là **rút thêm sáu bản thu cụ
thể, tất định**, vì attempt 5-10 dùng salt khác nên seed khác. Hoặc trong sáu bản ấy có một
bản vượt 12,5, hoặc không có bản nào — và một khi đã thử thì câu trả lời là **vĩnh viễn** cho
segment đó. Ước lượng ở trên đo khả năng dãy tất định ấy *có chứa* một bản đạt; nó không nói
"thử nhiều lần rồi sẽ được".

Điều này **củng cố** mục 4 chứ không làm yếu đi: vì chạy lại vô ích và vì cận dưới không được
nới, **thêm lượt thử là cách duy nhất còn lại** cho lớp này, ngoài việc sửa văn bản hoặc sửa
chính cổng.
