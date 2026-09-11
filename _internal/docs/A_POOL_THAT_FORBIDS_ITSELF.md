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

## Đã đo: đỉnh RSS của worker TTS, và hằng số mượn hoá ra đúng

Theo dõi đỉnh RSS theo từng pid trong 25 phút, 422 lần lấy mẫu, bắt được **14 worker TTS** (pool
được dựng lại nhiều lần trong một chương):

```
đỉnh mỗi worker (GB):  0,75  1,99  2,42  2,45  2,45  2,51  2,55
                       2,57  2,58  2,64  2,67  2,68  2,68  2,68
   cực đại 2,68   trung vị 2,57
```

(0,75 là một worker chỉ bị bắt gặp lúc đang nạp model rồi pool đóng — đỉnh của nó chưa từng tới.
Giữ lại trong danh sách thay vì lọc đi, vì lọc theo "trông không hợp lý" là cách người ta bịa ra
số liệu.)

So với con số người trước đo cho worker **cảm thụ** — 2,68 cực đại, 2,50 trung vị, trên 31
worker trong 15 phút — hai phân bố **gần như trùng nhau**. Nên quyết định "dùng chung
`PERCEPTUAL_WORKER_RAM_GB = 2,65` cho cả hai loại thay vì đẻ thêm một số nữa không ai đo lại"
không chỉ tiện, nó **đúng**: 2,65 nằm ngay dưới đỉnh 2,68 của worker TTS, đúng cái lề mà tác giả
kia chọn cho worker cảm thụ.

Cùng phép đo ấy cho một con số thứ hai: **36,5% thời gian, RAM trống nằm dưới sàn 3,5 GB.**

## Điều chưa đo, và đừng nói như đã đo

Hai worker chạy liên tục **có** nhanh hơn ba worker đứng 60% thời gian không? Rất có khả năng,
nhưng đó là dự đoán. Phép đo đúng là chạy cùng một chương hai lần với `pool_workers` 2 và 3
trên cùng mức chiếm RAM, rồi so segment/phút — chứ không phải so hai chương khác nhau.

(Chỗ này trước ghi "chưa đo đỉnh RSS của worker TTS". Đã đo — xem mục trên. Ảnh chụp cho
2,43–2,67 và đỉnh cho 2,68, tức chênh nhau ít hơn nhiều so với 20% mà perceptual_qa cảnh báo;
lý do có lẽ là worker TTS nạp model xong thì gần như không phình thêm, khác worker chấm điểm.)

Chưa vá. `tts_pool.py` và `pipeline.py` đều nằm trong `QUALITY_IMPLEMENTATION_FILES`.

## Lô 4: kho nam KÍN HẲN, và bộ cấp phát dồn tám người vào một bậc (2026-09-11, 07:30)

Lô 4 xong 25/27. Đo kho giọng, và đây là bằng chứng ở quy mô cho
`patch_a_step_remembers_every_holder` — đo **trước** khi nó được áp:

```
Thanh Bình  thang [0,898 0,93 0,97 1,00 1,04 1,08 1,16]   -> ĐỦ 7 bậc đã có chủ
Thái Sơn    thang [0,87  0,93 0,97 1,00 1,04 1,08 1,16]   -> ĐỦ 7 bậc đã có chủ
```

Cả hai thang nam **kín hẳn** (37 giọng được giữ chỗ trước khi phân vai), nên mọi người nam mới
đều đi vào đường quay vòng. Kết quả:

```
preset_thanh_binh_f100_p-04   8 người: BOWDEN(68 câu) KANG(24) ROB(8) JONES(3) MARK(1) + 3 NPC
preset_thai_son_f100_p+00     5 người: CHUA TÔ, LYLE, ĐẠI TƯ TẾ + 2 NPC
```

Tám người một bậc, và bậc ấy là **1,00 — nấc số 0 của thang**. Đúng cơ chế đã phân tích đêm qua
trên chương 071: `holders` chỉ nhớ **người giữ đầu tiên**, nên người thứ hai trở đi đọc bậc 1,00
thành "chỉ có KANG" (rồi "chỉ có KANG" mãi), thấy 0 chương chung, và xếp vào. Không ai thấy bảy
bậc kia trống hơn vì **chúng không trống** — tất cả đều có chủ; câu hỏi duy nhất là *dùng chung
với ai*, và câu trả lời bị đóng băng ở người đầu tiên. Hoà thì lấy nấc thấp nhất, tức 1,00, mãi
mãi.

**Dự đoán cho lô 5, ghi trước:** với bản vá, giá phải trả tính trên **hợp** của mọi người giữ
bậc, nên người thứ hai vào bậc 1,00 sẽ thấy cả BOWDEN lẫn KANG và đi tìm bậc khác. Không bậc nào
được mang quá hai, ba người, và số va chạm cùng chương phải về 0. Nếu lô 5 vẫn có một bậc mang
tám người thì bản vá sai — và con số ấy đọc được bằng một lệnh:
`python scripts/voice_pool_pressure.py <project lô 5>`.

## Chính registry đã cảnh báo, và không ai đọc

Trong `runtime_events` của lô 4:

```
CẢNH BÁO: nhiều nhân vật dùng chung một giọng, người nghe sẽ tưởng là cùng một người:
{22: [22, 45, 54, 61, 62, 64, 67, 69], 35: [57, 59, 63, 66, 68]}
```

Tám id nhân vật trên một profile, năm trên một profile khác — **đúng con số ở trên**, ghi ngay
lúc phân vai, hai mươi bốn giờ trước khi tôi tìm ra nó bằng cách khác. Nó nằm trong bảng
`runtime_events` và không chỗ nào nổi lên: không vào báo cáo chương, không vào log ranh giới,
không ai `SELECT` nó.

Một cảnh báo đúng mà không ai đọc thì rẻ hơn không có: nó tạo cảm giác hệ thống đang trông. Bước
0 của `boundary.sh` phải đổ những dòng `CẢNH BÁO` của lô vừa xong vào log ranh giới — thêm ở
ranh giới sau, vì `boundary.sh` đang chạy và sửa file đang chạy là đúng thứ đã bị cấm.
