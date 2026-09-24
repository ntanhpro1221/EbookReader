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

## Hai cái bẫy đã cắn thật, ngày 2026-09-01

### 1. `pyproject.toml` không nói được torch phải là bản CUDA

Bản đang chạy là `torch==2.8.0+cu128`, nhưng file chỉ ghi `torch==2.8.0`. Hậu tố `+cu128` đến từ
**cách cài**, không từ file. Chạy `uv pip install -e .` sẽ lấy torch từ PyPI, mà trên Windows PyPI
phục vụ **bản CPU**. Kết quả:

    torch 2.13.0+cpu   cuda None   available False

Và **không có lỗi nào được ném ra**. Pipeline vẫn chạy, chỉ là mọi thứ chuyển sang CPU và chậm hàng
chục lần. Đây là kiểu hỏng tệ nhất: im lặng.

**Luật:** sau mọi lần đụng tới torch, chạy

```
runtime/.venv/Scripts/python.exe -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

và phải thấy hậu tố `+cuXXX` cùng `True`. Cài lại bằng
`uv pip install --reinstall torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cu128`.

Lưu ý `uv` coi `2.13.0+cpu` là đã thoả `torch==2.13.0` nên **bỏ qua** lệnh cài lại nếu không có
`--reinstall`. Phải gỡ hoặc ép `--reinstall`.

### 2. "Latest" trên PyPI không có nghĩa là cài được

`check_dependency_updates.py` từng đọc `info.version` của PyPI và gọi đó là bản mới nhất. Nó báo
`numpy 2.5.2`, `librosa 1.0.0`, `scipy 1.18.1` — cả ba đều **đòi Python ≥3.12** trong khi project chạy
**3.11.9**. Tôi đã ghi những số đó vào `pyproject.toml` và chỉ phát hiện khi resolver báo lỗi.

Script giờ duyệt từng release, lọc theo `requires_python` của interpreter đang chạy, và báo **bản cao
nhất cài được**, kèm ghi chú khi PyPI có bản mới hơn nhưng cần Python mới hơn.

Bộ thực tế nâng được trên Python 3.11:

| nâng | giữ nguyên vì cần Python ≥3.12 |
|---|---|
| torch 2.13.0, transformers 5.16.1, numpy **2.4.6**, vieneu 3.3.0, sea-g2p 0.9.1, huggingface-hub 1.29.0, PySide6 6.11.2, psutil 7.2.2, soundfile 0.14.0, pyloudnorm 0.2.0, timm 1.0.29, requests 2.34.2, pytest 9.1.1, ruff 0.16.5 | numpy 2.5.2, librosa 1.0.0, scipy 1.18.1, pyworld 0.3.6 |

Muốn lấy nhóm bên phải thì phải nâng Python trước — đó là một quyết định riêng, không phải hệ quả
tự động của việc nâng package.

## Kiểm tra nhanh

```bash
cd _internal
./runtime/.venv/Scripts/python.exe -m ebook_reader.cli doctor --json
./runtime/.venv/Scripts/python.exe scripts/check_dependency_updates.py
```

## Trạng thái ngày 2026-09-17 — sau 18 ngày không ai kiểm

**Lỗi quy trình, ghi thẳng ra:** file này nói kiểm lại là "trách nhiệm thường trực", còn
`check_dependency_updates.py` thì có sẵn. Vậy mà từ 30-08 tới 17-09 nó không được chạy lần nào. Trong khoảng
ấy VieNeu ra 16 bản, và chủ sách phải tự hỏi *"vietneu có bản mới chưa?"*. Hai thay đổi để việc này không
lặp lại:

- `check_dependency_updates.py` giờ luôn ghi `runtime/dependency_audit.json` (có giờ kiểm).
- `heartbeat_tick.py` in một dòng "thượng nguồn: …" ở **mọi** nhịp tim, và la lên
  `QUÁ N GIỜ CHƯA KIỂM` khi lần kiểm cuối đã quá 24 giờ.

Script cũng được mở rộng tới những chỗ nó từng mù: tag SDK của VieNeu (GitHub "latest release" là bản app
desktop), torch theo từng biến thể CUDA mà driver chạy được, model Hugging Face đang ghim so với `main`
(kèm danh sách file đổi), manifest model Ollama trên đĩa so với registry, họ LLM mới vừa VRAM, và UTMOSv2
ghim theo commit.

Mục tiêu do chủ sách đặt lại ngày 17-09: *"giọng đổi tôi không quan tâm, mục tiêu đang là xây app tốt hơn
chứ không phải là đang tạo audio book"*. Vì vậy "audio đổi giữa cuốn" không còn là lý do để đứng yên. Mỗi
lần nâng vẫn là **sự kiện phiên bản**: làm ở ranh giới, không có lô nào bay, chạy bộ test và đo.

| thành phần | đang dùng | mới nhất dùng được | changelog nói gì liên quan tới app | kế hoạch |
|---|---|---|---|---|
| **vieneu** | 3.3.0 | **3.8.1** (16-09) | 3.7.0: mọi `infer` trên CUDA đi qua CUDA graph gộp, upstream đo 1 câu 2,3 s → 0,38 s; 3.8.0: sửa frame đệm mã 455 ở cuối giọng mẫu (#198, "một tiếng ngắn nghe rõ" mà model nhả ra cuối câu); 3.6.1: chặn đọc lan man + trần khung theo âm tiết (≤4 tiếng); 3.6.3: nối mảnh giữ đuôi tự nhiên, khoảng nghỉ 0,30/0,50/0,70 s; 3.6.5: cắt mảnh dài không xẻ số; 25 preset — app chỉ biết 14 | **ƯU TIÊN 1.** Venv phủ `runtime/venv-vieneu381` đã dựng; **bộ test đầy đủ chạy bằng 3.8.1: xanh**. Chờ GPU rảnh để chạy `scripts/audition_presets.py` (tốc độ + giọng mới). Rủi ro cần đo: trần 1 s cho câu 1 tiếng với tiếng kéo dài ("Áaaa!") |
| Ollama | 0.33.2 | 0.34.1 (14-09) | 0.33.3 "Honor GGUF model defined default parameters" (phải chắc app truyền tường minh mọi tham số sinh), báo token prompt đã cache; 0.34.1 ngưỡng phát hiện lặp token lên 100, `/api/tags` nhanh hơn 10 lần | Ưu tiên 2, rủi ro thấp. Nâng ở ranh giới; trước đó soát `options` app gửi |
| torch / torchvision | 2.11.0+cu128 / 0.26.0 | 2.14.0 / 0.29.0 **chỉ trên cu130/cu126** | bản cu128 cho Windows dừng ở 2.11.0; driver 581.80 chạy được CUDA 13.0 | Ưu tiên 3, rủi ro trung–cao. **torchaudio dừng ở 2.11** trên mọi biến thể, mà UTMOSv2 import torchaudio. Thử trên venv phủ riêng (tải ~3 GB): torch 2.14 cu130 + torchaudio 2.11 có nạp được không, VieNeu có nhanh hơn không |
| transformers | 5.16.1 | 5.17.0 (09-09) | tối ưu `generate` (app không dùng); thêm model ASR Fun-ASR-Nano, Canary | Nâng cùng đợt torch. Model ASR mới là **ứng viên nghiên cứu** cho tiếng Việt, không phải nâng cấp |
| huggingface-hub | 1.29.0 | 1.32.0 (17-09) | 1.31: tải bền hơn, vá bảo mật `HfFileSystem.get()`; 1.32: kho blob dùng chung cho file Xet **mới** (đổi bố cục cache) | Rủi ro trung vì `runtime_contract` kiểm đường dẫn snapshot. Thử trên venv phủ + `cli doctor` |
| pyworld | 0.3.5 | 0.3.6 | (chưa đọc được changelog; repo GitHub đã đổi tên) | Nâng cùng đợt, đo lại biến thể cao độ |
| ruff / pytest trong `runtime/.venv` | 0.9.10 / 8.3.5 | pin 0.16.5 / 9.1.1 | lệch pin (DRIFT) | Cài đúng pin, không rủi ro |
| Python | 3.11.9 | — | chặn numpy 2.5.3, scipy 1.18.1, librosa 1.0.0 | Sự kiện lớn riêng; để sau khi xong các mục trên |
| LLM phân tích | `qwen3:8b` / `qwen3:4b` | tag không bị đẩy lại | họ mới vừa 8 GB VRAM: `qwen3.5` 4b (3,4 GB) / 9b (6,6 GB), `gemma4` e4b-it-qat (6,1 GB) / 12b-it-qat (7,2 GB) | **Ứng viên để đo** chất lượng gán người nói; cần bộ chuẩn trước khi thay |
| Model Hugging Face | VieNeu `8b7e9cff`, wav2vec2, timm, faster-whisper turbo | — | VieNeu `main` chỉ đổi `README.md` và `onnx_int8/*` (không dùng); wav2vec2, timm trùng `main`; faster-whisper turbo không đổi từ 11-2025 | Không cần làm gì |
| UTMOSv2 | commit `cc2700db` | trùng HEAD | — | Không cần làm gì |
| openai-whisper, faster-whisper, ctranslate2, imageio-ffmpeg | 20250625, 1.2.1, 4.8.2, 0.6.0 | trùng | — | Không cần làm gì |

### Giọng mới cho pool (hỏi của chủ sách, 17-09)

Metadata lấy thẳng từ `voices_v3_turbo.json` của 3.8.1, và các trường `region`/`style` khớp đúng hằng số
của `voice_catalog`. Luật cứng của `casting_presets` (đúng giới, không phải tin tức, vùng Bắc/Nam, không bị
loại) cho qua **11 giọng app chưa biết**: 7 nam (Adam bựa, Anh Khôi, Minh Quân Pro, Thiền Tâm Đức, Mạnh
Dũng — Bắc; Đức Trí, Adam — Nam) và 4 nữ (Ngọc Huyền, Quỳnh Anh — Bắc; Mỹ Duyên, Kim Thanh — Nam).
Pool nam hiện chỉ có 3 preset (Phạm Tuyên, Thanh Bình, Thái Sơn), và lô 6 cần 13/14 bậc.

Độ giống nhau giữa các giọng, tính bằng cosine của `speaker_emb` có sẵn trong file (không cần GPU): cặp
giống nhất trong giọng nam mới là 0,62 (Thiền Tâm Đức ~ Adam, Adam bựa ~ Adam). Mức ấy ngang cặp Phạm Tuyên
~ Quang Sơn (0,58) mà catalog đang coi là hai người khác nhau.

Phần còn lại cần GPU (`scripts/audition_presets.py`): mỗi giọng đọc cùng câu, đo thanh điệu/WER bằng
Whisper, UTMOS, F0 và độ dài thanh quản (F3, Praat). Ngưỡng là giọng **tệ nhất đang được cast**, đo trong
cùng lượt. Trúc Ly dùng clip mới, nên số đo của giọng này trong `voice_catalog` cũng phải đo lại.

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

## faster-whisper: đã cài, đã kiểm với runtime thật (2026-09-04)

`faster-whisper 1.2.1` + `ctranslate2 4.8.2` đã cài vào venv của dự án. Đây là **sự kiện
phiên bản**: nó đổi `installed_dependency_provenance()`, tức đổi quality-policy hash, nên
mọi project đang dở phải xác minh lại. Cài lúc alpha.32 đã chạy xong nên không phá lần chạy
nào.

**Chưa bật.** `asr.engine` mặc định `"openai"`. Một project bật nó bằng settings, có chủ ý.

### Đo được gì

| | |
|---|---|
| 200 bản thu của alpha.25 | 0,77 s/bản → **0,37 s/bản** (2,07×) |
| bất đồng verdict | **0/200** |
| 3 bản thu qua đúng `WhisperVerifier` | 2,6s → **1,3s**, bản ghi **giống hệt từng chữ** |

Phép đo cuối là quan trọng nhất: nó đi qua bộ điều hợp thật chứ không phải stub, nên nó
kiểm luôn phần mà test đơn vị không chạm được — ghép mảnh, mốc thời gian cho phép kiểm ảo
giác, và `beam_size=1` thay cho "thiếu tham số".

### Chi tiết cài đặt: nhập torch trước là đủ

Tài liệu trước đây của tôi nói phải chép `cublas64_12.dll`, `cublasLt64_12.dll`,
`cudnn*64_9.dll` từ `torch/lib` sang cạnh package `ctranslate2`. **Trong venv của dự án thì
không cần.** CTranslate2 liên kết cuBLAS/cuDNN lúc nạp và không kèm chúng; torch thì có, và
`import torch` trước `from faster_whisper import WhisperModel` đưa chúng vào tiến trình.
`WhisperVerifier._load_faster` làm đúng thứ tự đó có chủ đích.

Việc chép DLL chỉ cần trong một venv **không có torch** — đó là tình huống của venv
scratchpad lúc đo, và ở đó `os.add_dll_directory` lẫn PATH kiểu POSIX đều không đủ.

Model CT2 tải từ `mobiuslabsgmbh/faster-whisper-large-v3-turbo` qua Hugging Face Hub, nằm
trong `runtime/models/huggingface`. Trên Windows không bật Developer Mode thì cache không
dùng symlink được và tốn thêm dung lượng — cảnh báo vô hại.

## Hai venv, và cái bẫy mất mười lăm phút (2026-09-06)

Dự án có **hai** môi trường, và chúng không thay thế được cho nhau:

| đường dẫn | dùng cho | có gì |
|---|---|---|
| `_internal/.venv` | script, test, truy vấn SQLite | 209 gói, torch 2.13.0, **không có** torchaudio/librosa/transformers/utmosv2 |
| `_internal/runtime/.venv` | **mọi lệnh CLI thật** | torch 2.11.0+cu128, CUDA True, đủ ngăn xếp ML |

Chạy `python -m ebook_reader.cli resume` bằng `_internal/.venv` cho ra:

```
BackgroundStartError: High-quality runtime contract is invalid:
dependency:torch: 2.13.0 (expected 2.11.0+cu128); ...
dependency:torchaudio: import failed: ModuleNotFoundError
```

Thông báo ấy **đọc y hệt như một venv vừa bị hỏng**, và nó nêu đúng đường dẫn interpreter
đang dùng — nhưng không nói rằng đó là interpreter sai. Tôi đã đi tìm kẻ đã gỡ gói: xem
mtime của `site-packages` (đổi, nhưng chỉ vì `__pycache__`), xem `uv.lock` (không đổi từ
04-09), tìm tiến trình cài đặt (không có). Chỉ tới khi thấy `torch-2.13.0.dist-info` đề ngày
**03-08** mới rõ: venv này chưa bao giờ có ngăn xếp ML, và nó không phải venv đang chạy.

**Luôn dùng `_internal/runtime/.venv/Scripts/python.exe` cho mọi lệnh `ebook_reader.cli`.**
Tài liệu này và `VERSIONS.md` vẫn luôn ghi `runtime/.venv`; cái sai là thói quen gõ tắt.

Dấu hiệu nhận ra ngay: nếu lỗi liệt kê **nhiều** gói cùng thiếu và torch lệch phiên bản
trong khi một run vừa chạy xong bình thường, đó là sai interpreter, không phải hỏng môi
trường. Một môi trường hỏng thật thì run đang chạy cũng đã chết.

## Bản mới thượng nguồn: đọc changelog rồi quyết (2026-09-18, 02:0x)

`pip list --outdated` trên `runtime/.venv` cộng với changelog từng gói. Cột cuối là việc phải làm,
không phải "nên nâng" chung chung.

| gói | đang cài | mới nhất | changelog nói gì đáng kể | quyết |
|---|---|---|---|---|
| `vieneu` | 3.3.0 | 3.8.1 | nhanh ~7,5 lần; clip mẫu Trúc Ly đổi; thêm giọng | **chờ tai chủ sách** (trang nghe), nâng ở ranh giới 6 nếu không giọng nào tệ đi |
| `transformers` | 5.16.1 | 5.17.0 | "stop synchronizing the accelerator on every decode step" (#47975) — bớt đồng bộ mỗi bước sinh; "prevent unconditionally downloading remote hub files during generation" (#48620) — đúng loại lỗi đã dời `refs/main` hôm 17-09; RoPE 2D/3D dồn về `modeling_rope_utils.py` (**breaking** cho mã tự xếp grid) | đáng nâng, nhưng **phải đo lại âm thanh**: VieNeu sinh qua transformers, nên thay đổi ở đường sinh có thể đổi giọng. Đo trên venv riêng có torch/transformers RIÊNG (overlay `venv-vieneu381` dùng chung site-packages nên không đo được) |
| `huggingface-hub` | 1.29.0 | 1.32.0 | 1.30 ghi revision đã giải xuống `refs/` để lượt sau offline dùng lại; 1.31 ghi `refs/` nguyên tử (hết đua khi nhiều `snapshot_download`); 1.32 chia sẻ blob Xet giữa các repo | nâng cùng transformers, và **kiểm `runtime_contract` về revision giọng** trước: chính `refs/` là chỗ đã hỏng hôm 17-09 |
| `torch` / `torchvision` | 2.11.0+cu128 / 0.26.0 | 2.14.0 / 0.29.0 | wheel CUDA 12.8/12.9/13.x; **"enable eligible fused SDPA backends for dense rank-3 inputs"** — đổi số học và cả chuỗi RNG của dropout; TorchScript bắt đầu cảnh báo | **coi như một lần đổi giọng**, không phải nâng gói thường: cùng seed có thể ra audio khác. Chỉ thử sau khi cài driver 592.47 (mở đường cu130 cho sm_120 của RTX 5060), trên venv riêng, và chỉ giữa hai cuốn |
| `pyworld` | 0.3.5 | 0.3.6 | chỉ sửa build (bản 0.3.6 vá lỗi biên dịch) | nâng khi rảnh, không gấp |
| `pytest` / `ruff` | 8.3.5 / 0.9.10 | 9.1.1 / 0.16.8 | — | **đây là LỆCH, không phải bản mới**: `pyproject.toml` đã ghim `pytest==9.1.1`, `ruff==0.16.5` mà venv vẫn giữ bản cũ. Sửa ở ranh giới bằng cách cài đúng bản ghim (đổi gói là đổi hash chính sách chất lượng, không làm giữa lô) |

**Kiểm lại 18-09 12:1x** (`check_dependency_updates.py`, giữa ranh giới 6):

- `vieneu` **đã nâng lên 3.8.1** ở ranh giới 6 sau khi chủ sách chấm (commit e0df5a7; wheel khớp sha256
  trong `uv.lock`). Tag SDK mới nhất vẫn là v3.8.1. 25 giọng dựng sẵn nằm TRONG wheel
  (`assets/voices_v3_turbo.json`), không trong repo model - nên nâng SDK không kéo theo đổi revision model.
- `pnnbao-ump/VieNeu-TTS-v3-Turbo` `main` đổi 6 file, cả 6 trong `onnx_int8/` (+ README). Dây chuyền
  ghim `8b7e9cf` và chạy đường torch, không đọc `onnx_int8/` - không có gì phải làm; ghi lại để lần sau
  không đọc nhầm thành "model đã đổi".
- `pytest` / `ruff` vẫn LỆCH khỏi bản ghim (8.3.5 / 0.9.10 so với 9.1.1 / 0.16.5). Sửa ở **ranh giới 7**:
  giữa ranh giới 6 thì bước 6 còn phải tự chạy bộ test trước khi thả lô 7, và đổi pytest ngay trước đó là
  đặt cược lô 7 vào một phiên bản test runner chưa ai chạy thử.
  **ĐÃ SỬA sớm hơn, 19-09 00:2x, giữa lô 7** — an toàn vì dây chuyền không import `pytest` (grep
  `ebook_reader/`: 0) và `ruff` là công cụ ngoài. Wheel tải về đối chiếu sha256 với `uv.lock` (khớp cả
  hai), cài `--no-deps --no-index` từ chính file ấy; phụ thuộc (pluggy 1.6.0, iniconfig 2.3.0, packaging
  26.2) vốn đã khớp khoá. Bộ test đầy đủ dưới pytest 9.1.1: **2967 passed**, không đỏ, không cảnh báo mới.
  `ruff check` 0.16.5 báo 1066 mục — ruff KHÔNG phải cổng của dự án, phần lớn là văn phong. Lọc những
  loại có thể là lỗi thật (F821, B015, B006, F841, PERF102): một cái thật ở test —
  `test_character_casting.py:1210` viết `assert_voice_stability(...) is None` THIẾU `assert`, nên phép so
  bị vứt đi; đã thêm. `character_registry.py:328` dùng `"Sequence[str]"` trong chú thích kiểu dạng chuỗi
  mà không import (F821): vô hại lúc chạy, nhưng file bị khoá — lần vá kế tiếp chạm file ấy thì thêm
  `from typing import Sequence`.

**Ollama, soát 19-09 07:3x** (điều kiện ghi ở bảng 17-09: "trước khi nâng, soát `options` app gửi").
Máy chủ đang chạy 0.33.2; mới nhất 0.34.2 (15-09). Đọc ghi chú phát hành: 0.33.3 "Honor GGUF model defined
default parameters"; 0.34.1 ngưỡng phát hiện lặp token lên 100, `typical_p` không đặt được khi tạo model
mới; 0.34.2 chỉ là giao diện cài đặt lần đầu và một lỗi bộ nhớ của MLX - không đụng dây chuyền.
`analysis.py` gửi tường minh `temperature`, `seed`, `num_ctx`, `num_predict` (và `temperature 0.0` cho các
lượt hỏi đáp), KHÔNG gửi `top_k`/`top_p`/`min_p`/`repeat_penalty`. `/api/show qwen3:8b`: các giá trị ấy đến
từ lớp tham số của model trong kho (`top_p 0.95`, `top_k 20`, `repeat_penalty 1`), còn siêu dữ liệu GGUF
**không có khoá `sampling` nào** - nên thay đổi của 0.33.3 không có gì để áp cho model đang dùng. Kết
luận: nâng lên 0.34.2 không đổi cách lấy mẫu; rủi ro thấp. Nâng ở một ranh giới (máy chủ đang phục vụ
bước phân tích), bằng bản cài chính thức - việc tải bản cài để chủ sách quyết. Nếu sau này đổi sang model
nhập từ GGUF (qwen3.5/gemma4 trong mục "Model chỉ đạo diễn xuất"), phải truyền tường minh cả bốn tham số.

### Cái tìm được nhờ đọc changelog: năm chốt chặn tải mạng đã chết

`transformers` 5.x dọn cả cờ offline lẫn đường dẫn cache về `huggingface_hub`, nên năm mục transformers
trong `worker._apply_model_network_policy` / `_apply_model_cache_policy` không còn tồn tại và vòng lặp
`hasattr` lặng lẽ bỏ qua. Dây chuyền không hở (biến môi trường + `huggingface_hub.constants` vẫn chốt,
`transformers.utils.hub.is_offline_mode()` trả về đúng cờ ấy), nhưng mã đọc như đang có chốt.
`tests/test_offline_guard_names.py` nay soi thư viện THẬT: mục còn sống phải còn, mục đã chết phải vẫn
chết, và bật cờ thì transformers phải thành offline. Dọn mã: `patch_a_dead_belt_should_not_look_like_a_belt.py`
đã xếp trong `ORDER`.

### Model phân tích: hai họ mới, và vì sao nó không nằm cùng bảng với các gói (18-09, 06:0x)

`qwen3.5` (bản 9b: 6,6 GB) và `gemma4` (e2b: 7,2 GB; 12b: 7,6 GB — vượt ngân sách 7,5 GB) đã có trên
thư viện Ollama. Dự án đang dùng `qwen3:8b`. Đây **không** phải một dòng trong bảng nâng gói: tên
model nằm trong `settings` nên không vào hash chính sách chất lượng, mà đổi nó thì đổi chỉ dẫn diễn
xuất → đổi âm thanh → mọi phán quyết tai người cho chương cũ hết hiệu lực. Cách đo và điều kiện đổi:
mục *"Model chỉ đạo diễn xuất"* trong `docs/OPTIMISATION_QUEUE.md`.

## Mốc driver 18-09-2026 (giữa lô 6 và lô 7)

Chủ sách cài bộ driver của đúng máy (Lecoo N176, AMD) sau khi lô 6 xong lúc 08:28:55 — tức **không lô
nào bị cắt ngang**, và mọi chương từ lô 7 trở đi được thu trên driver mới.

| thành phần | trước | sau |
|---|---|---|
| BIOS | N176DRLKV2222 | **N176DRLKV2525** |
| NVIDIA RTX 5060 Laptop | 32.0.15.8180 (Game Ready 581.80) | **32.0.15.9247 (592.47, bản Lenovo, `nvlt.inf` khớp `SUBSYS_380317AA`)** |
| AMD Radeon 610M | 32.0.13050.18 | **32.0.21038.6** |
| Senary Audio / WiFi / BT / LAN | 3.48.60.19 / 6001.15.156.0 / 18.4017… / 1168.22… | 3.48.109.0 / 6001.15.163.0 / 18.4038.2509.1901 / 1168.28.50.1224 |

Kiểm ngay sau khi cài (09:2x), trước khi chạy lại bất cứ thứ gì có GPU:

    nvidia-smi               592.47, CUDA 13.1, 8151 MiB, P5, 47°C
    torch 2.11.0+cu128       cuda True, cuDNN 9.19, RTX 5060 Laptop sm_120; matmul fp16 4096 x20 = 0,24 s
    cli doctor               failures: []  (VRAM trống 7.275 MiB; VieNeu 8b7e9cff; UTMOS sẵn sàng)

MUX (独显直连) bật suốt: RTX 5060 xuất hình trực tiếp 2560×1600 @ 180 Hz. Hai lần khởi động sau khi cài
(09:15 khởi động lại, 09:20 tắt/bật) đều lên hình — lỗi cũ của 581.80-thế-hệ-mới ("mỗi lần mở máy phải
bấm Win+Shift+B") chưa thấy lại; theo dõi thêm ở những lần bật máy sau.

**Điều driver mới mở ra:** CUDA 13.1 ở phía driver nghĩa là wheel `torch` cu130 (có từ 2.14) chạy được
trên máy này. Nhưng nâng torch là một lần **đổi giọng** (xem mục torch 2.14 phía trên: SDPA hợp nhất đổi
số học và RNG), nên nó vẫn chờ giữa hai cuốn, không phải việc của ranh giới này.

## Kiểm 2026-09-20 10:3x (giữa lô 10) — không có tin mới, và đó là tin tốt

`check_dependency_updates.py` báo 6 gói sau PyPI: `pyworld`, `torch`, `torchvision`, `huggingface-hub`,
`transformers`, `ruff`. Đối chiếu bảng quyết định 18-09 ở trên thì **không một mục nào là tin mới**:

| mục | trạng thái hôm nay |
|---|---|
| `torch` 2.14 / `torchvision` 0.29 | vẫn là "một lần đổi giọng", chờ **giữa hai cuốn**. Driver 592.47 mở CUDA 13.1 nên wheel cu130 (2.14.0) chạy được - đường đã mở, quyết định vẫn chưa tới hạn |
| `transformers` 5.17 + `huggingface-hub` 1.32 | vẫn "đáng nâng, phải ĐO LẠI ÂM THANH trên venv riêng" - việc GPU, chưa làm được khi lô còn chạy |
| `pyworld` 0.3.6 | chỉ sửa build, không gấp |
| `ruff` | LỆCH khỏi bản ghim, không phải bản mới; `pyproject.toml` ghim 0.16.5, venv giữ 0.9.10 (`pytest` đã sửa 19-09). Ruff không phải cổng của dự án |
| `pnnbao-ump/VieNeu-TTS-v3-Turbo` `main` đổi 6 file | vẫn đúng 6 file `onnx_int8/` + README như 18-09; dây chuyền ghim `8b7e9cf` và đi đường torch, không đọc `onnx_int8/` |
| SDK `vieneu` | tag mới nhất vẫn v3.8.1 = bản đang cài |

Vì sao vẫn ghi lại một lượt kiểm "không có gì": việc thường trực là **kiểm định kỳ và báo cáo**, và một
lượt kiểm im lặng chỉ đáng tin khi có dấu vết rằng nó đã chạy. Lần sau đọc bảng này trước khi chạy lại
script - ba trong sáu mục là quyết định ĐÃ CÓ, không phải việc còn tồn.

## Kiểm 2026-09-21 04:5x (không có lô nào bay) — vẫn im, và một dòng mới về `ruff`

Cùng sáu gói, cùng kết luận như bảng 20-09 ngay trên: `torch` 2.14 / `torchvision` 0.29 chờ **giữa hai
cuốn**, `transformers` 5.17 + `huggingface-hub` 1.32 chờ một lượt **đo lại âm thanh**, `pyworld` 0.3.6 chỉ
sửa build, VieNeu SDK vẫn v3.8.1, `main` của `VieNeu-TTS-v3-Turbo` vẫn đúng 6 file `onnx_int8/` + README.

Hai điều đáng thêm, không phải quyết định:

- **`ruff` nay đã KHỚP bản ghim 0.16.5** (bảng 20-09 còn ghi venv giữ 0.9.10). `ruff check .` hôm nay báo
  **1.177** mục, so với 1.066 hôm 19-09 - tăng vì cây có thêm mã, không phải vì luật đổi. Ruff không phải
  cổng của dự án; **cổng là `pytest`, và nó xanh toàn bộ** ở lượt kiểm 04:4x hôm nay.
- Lượt kiểm này chạy khi **GPU đang bị lượt so model chiếm** nên vẫn không làm được phép đo âm thanh cho
  `transformers` - lý do trì hoãn hôm nay giống hôm qua nhưng KHÁC nguyên nhân (hôm qua vì lô đang thu).
  Ghi rõ để lần sau không đọc thành "đã bỏ quên hai ngày".

Nhắc lại vì sao vẫn ghi một lượt kiểm rỗng: việc thường trực là kiểm định kỳ **và báo cáo**, và một lượt
kiểm im lặng chỉ đáng tin khi có dấu vết rằng nó đã chạy.

## Kiểm 2026-09-24 23:1x (giữa lô 17, pha phân tích) — ba gói mới, không cái nào chạm âm thanh

Lượt kiểm bị trễ 90 giờ (dòng đỏ trong nhịp tim nhắc). Sáu mục cũ giữ nguyên quyết định của bảng 20-09. Mới:

| mục | đọc diff/changelog | quyết định |
|---|---|---|
| `vieneu` 3.8.2 + 3.8.3 (23-09) | diff `v3.8.1...v3.8.3` trong `src/`: một dòng trong `voices_v3_turbo.json` + một chú thích - **đổi tên ba giọng** Minh Quân Pro → Hải Đăng, Anh Khôi → Thiện Minh, Mạnh Dũng → Quốc Tuấn, tên cũ vẫn dùng được qua `aliases`. Còn lại là README và `finetune/` (LoRA một giọng) | **không nâng**: engine và audio y hệt. Khi nào nâng (giữa hai cuốn) thì `voice_catalog.py` đổi tên hiển thị cùng lúc, nhưng khoá giọng theo tên cũ của sách vẫn sống nhờ alias |
| `sea-g2p` 0.10.0 (23-09) | 4 commit, đều là C ABI: tách PyO3 ra sau feature `python`, `normalize_batch` thành vỏ bọc mỏng; logic tách âm tiếng Việt không đổi | **không nâng**: `asr.py` chỉ dùng `G2P` để so âm vị tên riêng; không có gì cho ta |
| `timm` 1.0.30 (22-09) | phụ thuộc của UTMOSv2, ràng với cache revision đã khoá | **không nâng**, theo luật chung ở đầu file |
| `pnnbao-ump/VieNeu-TTS-v3-Turbo` `main` đổi **60 file** (trước 6) | thêm thư mục `gguf/` (bf16, q8_0, `voices/*`) cho bộ đọc audio.cpp mới của VieNeu Desktop 0.18.5 (nhanh gấp 3 trên máy họ) | dây chuyền ghim `8b7e9cf` và đi đường torch, không đọc `gguf/`. **Ghi lại làm ứng viên tốc độ** giữa hai cuốn: nếu SDK Python có đường audio.cpp thì phải ĐO lại toàn bộ ngân sách frame và nghe lại, vì đó là engine khác |
