# Test report — v0.2.0-alpha.8

Ngày cập nhật: 2026-08-01

Trạng thái source hiện tại: **33 test được định nghĩa**. Checkout này chưa có `_internal/runtime`, nên
chưa chạy lại pytest sau thay đổi alpha.8; setup bắt buộc phải chạy đủ test và system check trước khi ghi marker hoàn tất.

## Phạm vi tự động

- settings bất biến và cấm prompt/silent replacement;
- import nhiều TXT hoặc folder, natural sort và loại file không hợp lệ;
- one-click startup qua `START.bat`;
- root layout tối giản và naming `e_book_reader` nhất quán;
- không còn tham chiếu đến prototype/gói generate tạm;
- project lock, voice profile lock và resume;
- Resource Manager: foreground, RAM, SSD và stop policy;
- recovery: `.part`, checksum, WAV/MP3 hợp lệ;
- settings tamper, source mutation và khóa độc quyền một worker/project;
- required-analysis batch failure không được fallback ngầm;
- stereo WAV bị từ chối, ASR optional chuyển lỗi inference thành warning;
- voice-reference checksum, thermal hysteresis và cleanup full-book khi FFmpeg lỗi;
- pipeline mock không cần model;
- FFmpeg thật: ghép, khoảng nghỉ, encode và decode verify.

## Chưa xác nhận trên máy đích

- GUI PySide6 trên Windows;
- Ollama/Qwen3 8B thực tế;
- VoxCPM2 và VieNeu inference;
- Whisper Turbo GPU;
- CUDA 12.8 trên RTX 5060 Laptop;
- Windows Toast và foreground GPU detection;
- kill/resume giữa CUDA inference;
- OOM/backoff và thermal behavior dài giờ;
- tương thích dependency cuối cùng trên máy đích.

Bắt buộc smoke test một chapter 2.000–5.000 từ trước khi chạy book rất lớn.
