# Model giọng đã tự đổi giữa hai lượt chạy — và giờ đã được ghim

**Trạng thái: đã sửa 2026-09-08 17:5x.** Phần dưới giữ nguyên chuyện đã xảy ra và cách truy ra nó, vì cái đáng học không phải kết luận mà là đường đi tới đó.

Tìm ra 2026-09-08 khi truy vì sao alpha.60 và alpha.62 cho audio khác nhau với **cùng hạt
giống và mọi đầu vào ghi lại giống hệt nhau** — xem
[AUDIO_IS_NOT_ALWAYS_REPRODUCIBLE.md](AUDIO_IS_NOT_ALWAYS_REPRODUCIBLE.md) cho bốn giả thuyết
đã chết trước khi tới cái này.

## Bằng chứng

Cache runtime giữ **ba** revision của `pnnbao-ump/VieNeu-TTS-v3-Turbo`:

```
75ff82a7…   11/8
2da0efab…   24/8          <- mọi lượt chạy tới alpha.60 dùng bản này
8b7e9cff…   8/9  10:46    <- refs/main trỏ vào đây từ 10:45 hôm nay
```

alpha.60 chạy **07:06**, alpha.62 chạy **13:46**. Giữa hai mốc ấy, `refs/main` chuyển sang
revision mới.

Trọng số khác nhau thật, không phải chỉ đổi mốc thời gian — cùng kích thước 247.974.928 byte,
khác SHA-256:

```
2da0efab…/update/model.safetensors   82b24b3f02357d7c5ea69f5286dd2c2ec12041eca2a839843d3a4a21b5073f39
8b7e9cff…/update/model.safetensors   119003a9e121760d1c3b9b50bd675bfde8d5f3de2b12641cf97a17d3883a5da7
```

Đó là toàn bộ lời giải: **model đổi thì audio đổi**, dù hạt giống, chữ, giọng, cao độ và ngân
sách khung y hệt. Bốn nghi can trước — bản vá của tôi, `gpu_scale`, trạng thái pool, bóp bộ
nhớ — đều vô can.

## Khiếm khuyết, và nó không phải chuyện tái lập

Dự án **có** cơ chế ghim revision: `runtime_contract.py` đọc `refs/main` và so với hằng số
kỳ vọng. Nó ghim `wav2vec2`, `timm_backbone`, và các file model nền của perceptual QA, kèm cả
kích thước lẫn SHA-256.

**Nó không ghim VieNeu-TTS.**

Tức là dự án khoá chặt những model **chấm điểm** và để tự do model **tạo ra sản phẩm**. Cái
được bảo vệ là thước đo; cái không được bảo vệ là giọng đọc của cuốn sách.

## Vì sao đây là lỗi sản phẩm, không chỉ lỗi phương pháp

[PRODUCTION_PLAN.md](PRODUCTION_PLAN.md) là 16 lô, ~128 giờ máy, trải nhiều ngày. Nếu upstream
đẩy một revision mới ở giữa — đúng chuyện vừa xảy ra hôm nay — thì lô sau dùng model khác lô
trước, và **giọng người dẫn chuyện đổi giữa cuốn sách**.

Người nghe không cần biết gì về `refs/main` để nhận ra điều đó. Đây là loại lỗi mà mọi phép
kiểm trong dự án đều mù: từng chương vẫn qua ASR, qua perceptual QA, qua QA tầng chương — vì
mỗi chương được chấm **theo chính nó**, không ai so chương 1 với chương 200.

## Phải làm gì

1. **Ghim VieNeu-TTS trong `runtime_contract.py`**, cùng cách đã ghim wav2vec2 và timm: đối
   chiếu `refs/main` với một revision hằng số, và thêm `model.safetensors` vào danh sách file
   có kích thước + SHA-256 kỳ vọng. Hai hash đã có ở trên.

2. **Ghim revision nào?** Đề xuất: **`8b7e9cff…`, bản mới.** Lý do là kế hoạch sản xuất chạy
   lại từ chương 000 nên không có audio nào cần giữ liên tục với bản cũ; chấp nhận một lần đứt
   rồi ổn định mãi thì rẻ hơn quay về bản cũ để rồi vẫn phải đổi sau. alpha.62 cũng đã chạy
   trên bản mới rồi.

   **Bản mới không tốt hơn — đã đo sau khi chín chương chạy xong.** Lúc viết dòng này tôi có
   một điểm dữ liệu mỏng nghiêng về "tốt hơn" (`"Khác gì ăn cướp không?"` trượt ở alpha.60, đạt
   ngay ở alpha.62) và đã cố ý không tin nó. Đúng là không nên: trên 385 đoạn của hai chương
   đầu, **74 đoạn tốt lên, 73 xấu đi, 238 y nguyên**, WER trung bình còn nhích xấu. Nó chỉ
   khác, không hơn — nên lý do ghim bản mới vẫn là "chịu một lần đứt rồi ổn định", không phải
   "bản mới ngon hơn".

3. **Áp cùng lúc với hai thay đổi đang chờ khác** — [lọc thuỷ ấn](THE_SOURCE_IS_WATERMARKED.md)
   và (nếu làm) `cudnn.deterministic`. Cả ba đều đổi audio một lần; gộp lại thì trả giá một
   lần, ngay trước lô 1.

4. **Giữ cả `2da0efab…` trong cache.** Nó là bản đã sinh ra mọi audio từ alpha.10 tới alpha.60,
   và là thứ duy nhất tái tạo lại được chúng. Đừng dọn cache.

## Đã làm, 2026-09-08 17:5x

Khoản 1 và 2 xong: `runtime_contract.voice_model_check()` đối chiếu `refs/main` với
`VIENEU_CACHE_REVISION`, rồi kiểm kích thước + sha256 của năm file
(`config.json`, `denoiser.onnx`, `speaker_encoder.onnx`, `update/model.safetensors`,
`update/config.json`). Đăng ký thành `checks["model:vieneu_voice"]` và nằm trong
`runtime_contract_errors`. Sáu test ghim nó.

**Bản vá đầu tiên sai chỗ và bộ test bắt được.** Tôi nhét model giọng vào
`perceptual_cache_check`, và `test_perceptual_cache_marker_requires_locked_revision_and_checkpoint_hash`
đỏ ngay. Test ấy đúng: hàm kia đăng ký là `checks["model:utmosv2_cache"]`, nên một lần thiếu
ghim TTS sẽ báo thành lỗi perceptual — đúng lỗi, sai chỗ, và sai chỗ thì người đọc đi tìm nhầm
hướng. Bản sau có phép kiểm riêng.

Khoản 3 cũng xong: áp cùng lúc với [bản vá lọc thuỷ ấn](THE_SOURCE_IS_WATERMARKED.md), ngay tại
ranh giới alpha.62 / lô 1, nên hai lần đổi hash trả giá một lần.

Nghĩa là **không cần kiểm `refs/main` bằng tay sau mỗi lần cài gói nữa** — điều mà bản đầu của
tài liệu này còn dặn. Chủ sách vẫn cứ *"cần cài gì thì cứ cài thoải mái"*; nếu một lần cài kéo
theo model mới thì `cli check` sẽ nói ra, thay vì để nó lặng lẽ đổi giọng giữa cuốn sách.
