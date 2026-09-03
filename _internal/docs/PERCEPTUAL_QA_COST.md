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
