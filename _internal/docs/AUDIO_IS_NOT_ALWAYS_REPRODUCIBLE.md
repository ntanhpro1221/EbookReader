# Audio không phải lúc nào cũng tái lập được, và điều đó làm hỏng cách so phiên bản

Tìm ra 2026-09-08, giữa lúc alpha.62 đang chạy, khi kiểm một khẳng định **tôi vừa tự viết vào
[VERSIONS.md](VERSIONS.md) ba tiếng trước**: *"cùng chia đoạn, cùng giọng, cùng cách đọc thì ra
cùng bản thu tới từng bit"*. Số liệu bác bỏ nó.

## Số liệu

Bốn cặp lượt chạy, đếm số đoạn có **checksum audio giống hệt nhau**:

| cặp | đoạn so được | cùng hạt giống | cùng checksum |
|---|---|---|---|
| alpha.53 ↔ alpha.54 | 948 | 948 | **948 (100%)** |
| alpha.55 ↔ alpha.56 | 1.083 | 1.083 | **1.082 (100%)** |
| alpha.57 ↔ alpha.60 | 1.355 | 1.095 | 1.071 (79%) |
| **alpha.60 ↔ alpha.62** | 207 | 189 | **0 (0%)** |

Không phải trôi dần mà là **đứt gãy**: 189 đoạn cùng hạt giống và **không đoạn nào** cho cùng
bản thu. Ví dụ cụ thể, `c00001_s0000156` `"Khác gì ăn cướp không?"`:

```
alpha.60: seed 851566009 -> 2,24s, sha ca1e0afefdb8, ASR trượt, 5 vòng sửa, cuối cùng failed
alpha.62: seed 851566009 -> 0,96s, sha 39d7e83ec1c2, ASR đạt ngay, không cần vòng sửa nào
```

Và mọi đầu vào **được ghi lại** đều giống nhau: `text_sha256`, `speaker`, `gender`, `emotion`,
`intensity`, `pace`, `volume`, `tts_delivery_mode`, `spoken_text_sha256`, `pitch_semitones`,
`generation_frame_cap`. Chỉ `confidence` lệch (0,90 → 0,95) và đó là metadata, không vào TTS.

## Ba nghi can đã loại

1. **Bản vá nhịp đọc.** `segment_duration_policy` dùng `spoken_speakable_chars` để tính ngân
   sách khung, nên nghi ngay. Nhưng bản vá chỉ đổi cách đếm **chữ số**, và câu trên không có
   chữ số nào — cùng con số, cùng ngân sách khung.
2. **`gpu_scale`.** alpha.60 và alpha.62 đều chạy bị bóp. Nhưng `gpu_batch_scale` chỉ được
   **ghi ra**, không có mã sinh nào đọc nó (`grep gpu_batch_scale`: chỉ `resource_manager.py`
   đặt và `pipeline.py` log).
3. **Trạng thái tiến trình trong pool.** `_set_generation_seed` gieo lại `random`,
   `np.random`, `torch.manual_seed` và `torch.cuda.manual_seed_all` **trước từng lần sinh**
   (`tts.py:547`), nên lịch sử của tiến trình không mang sang.

## Nghi can còn lại, chưa chứng minh

**Không có `torch.backends.cudnn.deterministic`.** Khi không đặt, cuDNN tự chọn thuật toán
theo bộ nhớ trống và điều kiện máy lúc ấy, và hai thuật toán khác nhau cho kết quả dấu phẩy
động lệch nhau chút ít. Lệch chút ít trong một mô hình tự hồi quy thì cộng dồn thành một câu
dài ngắn khác hẳn — đúng dạng đã đo: 3,20→2,96s, 3,52→3,44s, 6,00→5,84s.

Khớp với cả bốn hàng của bảng: hai cặp **100%** đều chạy ở `gpu_scale 1.0` trên máy rảnh; cặp
79% có một bên bị bóp; cặp 0% thì **cả hai** bị bóp nhưng theo chuỗi khác nhau.

Đây là **giả thuyết**, không phải kết luận. Chứng minh nó cần chạy cùng một đoạn hai lần dưới
hai mức tải, và việc ấy phải đợi máy rảnh.

## Hệ quả, và nó nghiêm trọng hơn nguyên nhân

**Một chương chuyển từ `failed` sang xuất bản KHÔNG tự chứng minh bản vá có tác dụng.** Nếu
bản thu đầu tiên đã khác thì chương ấy có thể chỉ gặp một lần bốc thăm may hơn.

Chương 019 của alpha.62 là ví dụ sống: nó xuất bản, đoạn từng chặn giờ `verified` — nhưng bản
thu là **0,96 giây thay vì 2,24 giây**, tức một bản thu khác hẳn, đạt ngay từ lần đầu mà không
cần vòng sửa nào. Không có gì ở đây nói rằng bản vá đã làm điều ấy.

Cách đọc kết quả alpha.62 phải sửa lại cho đúng:

| đo được | kết luận rút ra được |
|---|---|
| chương nào xuất bản | **có** — đó là sản phẩm, và nó có thật |
| máy tự cho qua mấy đoạn, đoạn nào | **có** — cơ chế hoặc chạy hoặc không, và log ghi rõ |
| `"Gì cơ?"` có được thu lại không | **có** — `segment_candidates` rỗng hay không là chuyện logic, không phải chuyện bốc thăm |
| bản vá có làm chương 019 xuất bản được không | **không** — bản thu đã khác từ đầu |

Ba dòng đầu vẫn đứng vững, và chúng là ba thứ đã ghi sẵn phải đo. Dòng thứ tư là thứ tôi tưởng
sẽ có và không có.

## Phải làm gì

1. **Sửa ngay** câu trong [VERSIONS.md](VERSIONS.md) nói phép so là "có kiểm soát tới từng
   bit" — đã sửa cùng lúc với việc tạo file này.
2. **Cân nhắc `torch.backends.cudnn.deterministic = True`.** Nó làm chậm, và nó đổi **toàn bộ**
   audio một lần. Nếu làm thì làm ngay trước lô 1 của
   [PRODUCTION_PLAN.md](PRODUCTION_PLAN.md), cùng lúc với
   [bản vá lọc thuỷ ấn](THE_SOURCE_IS_WATERMARKED.md) — hai thay đổi cùng đổi hash một lần thì
   trả giá một lần.
3. **Đừng so hai lượt chạy trên máy có tải khác nhau** rồi kết luận về chất lượng mã. Bốn hàng
   trong bảng trên là bằng chứng đủ để không tin phép so ấy nữa.
