# Cảm xúc và cường độ thực sự làm gì trong sản phẩm

Đo trên **16953 segment đã phân tích** của các run thật, không phải suy đoán từ mã.

## Cảm xúc: 95,8% neutral — đúng thiết kế

| cảm xúc | số segment | tỉ lệ |
|---|---|---|
| neutral | 16246 | **95,8%** |
| angry | 227 | 1,3% |
| afraid | 164 | 1,0% |
| sad | 143 | 0,8% |
| surprised | 81 | 0,5% |
| happy | 46 | 0,3% |
| còn lại | 46 | 0,3% |

Khớp đúng yêu cầu đã đặt ra: *"người kể đa số là không có cảm xúc, đoạn nào rõ ràng, cần
thiết thì mới có thôi"*. Cảm xúc là gia vị, và nó đang được dùng đúng như gia vị.

## Cường độ: vô hiệu trên neutral, tức trên 95,8% cuốn sách

`prosody_targets("neutral", i)` trả về **y hệt nhau** với mọi `i` từ 0 đến 3:

| intensity | F0 (nửa cung) | dải | gain (dB) |
|---|---|---|---|
| 0 | +0,000 | 1,000 | +0,000 |
| 1 | +0,000 | 1,000 | +0,000 |
| 2 | +0,000 | 1,000 | +0,000 |
| 3 | +0,000 | 1,000 | +0,000 |

Đúng như thiết kế: PAD của `neutral` là gốc toạ độ, nhân với cường độ nào cũng ra gốc.

Hệ quả: phân bố cường độ trên đoạn neutral trông rất kỳ — **63,8% ở mức 1, 28,2% ở mức 3,
chỉ 0,3% ở mức 2**, tức model dùng thang 0–3 như thang nhị phân — nhưng **hoàn toàn vô
hại**, vì không con số nào trong đó chạm tới âm thanh.

Trên cảm xúc thật thì cường độ hoạt động đúng:

| cảm xúc | phân bố cường độ |
|---|---|
| afraid | 98,2% ở mức 2 |
| sad | 86,7% ở mức 2 |
| surprised | 82,7% ở mức 2 |
| angry | 34,8% mức 2, 64,8% mức 3 |
| excited | 100% mức 3 |

Và `sad` cho −0,66 / −1,34 / −2,06 nửa cung ở mức 1/2/3 — thang bậc đều, có nghĩa.

## Cảnh báo cho người đọc số liệu này

**Đừng kết luận chất lượng từ tỉ lệ trùng khớp cường độ.** Khi so hai cấu hình phân tích,
95,8% số segment là neutral, nơi cường độ vô hiệu — nên "chỉ trùng 20% cường độ" nghe như
thảm hoạ mà thực chất gần như toàn bộ phần lệch đó không phát ra tiếng.

Thứ đáng nhìn khi so hai cấu hình là **người nói** và **cảm xúc**, theo thứ tự đó. Sai người
nói là sai giọng nhân vật, thứ người nghe nhận ra ngay.

## Chế độ suy nghĩ của qwen3: CHƯA KẾT LUẬN, đừng đổi

Request phân tích hiện không đặt trường `think`, nên chế độ suy nghĩ **đang bật**. Đã thử đo
xem tắt đi có nhanh hơn không, và **hai phép đo mâu thuẫn nhau**:

| phép đo | kết quả |
|---|---|
| 1 prompt cố định, lặp 4 lượt xen kẽ | tắt nghĩ **nhanh gấp 1,71×** |
| 40 segment thật, 8 batch | tắt nghĩ **chậm hơn, 0,62×** |

Cả hai đều đo trong lúc một run khác đang dùng chung Ollama, nên chưa phép đo nào đáng tin.
**Phải đo lại khi GPU trống.**

Kể cả khi tốc độ ngã ngũ, vẫn còn rào chất lượng: hai chế độ chỉ **trùng 80% người nói** trên
40 segment thật. Một trong năm segment bị gán sai người nói là đổi giọng nhân vật giữa
chừng — không đánh đổi lấy tốc độ được.

`OLLAMA_NUM_PARALLEL` đọc từ log server đang chạy là **1**, xác nhận vì sao gửi request đồng
thời đo được đúng 1,00×. Ứng dụng tự khởi động Ollama bằng `Popen([exe, "serve"])` **không
truyền `env`**, nên đặt biến đó trong mã là làm được — nhưng cũng phải đo khi GPU trống, và
KV cache cho luồng thứ hai ở `num_ctx=16384` chưa chắc vừa 1,9 GB còn lại.
