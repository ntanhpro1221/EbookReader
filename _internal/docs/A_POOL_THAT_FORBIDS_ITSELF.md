# Pool TTS tự định cỡ vào đúng trạng thái cấm nó chạy

Đo ngày 2026-09-09, giữa chương 007 của lô vá, khi lượt chạy đứng yên hơn nửa giờ với nhịp tim
vẫn 5 giây:

```
RAM trống                       2,85 GB
sàn của bộ điều tiết            3,50 GB   (resources.min_free_ram_gb)
pool TTS đang giữ               7,63 GB   (3 worker)
   nếu bỏ pool  -> trống 10,48 GB
   nếu 2 worker -> trống  5,39 GB
```

Dưới sàn, `decide()` báo `memory_pressure` và tắt **cả** `allow_new_gpu_batch` lẫn
`allow_cpu_heavy_work`. GPU đo được 0% và 4,6 W. Nói cách khác: **worker thứ ba chính là thứ
đẩy lượt chạy vào trạng thái không worker nào được chạy.**

## Vì sao pool không biết

`workers_for_vram` trong `tts_pool.py` định cỡ **chỉ theo VRAM**:

```python
budget = min(free_vram_mb, total_vram_mb - TTS_POOL_FOREGROUND_RESERVE_MB)
affordable = (budget - TTS_POOL_BASE_VRAM_MB) // TTS_POOL_WORKER_VRAM_MB
return min(ceiling, affordable)
```

Ba hằng số, cả ba là VRAM. Trong cả `tts_pool.py` **không có một số hạng RAM hệ thống nào** —
trong khi một worker TTS chiếm khoảng 2,5 GB RAM. Ba worker là ~7,6 GB mà phép tính trên không
nhìn thấy.

### Nhưng đường ống **biết** con số ấy — nó chỉ dùng theo một chiều

`pipeline._synthesis_pool_ram_reserve()` có tồn tại, và chú thích của nó đã đo sẵn:

> A synthesis worker measured 2.33 GB resident on alpha.47, the same order as a scoring one,
> so the scoring constant stands in for both rather than inventing a second number nobody
> re-measures.

Nhưng hàm ấy chạy **ngược chiều**: nó trả về `ceiling × PERCEPTUAL_WORKER_RAM_GB` để đưa cho
pool *cảm thụ* làm `reserve_ram_gb` — tức "pool TTS sắp đòi ngần này, đừng lấy". Nó bảo vệ pool
TTS khỏi pool cảm thụ, và không có chiều ngược lại: không ai bảo vệ cỗ máy khỏi pool TTS.

Nên bản vá **không cần phát minh hằng số mới**, và không nên: `PERCEPTUAL_WORKER_RAM_GB = 2,65`
đã đo theo đỉnh, đã được chính tác giả tuyên bố là dùng cho cả hai loại worker, và thêm một số
thứ hai chỉ tạo ra một số nữa không ai đo lại.

## Người trước đã sửa đúng lỗi này — ở pool bên cạnh

`perceptual_qa.py` có `usable_for()`, và chú thích của nó mô tả chính xác chuyện vừa xảy ra:

> The pool would size itself into the state that forbids the work it was built for.

Ở đó phép tính có số hạng RAM, lấy sàn từ chính bộ điều tiết chứ không tự đặt số:

```python
floor = settings["resources"]["min_free_ram_gb"]
spare = free_ram_gb - floor - reserve_ram_gb
affordable = int(max(0.0, spare) / PERCEPTUAL_WORKER_RAM_GB)   # 2,65 GB, đo theo ĐỈNH RSS
```

Và `PERCEPTUAL_WORKER_RAM_GB = 2.65` được đo tử tế: theo dõi đỉnh RSS của 31 worker trong 15
phút cho 1,72 min / 2,50 trung vị / 2,68 max, trong khi **một ảnh chụp** của 11 worker đang
sống cho trung vị 2,16 — thấp hơn hẳn. Bài học ghi ngay trong file: ngân sách phải dựng trên
đỉnh, mà ảnh chụp thì không thấy đỉnh.

Cách sửa đã tồn tại, đã đo, và nằm cách hai file. Nó chỉ chưa đi sang pool TTS.

Nói cho công bằng: đây không phải chuyện quên. Bộ điều tiết ra đời để nhường máy cho **người
khác**, và cả hai pool đều được dạy nhường cho nhau. Cái chưa ai viết là pool tự hỏi *chính tôi
có làm cỗ máy tụt xuống dưới sàn không* — và câu hỏi ấy chỉ thành cấp bách khi có một lô 13 giờ
chạy cạnh một phiên Unity, tức là chỉ từ hôm nay.

## Cái này không mâu thuẫn với [THE_MACHINE_IS_SHARED.md](THE_MACHINE_IS_SHARED.md), nó sửa nó

Tài liệu kia quy 64% thời gian bị hãm cho Unity và Rider (~9,5 GB). Đúng nhưng thiếu: đường
ống **tự** giữ 7,6 GB, và trên máy 31,3 GB thì hai bên cộng lại mới vượt ngưỡng. Bỏ một trong
hai là đủ:

```
đóng Unity        -> trống ~12,4 GB   không hãm
pool còn 2 worker -> trống  ~5,4 GB   không hãm
```

Cái thứ nhất là quyết định của chủ máy. Cái thứ hai là việc của mã.

## Điều chưa đo, và đừng nói như đã đo

Hai worker chạy liên tục **có** nhanh hơn ba worker đứng 60% thời gian không? Rất có khả năng,
nhưng đó là dự đoán. Phép đo đúng là chạy cùng một chương hai lần với `pool_workers` 2 và 3
trên cùng mức chiếm RAM, rồi so segment/phút — chứ không phải so hai chương khác nhau.

Cũng chưa đo: **đỉnh** RSS của worker TTS. Con số 2,5 GB ở trên là ảnh chụp, và perceptual_qa
đã ghi rõ ảnh chụp thấp hơn đỉnh khoảng 20%. Ngân sách phải dùng đỉnh.

Chưa vá. `tts_pool.py` và `pipeline.py` đều nằm trong `QUALITY_IMPLEMENTATION_FILES`.
