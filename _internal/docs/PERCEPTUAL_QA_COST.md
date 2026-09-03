# Giá của việc chấm điểm cảm thụ

UTMOSv2 là phép kiểm tra chất lượng duy nhất trong dự án nghe được bằng tai thay cho
người. Nó cũng là khoản tốn kém ngoài-TTS lớn nhất. Tài liệu này ghi những gì đã đo về
giá của nó.
## Ba lượt suy luận có cần không? (đo 2026-09-03)

`perceptual_qa.num_repetitions = 3` nằm trong settings mặc định mà không có ghi chú nào
nói tại sao. Đây là khoản tốn kém ngoài-TTS lớn nhất của một lần chạy: alpha.25 tốn
1934s cho 979 lượt chấm trên tổng 5100s, gần bằng toàn bộ TTS (2055s) và lớn hơn TTS ở
chương 8 (287.8s so với 262.6s). Nếu một lượt trả lời cùng một câu hỏi thì hai phần ba
số đó đang tiêu phí.

Đo trên 8 bản thu thật, cùng model, cùng seed, chỉ đổi `num_repetitions`:

| | |
|---|---|
| chênh lệch điểm lớn nhất | **0.208337** |
| chênh lệch trung bình | 0.099490 |
| ngưỡng quyết định (`review_delta`) | 0.8 |

Từng bản: 0.040, 0.048, 0.058, 0.064, 0.115, 0.118, 0.143, 0.208.

**Kết luận: giữ nguyên 3.** Một lượt lệch tới **26% biên quyết định**. Quyết định ở đây là
"tụt bao nhiêu so với bản xem trước của chính preset đó", nên một segment thực sự tụt 0.6
có thể ngẫu nhiên vượt ngưỡng, và một segment thực sự tụt 0.85 có thể ngẫu nhiên không
vượt. Đổi lấy 21 phút mỗi lần chạy để mất một phần tư biên an toàn của phép kiểm tra chất
lượng duy nhất nghe được bằng tai là không đáng — nhất là khi còn một khoản 2055s (40%)
lấy được mà không mất gì, bằng cách chồng lấn QA với TTS.

Cách đo: `scratchpad/utmos_reps.py`. Lưu ý cho người đo lại: `UTMOSNaturalnessVerifier`
nhận **toàn bộ** dict settings rồi tự đọc khoá `perceptual_qa` bên trong; truyền thẳng
dict con vào thì `enabled` thành False và `load()` lặng lẽ trả về False.

## Một worker chấm điểm tốn bao nhiêu RAM thật? (đo 2026-09-03)

`PERCEPTUAL_WORKER_RAM_GB` là con số mà `usable_for()` đem chia RAM trống để quyết định cấp
mấy worker. Nó ghi **1,0 GB**. Đo thật:

| phép đo | kết quả |
|---|---|
| RSS của một worker sau khi nạp UTMOSv2 | 1,87 GB |
| đỉnh RSS khi đang chấm | 2,18 GB |
| chi phí biên (nhìn RAM trống toàn máy), worker 1 | 1,76 GB |
| chi phí biên, worker 2 | 1,52 GB |
| chi phí biên, worker 3 | *nhiễu* (RAM trống **tăng** — job khác nhả bộ nhớ) |

Mọi con số đều cao hơn hẳn 1,0. Với 7,3 GB trống, pool đang cấp **5 worker**, tức khoảng
**8,8 GB worker trên 7,3 GB bộ nhớ**.

Đây không phải lỗi thông lượng, đây là **cách một lần chạy chết**. alpha.26 dừng ở 357/948
segment vì "available RAM 1.1 GB". Và phần chồng lấn mới - chấm điểm chạy cạnh ASR - làm
con số cũ nguy hiểm hơn nữa, vì pool không còn chờ Whisper nhả bộ nhớ trước khi đòi.

Đã sửa thành **1,75 GB**. Sai lệch về phía cao là hướng rẻ: quá lớn thì mất worker, quá nhỏ
thì mất cả lần chạy. Với 7,3 GB trống, giờ cấp 3 worker thay vì 5.

Con số "8 worker đạt 3,68×" vẫn đạt được: 8 worker cần `2 + 8×1,75 = 16 GB` trống, mà máy
31 GB lúc rảnh thì có. Pool chỉ thôi hứa điều đó khi bộ nhớ không có thật.

**Cần đo lại trên máy rảnh.** Lần đo này chạy song song với alpha.28, và số thứ ba đã bị
nhiễm. Cách đo: `scratchpad/worker_ram.py`.

## Pool từng tự chỉnh cỡ vào đúng vùng cấm chính nó

`usable_for()` chừa lại một hằng số **2,0 GB** cứng. `resources.min_free_ram_gb` là **3,5 GB**.
Và trong `AdaptiveResourceManager.decide()`, RAM trống ở hoặc dưới 3,5 GB là "memory
pressure", mà memory pressure tắt **cả hai**:

```python
allow_new_gpu_batch = not (foreground_gpu_pressure or memory_pressure or ...)
allow_cpu_heavy_work = not (foreground_cpu_pressure or ... or memory_pressure or ...)
```

Nên một pool chỉnh cỡ theo quy tắc cũ sẽ tiêu máy xuống còn 2,0 GB trống — tức **tự đặt
mình vào trạng thái cấm đúng loại việc nó sinh ra để làm**. Và từ khi chấm điểm chạy cạnh
ASR, hậu quả nặng hơn: `allow_new_gpu_batch` tắt theo, nên pool sẽ **làm nghẽn chính cái
ASR mà nó định nấp sau**.

Test `test_a_busy_machine_keeps_todays_behaviour_instead_of_stalling_asr` không bắt được
điều này, vì nó chỉ phủ quyết định **lúc khởi động**, không phủ trạng thái pool **tạo ra
sau khi đã chạy**.

Đã sửa: mức chừa lấy từ chính ngưỡng của van tiết lưu (`resources.min_free_ram_gb`), không
phải một con số do module này tự chọn. Với 7,3 GB trống: 2 worker, còn lại 3,8 GB — trên
ngưỡng. Một dự án nâng ngưỡng lên thì được pool nhỏ hơn, thay vì một pool cãi nhau với van
tiết lưu của chính nó.

Một test cũ vỡ vì việc này, và vỡ đúng: nó khẳng định 6 GB trống vẫn đủ cho hai worker —
điều chỉ đúng khi worker được tính 1,0 GB và mức chừa là 2,0. Ý định của test (nhiều chỗ
hơn thì nhiều worker hơn) giữ nguyên; con số sinh ra từ số học cũ thì bỏ.

## Cổng perceptual đòi tai người nghe nhiều hơn hẳn với đoạn ngắn (đo 2026-09-04)

`c00003_s0000014` — *"Tất cả đều đã ra đi."*, **1,5 giây** — chặn chương của nó ở **cả**
alpha.32 lẫn alpha.43, trong khi ASR nghe đúng từng chữ. Vài segment bị chặn khác cũng
ngắn. Đó là đủ dấu hiệu để hỏi cổng có thiên vị theo độ dài không.

Có, trên 2.282 phép chấm của alpha.32:

| độ dài | n | delta trung vị | **độ lệch chuẩn** | gắn cờ |
|---|---|---|---|---|
| <2s | 114 | −0,445 | **0,308** | **14,9%** |
| 2-3s | 395 | −0,389 | 0,276 | 8,4% |
| 3-5s | 502 | −0,386 | 0,247 | 2,2% |
| 5-8s | 490 | −0,388 | 0,209 | 1,0% |
| ≥8s | 781 | −0,397 | **0,189** | 1,8% |

**Trung vị phẳng** — từ −0,386 tới −0,445, không có xu hướng. Chỉ **độ tán** đổi, tăng 63%
khi đoạn ngắn lại. Nên đoạn ngắn *không phải điểm tệ hơn*; chúng **tán rộng hơn**, và một
ngưỡng tuyệt đối cố định thì hớt đúng cái đuôi ấy.

Hệ quả là chữ "tệ nhất" mang hai nghĩa khác nhau trong cùng một cổng: với đoạn dài nó nghĩa
là **1,5% dưới cùng**, với đoạn ngắn là **15% dưới cùng**.

### Nếu áp cùng một mức khắt khe thay vì cùng một con số

Trên đoạn ≥5s, −0,8 nằm ở *trung vị trừ 2,06 sigma*. Áp đúng 2,06 sigma ấy cho từng nhóm:

| độ dài | ngưỡng mới | gắn cờ nay → mới |
|---|---|---|
| <2s | −1,079 | 14,9% → **2,6%** |
| 2-3s | −0,958 | 8,4% → **0,8%** |
| 3-5s | −0,895 | 2,2% → 1,4% |
| 5-8s | −0,819 | 1,0% → 0,8% |
| ≥8s | −0,787 | 1,8% → **2,8%** |

Tổng: **80 → 39 lần gắn cờ.** Đọc cho đúng: đây **không phải nới lỏng**. Nó *siết* đoạn dài
(1,8% → 2,8%) và *nới* đoạn ngắn, để mức khắt khe như nhau ở mọi độ dài.

### Chưa phân giải được, và một phép thử rỗng

Phần tán thêm ở đoạn ngắn là **nhiễu của thước đo** hay là **chất lượng thật sự dao động
hơn**? Dữ liệu này không tách được, và điều đó quan trọng: nếu là cái sau thì cổng đang làm
đúng việc của nó.

Phép thử tự nhiên — so điểm giữa các bản thu **khác seed của cùng một câu** — trả về biên độ
**0,000 ở mọi nhóm**. Không phải vì thước đo ổn định, mà vì các hàng `quality_checks` lặp
lại đang chấm **đúng một file âm thanh**, không phải các bản thu khác nhau. Kết quả rỗng.
Ghi lại để người sau không thử lại đúng cách ấy; muốn phân giải thì phải **tự tổng hợp cùng
một câu ngắn nhiều lần với seed khác nhau rồi chấm**.

`scripts/perceptual_duration_bias.py` dựng lại toàn bộ bảng trên từ bất kỳ project nào.
