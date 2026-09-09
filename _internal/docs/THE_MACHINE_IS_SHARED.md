# Máy này không chạy một mình, và nó làm lô chậm gấp ba

Đo ngày 2026-09-09 trên chương 003 của lô vá, **pha sinh audio**, 121 segment:

```
chế độ         phút   segment   segment/phút
  maximum        8,6      113      13,13
  yield_light    2,8        0       0,00
  yield_heavy   15,6        8       0,51
  TỔNG          27,0      121       4,48
```

Chạy hết tốc độ thì 121 segment tốn **9,2 phút**. Thực tế tốn **27,0 phút** — **chậm gấp 2,93
lần**. Gần sáu mươi phần trăm thời gian nằm trong `yield_heavy`.

### Bằng chứng vững hơn: ba chương, chỉ dùng số tổng

Lô vá chạy ba chương có nhiều đoạn, trên cùng mã, cùng máy, cách nhau vài giờ. So chúng bằng
**tổng thời gian và tổng segment** — không đụng tới phép gán segment-vào-chế-độ vốn nhiễu:

| chương | segment | phút | segment/phút | % thời gian `yield_heavy` |
|---|---|---|---|---|
| 016 | 186 | 23,5 | **7,91** | 34% |
| 003 | 121 | 27,0 | 4,48 | 58% |
| 007 | 151 | 41,8 | **3,61** | 65% |

Đơn điệu, không có ngoại lệ, và biên độ là **2,2 lần** giữa chương ít bị hãm nhất và chương bị
hãm nhiều nhất. Nội suy về 0% cho khoảng 11–12 segment/phút, khớp với 13,13/phút đo trực tiếp ở
chế độ `maximum` của chương 003 — hai đường đo độc lập gặp nhau.

Đây là con số nên trích dẫn. Bảng chia theo chế độ bên dưới giữ lại vì nó chỉ ra *chế độ nào*,
nhưng chỉ có tổng mới tin được:

**Hai cột nào tin được và cột nào không.** Tổng (121 segment / 27 phút) và tốc độ `maximum`
(113 segment trên 8,6 phút) đứng vững. Phần chia cho các chế độ *hiếm* thì không: hai lần chạy
cách nhau vài phút cho `yield_heavy` lúc 2 segment lúc 8, vì việc gán segment vào chế độ dựa
trên mốc đổi chế độ gần nhất trước `updated_at`, và mỗi mốc mới rơi vào giữa lại xáo lại phần
chia. Con số đáng trích dẫn là **2,9 lần**, không phải "0,13 segment/phút".

## Vì sao

Bộ điều tiết (`resource_manager.py`) nhường máy cho người đang ngồi trước nó. Ngưỡng:

```
min_free_ram_gb        3,5     foreground_cpu_trigger   35%
min_free_disk_gb      12,0     foreground_gpu_trigger   25%
                               system_cpu_trigger       82%
```

Log của chính lượt ấy:

```
yield_heavy — foreground CPU 65%
yield_heavy — foreground CPU 40%
yield_heavy — foreground CPU 164%; available RAM 3,1 GB
yield_heavy — available RAM 3,4 GB
```

Lúc đo, máy đang mở **ba tiến trình Unity.exe (~5,1 GB) và Rider + Rider.Backend (~4,5 GB)**.
RAM tổng 31,3 GB. Nghĩa là chín rưỡi GB nằm trong tay công việc khác của chủ máy, và RAM còn
trống dao động quanh đúng cái ngưỡng 3,5 GB.

**Nhường như thế là đúng, không phải lỗi.** Người đang làm việc quan trọng hơn một lô chạy nền.
Tài liệu này không đề nghị bỏ việc nhường.

**Nhưng quy hết cho Unity và Rider là thiếu.** Đo sau đó: pool TTS tự giữ 7,63 GB, và trên máy
31,3 GB thì hai bên cộng lại mới vượt ngưỡng — bỏ một trong hai là đủ. Xem
[A_POOL_THAT_FORBIDS_ITSELF.md](A_POOL_THAT_FORBIDS_ITSELF.md).

## Nhưng "hãm" đang có nghĩa là "dừng"

`yield_heavy` khai báo `gpu_batch_scale = 0,25` — nghe như chạy một phần tư tốc độ. Đo thật là
**0,13 / 13,60 = 1%**. Vì khi nguyên nhân là RAM hay CPU tiền cảnh, quyết định còn tắt luôn
`allow_new_gpu_batch` và `allow_cpu_heavy_work`, nên đường ống không chậm lại mà **đứng**.

Người trước đã đo `yield_heavy` trên alpha.46 và ghi vào chú thích trong `resource_manager.py`:

```
alpha.46:  maximum  5,60/phút   yield_heavy 2,27/phút
hôm nay :  maximum 13,13/phút   yield_heavy ~0,5/phút   (xem cảnh báo ở trên về cột này)
```

Tốc độ tối đa **nhanh lên 2,3 lần** — con số này chắc, cả hai đầu đều dựa trên hơn trăm mẫu.
`yield_heavy` thì chậm đi khoảng bốn tới năm lần, nhưng đầu "hôm nay" của phép so ấy dựng trên
tám mẫu nên đừng dùng nó để tính toán gì. Điều nói được chắc chắn là: chú thích alpha.46 mô tả
một `yield_heavy` còn *làm việc*, còn `yield_heavy` hôm nay gần như đứng.

Đây là chỗ đáng xem lại, và nó **không** phải chuyện hạ ngưỡng: hạ `min_free_ram_gb` xuống dưới
3,5 GB trên một máy đang bị chiếm 9,5 GB là mời swap vào, và swap còn tệ hơn dừng. Chỗ đáng xem
là **hụt ngưỡng 0,1 GB thì dừng hẳn thay vì chậm lại**, cộng với hồi phục chậm (`20 + 8` giây
ổn định mới được ramp) trong khi kích hoạt lại thì tức thì.

## Hệ quả cho kế hoạch sản xuất

Mọi con số giờ trong [PRODUCTION_PLAN.md](PRODUCTION_PLAN.md) là **ước lượng cho máy rảnh**.
Với mức chia sẻ đo được hôm nay:

```
lô 2 ước lượng  8,1 giờ   ->  ~23,7 giờ nếu máy bị chia như hôm nay
16 lô ~130 giờ            ->  ~380 giờ
```

Điều quan trọng không phải con số mà là **đừng đọc nhầm một lô chậm thành một lô treo**. Lúc ba
giờ sáng, một lô đi được vài segment trong mười lăm phút trông hệt như treo. Nó không treo:

- nhịp tim `worker_leases.heartbeat_at` vẫn dưới 180 giây,
- và `runtime_events` có dòng `Resource mode: yield_heavy` kèm lý do.

Hai dấu ấy phân biệt "đang nhường" với "đã chết". Xem thêm
[SURVIVING_AN_INTERRUPTION.md](SURVIVING_AN_INTERRUPTION.md).

## Cách đo lại

```bash
python scripts/throttle_report.py <project>
```
