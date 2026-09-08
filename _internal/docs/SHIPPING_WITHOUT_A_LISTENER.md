# Xuất bản khi không có ai để hỏi

Chủ sách ra lệnh 2026-09-07: *"tôi không muốn phải tự nghe, project phải hoạt động toàn bộ cho
ra sản phẩm"*.

**Trạng thái: đã cài, 2026-09-08.** Phần dưới ghi cả thiết kế lẫn ba chỗ bằng chứng lật ngược
nó — hai trong ba là dự đoán của chính tôi bị số liệu bác bỏ, và chúng đáng đọc hơn phần đúng.

## Cơ chế, một câu

Khi vòng sửa đã cạn và **ASR là nhân chứng duy nhất** phàn nàn, máy ghi một hàng vào
`machine_audio_acceptances` nói "chưa ai nghe cái này" rồi để chương đi tiếp. Bản thu giữ
nguyên trạng thái `failed`, giữ nguyên mã cảnh báo, giữ nguyên điểm số — máy không đổi ý điều
gì, y hệt khi một người nghe đè lên nó.

Vào bằng `_grant_machine_acceptances` (pipeline.py), gọi đúng một chỗ: sau
`_repair_chapter_perceptual_candidates`, trước cổng chặn đầu tiên. Tắt bằng
`asr.ship_without_a_listener = False`.

## Hiện trạng đo được, và nó không giống thứ tôi tưởng

Đo trên alpha.60, chín chương. **Năm chương không xuất được MP3, do tám đoạn** — không phải
bốn chương / sáu đoạn như tôi ghi ở bản thiết kế trước. Quan trọng hơn con số: **cả tám đoạn
đều mang trạng thái `failed`**, không phải `warning`.

Điều đó giết phương án đầu tiên của tôi. Tôi định làm cơ chế chỉ dập *mã cảnh báo* và tuyệt
đối không đụng tới trạng thái, vì như thế "sạch" hơn. Nhưng cổng chặn chương đọc **trạng
thái**, nên một cơ chế như thế sẽ không gỡ được **một chương nào**. Nếu tôi viết trước rồi đo
sau thì đã có một cơ chế chạy đúng, test xanh, và vô dụng hoàn toàn.

Tám đoạn chia làm hai nhóm, và ranh giới sắc đến mức nó trở thành chính quy tắc:

| | mã lỗi | tín hiệu từ bộ sinh |
|---|---|---|
| **sáu đoạn** | chỉ `ASR_*` | **không có gì** — `generation_ceiling_hit` vắng mặt hoàn toàn |
| **hai đoạn** | có `ASR_*` | `generation_ceiling_hit = 1.0` |

Sáu đoạn đầu, đọc transcript là hiểu ngay vì sao ASR mù:

```
"Gia tộc Remis,"             → "Gia tộc dây mít"       sim 0,94   (d/r lẫn nhau)
"Bụi đá của Golem Silian,"   → "Bụi đá của go lem xí lên"  sim 0,89   (s/x đồng âm)
"Tên của cô là Selene Valkryn." → "Selenva L. Green."   sim 0,74   (tên bịa, đánh vần Latin)
"Dịch câu này: Kalbi kathub 'ala ramal." → "cao bê coa thúc à la răm mù."
"Khác gì ăn cướp không?"     → "Khắc gì ăn cướp không? Khắc gì ăn cướp không?"
"Tôi cười toe toét."         → "Tôi cười tué toách."
```

Lỗi **phiên âm**, không phải lỗi **đọc**. Năm vòng thu lại không đổi được gì vì chẳng có gì để
đổi — bản thu đúng ngay từ đầu, chỉ Whisper không đánh vần nổi một cái tên không tồn tại.

Hai đoạn còn lại thì ngược hẳn. `"Gì cơ?"` của chương 008 dài 1,92 giây, và Whisper nghe ra:

> *"Các bạn hãy đăng ký kênh để ủng hộ kênh của mình nhé."*

Một câu chào cuối video YouTube, WER 6,5. Đó không phải Whisper mù — đó là Whisper **rơi khỏi
âm thanh** vào thứ nó học được lúc huấn luyện, đúng như `ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE`
mô tả. Bản thu ấy hỏng thật, bộ sinh tự khai nó chạm trần khung, và máy phải im.

## Chỗ thứ hai số liệu bác bỏ tôi: ngưỡng nhịp đọc

Tôi định thêm một tiêu chí thứ ba, nghe rất hợp lý: **thời lượng bất khả**. `"Tiếp theo."` dài
1,92 giây là 4,7 ký tự/giây, trong khi băng bình thường là 12,5–24,5. Chắc chắn chạy loạn.

Đo trên 205 đoạn ngắn `verified` của chính alpha.60:

```
đoạn ngắn (<24 ký tự), verified:  min 1,56   p5 4,76   p50 10,94   p95 14,06
đoạn ngắn (<24 ký tự), failed:    min 2,08             p50  9,82
```

Và trong đám `verified` có `"Tiếp theo!"` — **4,76 ký tự/giây, 1,68 giây, sạch**. Gần như trùng
khít với `"Tiếp theo."` mà tôi vừa định gọi là chạy loạn. Thấp nhất là `"À!"` ở 1,56.

Hai phân bố chồng lên nhau hoàn toàn. Bất kỳ ngưỡng nào đặt ở đây cũng chỉ là con số tôi bịa
ra, và nó sẽ ném đi những bản thu hoàn hảo. Bỏ.

Cái thay thế nó không phải một ngưỡng mà là **lời tự khai của bộ sinh**:
`generation_ceiling_hit`. Không phải con số suy ra từ sóng âm mà là bộ sinh nói "tôi chạy hết
khung mà chưa dừng". Và nó chia đúng tám đoạn thành 6/2 như bảng trên.

## Chỗ thứ ba: một bảng riêng hay một cột `source`?

Bản thiết kế cũ nói *"Một bảng chung với cột `source` cũng được, miễn không có truy vấn nào
quên lọc"*. Khi đi tìm chỗ phải sửa thì thấy con số thật: **sáu cổng** đã lần lượt đè lên phán
quyết của người nghe, mỗi cổng được vá sau khi làm mất một chương —
`chapter_is_publishable`, `chapter_segments_have_current_audio_qa`,
`_listener_ruled_on_this_take`, tiền điều kiện perceptual,
`_high_quality_blocking_segment_warnings`, và bản quét recovery.

Sáu chỗ phải nhớ union bảng mới. Một cột `source` thì **không chỗ nào** phải sửa — lập luận
nghiêng hẳn về cột `source`.

Nhưng hai kiểu hỏng không ngang nhau:

- **quên union bảng** → một chương bị chặn oan. Ồn ào, thấy ngay, sửa được.
- **quên lọc cột `source`** → báo cáo nói "người đã nghe" về một bản thu chưa ai nghe. Im
  lặng, và là nói dối chủ sách về đúng thứ ông ấy vừa uỷ quyền.

Chọn kiểu hỏng ồn ào. Hai bảng.

Và để sáu chỗ ấy không thành bảy, thêm **một accessor duy nhất**:
`ProjectDB.ruled_segment_warnings()` / `ruled_segment_takes()` — hợp cả hai nguồn, và là hàm
mọi **cổng** phải gọi. `accepted_segment_warnings()` giữ nguyên nghĩa "một người đã nghe" và
là hàm mọi **báo cáo** phải gọi. Cổng thứ bảy gọi `ruled_` mà không cần biết có mấy bảng.

## Ba ràng buộc, và răng của chúng

1. **Chỉ khi ASR là nhân chứng duy nhất.** `MACHINE_ACCEPTABLE_SEGMENT_WARNINGS` toàn `ASR_*`.
   Cố ý loại: `PERCEPTUAL_NATURALNESS_REVIEW` (máy chấm khác), `TTS_PACE_OUTLIER` (đo trên sóng
   âm), `SEGMENT_FAILED`, `TTS_GENERATION_CEILING_REACHED`. Cộng thêm một lớp nữa ở
   `_grant_machine_acceptances`: chạm trần khung thì từ chối kể cả khi mã không nói ra.

2. **Chỉ sau khi hết ngân sách sửa.** Bảo đảm bằng **vị trí gọi**, không bằng một biến đếm ai
   đó phải nhớ tăng — hàm chạy sau mọi đường thu lại. Cấp sớm hơn là bỏ qua những vòng còn cứu
   được: đo được vòng 2 trở đi cứu 106/641 đoạn (16,5%).

3. **Không im lặng.** Ba lớp: một dòng log, một `db.event("warning",
   "MACHINE_ACCEPTED_WITHOUT_LISTENER", …)` kèm cả câu gốc lẫn câu nghe ra, và
   `unheard_segments` trong `audiobook_quality_report.json` của từng chương. Con số ấy đếm
   **lúc đọc báo cáo**, nên một người nghe sau đó thì đoạn ấy tự rụng khỏi danh sách.
   `scripts/machine_acceptances.py` in ra chúng kèm **mốc thời gian trong file MP3** — cột đắt
   nhất, vì có nó thì kiểm một đoạn mất năm giây, không có nó thì phải nghe cả chương, tức là
   không ai kiểm.

## Chạy thật, alpha.62 chương 021 — cả ba ràng buộc đứng vững

Lần đầu cơ chế nổ trên audio thật, 2026-09-08 16:24. Chương 021 có bốn đoạn `failed` ở
alpha.60; ở lượt này ba trong bốn **vẫn `failed` với đúng mã cũ**, tức không được bốc thăm cứu.

| ràng buộc | bằng chứng trên lượt chạy thật |
|---|---|
| chỉ khi ASR là nhân chứng duy nhất | cho qua 3 đoạn `failed` không tín hiệu bộ sinh; **bỏ qua** 4 đoạn `warning` mang mã vốn không chặn |
| chỉ sau khi hết ngân sách sửa | cấp sau `_repair_chapter_perceptual_candidates`, và cả ba đoạn đã đi hết vòng sửa |
| không im lặng | 3 dòng log, 3 `db.event`, `unheard_segments` liệt kê đúng 3 đoạn ấy trong báo cáo — và `[]` ở ba chương kia |

Và thứ đáng lo nhất đã không xảy ra: **không có cổng thứ bảy.** Cả sáu cổng đều tôn trọng chấp
nhận của máy. Chương ra MP3, mang theo ba đoạn chưa ai nghe, có mốc thời gian để nghe nếu muốn.

Ngoài lề: `"Tiếp theo."` lần này ra 0,48–0,56 giây, không chạm trần, nên nó rơi vào nhóm
`warning` không chặn và cơ chế đúng đắn không đụng tới. Nhưng đó là model khác chứ không phải
bản vá — xem [AUDIO_IS_NOT_ALWAYS_REPRODUCIBLE.md](AUDIO_IS_NOT_ALWAYS_REPRODUCIBLE.md).

## Hướng đã loại: thăng bản thu "ít tệ nhất"

Trong cả bốn ca thu lại, bản được giữ **không phải bản điểm cao nhất** máy đã tạo. Cám dỗ hiển
nhiên: hết ngân sách thì thăng bản tốt nhất trong đám.

**Không làm, vì đó là quyết định cố ý của người trước**, ghim bằng
`test_candidate_exhaustion_keeps_incumbent_and_uses_incumbent_evidence`. Và lý lẽ của nó đúng:
một bản thu đã trượt cổng không phải bằng chứng nó khá hơn — nó chỉ là một cách hỏng khác.
Thăng nó là đưa vào sách một bản thu **không phép kiểm nào tán thành**, dựa trên việc so hai
con số mà cả hai đều dưới ngưỡng.

Đêm 2026-09-07 tôi đã một lần đè lên đúng loại quyết định như thế — xem
[WHY_A_GOOD_TAKE_GETS_THROWN_AWAY.md](WHY_A_GOOD_TAKE_GETS_THROWN_AWAY.md) — nên lần này thiết
kế **theo** nó.

Hệ quả: `"Tiếp theo."` của chương 003 vẫn chặn. Nó chạm trần khung nên máy không cho qua, và
năm ứng viên thu lại (0,56–0,96 giây, ngắn hơn hẳn bản 1,92 giây đang giữ) đều trượt ASR nên
luật giữ-bản-đương-nhiệm giữ lại đúng bản chạy loạn. Đó là cái giá của việc không đè lên quyết
định kia, và tôi trả nó một cách có ý thức.

## Đo trên dữ liệu thật, và phần vẫn còn là dự phóng

Chạy đúng hàm cấp phép lên một **bản sao** cơ sở dữ liệu alpha.60 (`_internal` không bị đụng
tới), kết quả:

| | |
|---|---|
| cho qua | **6** — cả sáu đều `failed`, không đoạn nào có tín hiệu xấu từ bộ sinh |
| từ chối | **2** — `"Tiếp theo."` (ch003) và `"Gì cơ?"` (ch008), cả hai chạm trần khung |
| không đụng tới | 9 — đoạn `warning` mang mã vốn đã không chặn |
| **chương còn đoạn `failed`** | **5 → 2** |

Hai đoạn bị từ chối đúng là hai đoạn [bản vá trần khung](WHAT_BLOCKS_A_CHAPTER.md) vừa cho
phép thu lại — cơ chế và bản vá khớp nhau chứ không giẫm chân nhau.

Con số "không đụng tới" là kết quả của một lần đo cứu được một khiếm khuyết: bản đầu tiên cấp
**13** lượt, trong đó 7 lượt cho những đoạn `warning` chưa từng chặn gì. Cơ chế vẫn chạy đúng,
nhưng chương 007 và 009 - vốn xuất bản bình thường - sẽ mang nhãn "3 đoạn chưa ai nghe", và một
con số kêu ở chỗ không có gì sai thì lần sau không ai đọc nó nữa.

**Phần còn là dự phóng:** 5 → 2 đo trên bảng dữ liệu **cũ**. Nó chưa tính bản vá trần khung sẽ
làm gì với `"Gì cơ?"` ở lượt chạy mới - đoạn ấy trước đây có **0 ứng viên** và giờ được thu lại
năm vòng. Nếu một vòng ra bản sạch thì chương 008 xuất bản và còn **1** chương chặn; nếu không
thì vẫn **2**.

Ba lần trước tôi ngoại suy từ một cửa sổ không đại diện và sai cả ba (xem
[WORK_LOG.md](WORK_LOG.md)), nên phần dự phóng ấy chỉ có giá trị tới lượt chạy tiếp theo trên
chính chín chương này.

## Không gieo chấp nhận của máy sang bản sau — và vì sao đó không phải thiếu sót

`seed_listener_acceptances.py` và `port_listener_acceptances.py` chỉ đọc
`listener_audio_acceptances`. Bảng của máy **cố ý** nằm ngoài, và nếu ai đó thấy "thiếu" rồi
thêm vào thì sẽ hỏng một thứ khó thấy.

Phán quyết của người là **tài sản**: nghe một lần, dùng mãi, và mất nó thì phải bắt người nghe
lại từ đầu. Chấp nhận của máy là **kết luận của một lượt chạy cụ thể** — "lượt này đã tiêu hết
năm vòng sửa và không khá hơn được". Lượt sau phải tự tiêu ngân sách của nó rồi tự kết luận.

Cụ thể nó sẽ hỏng ở đâu: audio tái lập bit-exact khi seed không đổi, nên một chấp nhận mang
sang **sẽ khớp checksum**. Bản quét resume gọi `_listener_ruled_on_this_take`, thấy đã có phán
quyết, và **bỏ qua việc kiểm lại đoạn ấy**. Kết quả là lượt mới thừa hưởng lời đầu hàng của
lượt cũ mà chưa hề thử — đúng thứ ràng buộc số 2 sinh ra để chặn.

Người nghe thì ngược lại: họ phán về bản thu, và bản thu ấy vẫn thế.
