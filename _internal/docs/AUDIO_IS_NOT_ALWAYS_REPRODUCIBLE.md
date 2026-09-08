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

## Mọi đầu vào ghi lại đều giống nhau — đo trên cả 189 đoạn

Không phải một ca lẻ. Trong 189 đoạn cùng hạt giống:

```
lệch text_sha256          : 0
lệch spoken_text_sha256   : 0
lệch effective_pitch      : 0
lệch tts_delivery_mode    : 0
lệch pronunciation_variant: 0
lệch generation_frame_cap : 0
lệch CHECKSUM AUDIO       : 189   ← tất cả
```

Hồ sơ giọng cũng giống hệt ở mọi trường có nghĩa — `voice_key`, `engine`, `preset_name`,
`seed` riêng của profile, `pitch_semitones`, `formant_ratio`; chỉ `id` và mốc thời gian khác,
và cả hai đều là khoá/nhãn nội bộ.

## Bốn nghi can đã loại, bằng đo chứ không bằng suy

1. **Bản vá nhịp đọc.** `segment_duration_policy` dùng `spoken_speakable_chars` để tính ngân
   sách khung, nên nghi ngay. Nhưng bản vá chỉ đổi cách đếm **chữ số**, và các câu này không có
   chữ số — cùng con số, cùng ngân sách khung. `generation_frame_cap` lệch 0/189 xác nhận.
2. **`gpu_scale`.** `gpu_batch_scale` chỉ được **ghi ra**, không mã sinh nào đọc
   (`resource_manager.py` đặt, `pipeline.py` log, hết).
3. **Trạng thái tiến trình trong pool.** `_set_generation_seed` gieo lại `random`, `np.random`,
   `torch.manual_seed`, `torch.cuda.manual_seed_all` **trước từng lần sinh** (`tts.py:547`).
4. **Máy bị bóp bộ nhớ.** Đây là giả thuyết đầu tiên của tôi và nó nghe rất khớp — cho tới khi
   đo: **alpha.53 và alpha.54 đều bị bóp nặng** (70 lần ở `gpu_scale 0.25`, 63 lần ở `0.6`) và
   vẫn giống nhau **948/948, 100%**. Bóp GPU không phá tính tái lập.

## Nghi can còn lại, và tôi dừng ở mức nghi

**Model TTS đã bị ghi lại lúc 10:45 hôm nay, giữa hai lượt chạy.** alpha.60 chạy 07:06, alpha.62
chạy 13:46, và snapshot VieNeu mang mốc 8/9 10:45–10:46:

```
snapshots/8b7e9cff…/config.json           10:45
snapshots/8b7e9cff…/denoiser.onnx         10:46   (42 MB)
snapshots/8b7e9cff…/speaker_encoder.onnx  10:46   (28 MB)
snapshots/8b7e9cff…/update/model.safetensors 10:45 (248 MB)
```

Gói `hf_xet` cũng mang đúng mốc 10:45, nên nhiều khả năng một lần cài đặt đã làm HuggingFace
tải lại toàn bộ file qua giao thức Xet.

**Nhưng tải lại cùng một revision thì ra cùng bytes.** `refs/main` vẫn trỏ `8b7e9cff…`, và
thư mục `blobs/` rỗng nên không còn bản cũ để so. Tôi **không chứng minh được** trọng số đã
đổi, và cũng không loại được khả năng ấy.

Đến đây tôi dừng. Ba giả thuyết trước đều nghe hợp lý và đều chết khi đo, nên giả thuyết thứ tư
không đáng được viết như một kết luận. Cái chắc chắn là **mọi đầu vào ghi lại đều giống nhau mà
audio thì khác**, và cái đó đã đủ để không tin phép so audio giữa hai lượt.

Cách kiểm rẻ nhất khi máy rảnh: sinh lại **một** đoạn đã biết bằng chính seed cũ và so checksum
với bản trong alpha.60. Giống nhau ⇒ nguyên nhân nằm ở điều kiện lượt chạy; khác nhau ⇒ nằm ở
model hoặc mã.

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
