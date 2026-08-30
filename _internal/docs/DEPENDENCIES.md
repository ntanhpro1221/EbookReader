# Quản lý dependency, model và tool

File này là trách nhiệm thường trực của người dev project, không phải một lần rà soát. Mỗi phiên bản
phải kiểm lại bảng dưới và ghi kết quả vào `VERSIONS.md`.

## Vì sao không nâng cấp bừa

`QUALITY_IMPLEMENTATION_FILES` trong `quality_policy.py` bao gồm cả `../pyproject.toml` và `../uv.lock`,
còn policy còn nhúng `installed_dependency_provenance()`. Nghĩa là **mọi thay đổi dependency đều đổi
quality-policy hash và làm project đang dở không resume được**. Đó là hành vi đúng: audio sinh bởi hai
phiên bản engine khác nhau không được phép trộn vào cùng một cuốn sách.

Hệ quả thực tế cho quy trình dev:

> **Tuyệt đối không sửa file nào trong `QUALITY_IMPLEMENTATION_FILES` — kể cả `pyproject.toml` —
> khi đang có job chạy.** Pipeline tính policy hash một lần lúc khởi tạo, nên job đang chạy không chết
> ngay; nhưng lần resume kế tiếp sẽ bị từ chối và mất toàn bộ phần chưa xuất bản.

Nâng cấp dependency vì vậy luôn là một **sự kiện phiên bản**: nâng cấp → chạy lại từ project sạch →
so sánh audio với phiên bản trước → tag.

## Kiểm tra nhanh

```bash
cd _internal
./runtime/.venv/Scripts/python.exe -m ebook_reader.cli doctor --json
./runtime/.venv/Scripts/python.exe scripts/check_dependency_updates.py
```

## Trạng thái ngày 2026-08-30

### Model và tool — đều đang là bản mới nhất

| Thành phần | Đang dùng | Mới nhất | Ghi chú |
|---|---|---|---|
| Ollama server | 0.33.2 | 0.33.2 | app tự khởi động ẩn, không dùng desktop app |
| Qwen (analysis) | `qwen3:8b` | — | `qwen3:4b` cho profile `fast`; digest khóa theo book |
| openai-whisper | 20250625 | 20250625 | model `turbo` |
| UTMOSv2 | commit `cc2700db` (1.3.1.dev0) | v1.3.0 | pin sau v1.3.0, checkpoint khóa bằng SHA-256 |
| FFmpeg | 7.1 (imageio-ffmpeg 0.6.0) | 0.6.0 | |

### Thư viện Python — nhiều pin đã cũ

| Package | Pin | PyPI | Rủi ro khi nâng |
|---|---|---|---|
| ruff | 0.9.10 | 0.16.5 | **thấp** — chỉ dev tool, lint mới có thể lộ lỗi thật |
| pytest | 8.3.5 | 9.1.1 | **thấp** — chỉ dev tool |
| requests | 2.32.3 | 2.34.2 | thấp — vá lỗi/bảo mật cho client Ollama |
| psutil | 6.0.0 | 7.2.2 | thấp–trung — major bump, dùng trong `resource_manager` |
| soundfile | 0.13.1 | 0.14.0 | trung — đọc/ghi WAV, phải smoke lại checksum |
| pyworld | 0.3.5 | 0.3.6 | **trung–cao** — đổi vocoder pitch là đổi audio |
| scipy | 1.17.1 | 1.18.1 | trung |
| timm | 1.0.28 | 1.0.29 | **cao** — khóa cùng cache revision của UTMOSv2; đổi có thể đổi điểm MOS |
| numpy | 1.26.4 | 2.5.2 | **cao** — numpy 2.x lan ra toàn bộ stack audio |
| librosa | 0.11.0 | 1.0.0 | **cao** — major bump |
| transformers | 5.7.0 | 5.16.1 | **cao** — ràng buộc với UTMOSv2 và Whisper |
| huggingface-hub | 1.7.1 | 1.29.0 | **cao** — ràng buộc với cache revision đã khóa |
| torch / torchaudio / torchvision | 2.8.0+cu128 / 2.8.0+cu128 / 0.23.0 | 2.13.0 / 2.11.0 / 0.28.0 | **cao** — phải có wheel CUDA khớp Blackwell sm_120 |
| PySide6 | 6.8.0 | 6.11.2 | trung — chỉ GUI |
| vieneu | 3.2.3 | 3.3.0 | **rất cao** — xem bên dưới |

### vieneu 3.3.0 đổi kiến trúc, chưa nên nâng

Đọc metadata PyPI của 3.3.0: dependency mặc định chuyển sang **ONNX Runtime**
(`onnxruntime`, `kaldi-native-fbank`, `soxr`, `sea-g2p`), còn `torch`/`transformers`/`neucodec`
bị đẩy xuống extra `legacy`. Toàn bộ invariant hiện tại về ngân sách frame
(`3.840 sample/frame @ 48 kHz`, `max_new_frames`, cap sửa 24/12/6 frame) được đo trên engine
torch cũ. Nâng lên mà không giữ `[legacy]` là đổi hẳn engine sinh audio.

Ngoài ra, trên nhánh `main` của VieNeu, tham số `style` **đã bị deprecate và bỏ qua**
("style đã nằm trong ref code"). `tts.py` hiện vẫn truyền `style="doc_truyen"` cho NARRATOR và
`"tu_nhien"` cho nhân vật. Với 3.2.3 tham số này còn tác dụng; sau khi nâng thì không, nên
mọi khác biệt giọng kể/nhân vật sẽ phải đến từ preset và pitch chứ không từ `style`.

### Không có điều khiển tốc độ đọc trong thư viện Python

VieNeu **Desktop app** 0.8.0 (2026-08-25) có ô nhập tốc độ 0.5–3.0 giữ nguyên cao độ. Nhưng đọc
`src/vieneu/v3turbo.py` trên nhánh `main`: **không có tham số `speed` nào** — tính năng đó nằm ở
lớp ứng dụng Rust, không nằm trong thư viện. Kết luận: nâng `vieneu` **không** mang lại điều khiển
tốc độ, và cách đúng để hiện thực hóa `pace` vẫn là hậu xử lý giữ cao độ (FFmpeg `atempo`) — đúng
kỹ thuật mà tempo rescue đang dùng.

### "Emotion cue" của VieNeu chính là thứ invariant đang từ chối — đã xác minh

Config của engine v3 có `emotion_0..7_token_id` và prompt builder nói "inline `<|emotion_N|>` tags".
Thoạt nhìn giống một API điều khiển cảm xúc gốc mà project chưa dùng. **Không phải.** README upstream ghi rõ:

> **Emotion / non-verbal cues** *(experimental)*: drop `[cười]`, `[thở dài]`, `[hắng giọng]` straight into the text.

Tức là các emotion token đó chính là hiện thực của mấy tag phi ngôn ngữ thử nghiệm mà `AGENTS.md` đã cấm và
`text_processing.py` đã thay bằng âm tiết tiếng Việt (`[cười] → ha ha`, `[thở dài] → hầy`). Không có kênh
conditioning cảm xúc tổng quát nào khác trong model.

**Kết luận: invariant hiện tại là đúng, đừng đào lại.** Cảm xúc chỉ còn các lever hợp lệ là sampling
(temperature/top_p), preset + pitch, mức loudness mục tiêu, và — chưa dùng — tốc độ đọc qua hậu xử lý
giữ nguyên cao độ.

`style` trong 3.2.3 thì vẫn thật: `style_labels = {"tu_nhien": 16, "tin_tuc": 17, "doc_truyen": 18}` ánh xạ
thành style head token, nên `doc_truyen` cho NARRATOR đang có tác dụng thật. Upstream đã deprecate nó
("the style argument is deprecated and ignored"), nên khi nâng vieneu thì khác biệt giọng kể/nhân vật phải
chuyển hẳn sang preset và pitch.

## Lỗ hổng đã phát hiện, chưa sửa

`CRITICAL_RUNTIME_DISTRIBUTIONS` trong `runtime_contract.py` chỉ khóa 8 distribution quanh
UTMOSv2 và torch. **`vieneu`, `pyworld`, `numpy`, `soundfile`, `scipy` và `openai-whisper` không được
khóa** — trong khi `vieneu` chính là engine sinh audio và `pyworld` chính là vocoder đổi pitch.
Provenance có ghi chúng qua `uv.lock`/`pyproject.toml`, nhưng `doctor` không kiểm và policy không
so khớp phiên bản thực đang cài. Cần đưa chúng vào danh sách khóa.

Thêm nữa, policy hash băm **toàn bộ byte** của `pyproject.toml`, nên chỉ đổi dòng `version` cũng làm
mọi project đang dở hết resume được, dù không có gì ảnh hưởng tới audio. Nên thu hẹp phần đóng góp của
`pyproject.toml` về đúng dữ liệu dependency thay vì cả file.
