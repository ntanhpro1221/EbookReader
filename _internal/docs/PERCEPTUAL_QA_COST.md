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
