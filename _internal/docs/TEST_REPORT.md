# Test report

Ngày cập nhật: 2026-08-02

Trạng thái source hiện tại: **37/37 test pass** trên Python hệ thống 3.11.9, gồm pronunciation/fallback,
completed fast-path và FFmpeg encode/decode thật.
Các dependency kiểm thử được cài trong thư mục tạm, sau đó đã xóa. `python -m compileall -q _internal` và `git diff --check` cũng pass.
`ruff 0.9.10 check _internal` và Vulture dead-code scan pass; các dependency tạm cũng đã được xóa.
Setup chỉ cài runtime dependency/model và chạy system check trên máy đích trước khi ghi marker hoàn tất;
pytest/Ruff không được cài hoặc chạy trong luồng mở app của người dùng.

## Phạm vi tự động

- settings bất biến và cấm prompt/silent replacement;
- import nhiều TXT hoặc folder, natural sort và loại file không hợp lệ;
- one-click startup qua `START.bat`;
- project lock, voice profile lock và resume;
- Resource Manager: foreground, RAM, SSD và stop policy;
- recovery: `.part`, checksum, WAV/MP3 hợp lệ;
- settings tamper, source mutation và khóa độc quyền một worker/project;
- source đổi cùng kích thước trong cửa sổ đọc, CP1258/UTF-16 không BOM và tên output an toàn;
- warning code hợp nhất và pronunciation ưu tiên confidence cao;
- required-analysis batch failure không được fallback ngầm;
- stereo WAV bị từ chối, ASR optional chuyển lỗi inference thành warning;
- voice-reference checksum, thermal hysteresis và cleanup full-book khi FFmpeg lỗi;
- pipeline mock không cần model;
- FFmpeg thật: ghép, khoảng nghỉ, encode và decode verify.
- Windows `fsync` cho WAV/silence dùng descriptor read-write, được bao phủ bởi test FFmpeg thật.

## Chưa xác nhận trên máy đích

- GUI PySide6 trên Windows;
- Ollama/Qwen3 8B thực tế;
- VoxCPM2 và VieNeu inference;
- Whisper Turbo GPU;
- CUDA 12.8 trên RTX 5060 Laptop;
- Windows Toast và foreground GPU detection;
- kill/resume giữa CUDA inference;
- OOM/backoff và thermal behavior dài giờ;
- startup thực tế sau khi đóng gói release;
- bộ dependency đã pin trên máy đích.

Bắt buộc smoke test một chapter 2.000–5.000 từ trước khi chạy book rất lớn.
