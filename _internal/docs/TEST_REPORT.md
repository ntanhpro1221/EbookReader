# Test report

Ngày cập nhật: 2026-08-02

Trạng thái source hiện tại: **44/44 test pass** trên Python 3.11.9, gồm pronunciation/fallback,
completed fast-path, batch-local analysis ID, VoxCPM2/VieNeu API adapter, chính sách câu cực ngắn/ASR
và FFmpeg encode/decode thật.
Các dependency kiểm thử được cài trong thư mục tạm, sau đó đã xóa. `python -m compileall -q _internal` và `git diff --check` cũng pass.
`ruff 0.9.10 check _internal` và Vulture dead-code scan pass; các dependency tạm cũng đã được xóa.
Setup chỉ cài runtime dependency/model và chạy system check trên máy đích trước khi ghi marker hoàn tất;
pytest/Ruff không được cài hoặc chạy trong luồng mở app của người dùng.

## Phạm vi tự động

- settings bất biến và cấm prompt/silent replacement;
- import nhiều TXT hoặc folder, natural sort và loại file không hợp lệ;
- one-click startup ẩn qua `START.vbs`, chỉ hiện console khi cần setup;
- analysis dùng ID ngắn bị ràng buộc theo batch rồi ánh xạ chính xác về stable ID;
- project lock, voice profile lock và resume;
- Resource Manager: foreground, RAM, SSD và stop policy;
- recovery: `.part`, checksum, WAV/MP3 hợp lệ;
- settings tamper, source mutation và khóa độc quyền một worker/project;
- source đổi cùng kích thước trong cửa sổ đọc, CP1258/UTF-16 không BOM và tên output an toàn;
- warning code hợp nhất và pronunciation ưu tiên confidence cao;
- required-analysis batch failure không được fallback ngầm;
- stereo WAV bị từ chối, ASR optional chuyển lỗi inference thành warning;
- VoxCPM không gắn control prompt dài vào câu cực ngắn; dấu câu bỏ qua Whisper và ASR một từ không kích hoạt vòng tái tạo;
- voice-reference checksum, thermal hysteresis và cleanup full-book khi FFmpeg lỗi;
- pipeline mock không cần model;
- FFmpeg thật: ghép, khoảng nghỉ, encode và decode verify.
- Windows `fsync` cho WAV/silence dùng descriptor read-write, được bao phủ bởi test FFmpeg thật.

GUI PySide6 đã mở thực tế trên Windows. Qwen3 8B đã phân tích và checkpoint đủ **599/599 segment**,
hợp nhất bí danh, khóa voice casting và tạo đủ **8/8 voice reference** trên project thử. VoxCPM2 2.0.3
và VieNeu 3.2.3 preset `Phạm Tuyên` cũng đã inference thật bằng PyTorch CUDA 12.8 trên RTX 5060 Laptop,
tạo waveform 48 kHz hữu hạn.

## Chưa xác nhận trên máy đích

- chạy VoxCPM2/VieNeu trọn toàn book;
- Whisper Turbo GPU;
- Windows Toast và foreground GPU detection;
- kill/resume giữa CUDA inference;
- OOM/backoff và thermal behavior dài giờ;
- startup thực tế sau khi đóng gói release;
- bộ dependency đã pin trên máy đích.

Bắt buộc smoke test một chapter 2.000–5.000 từ trước khi chạy book rất lớn.
