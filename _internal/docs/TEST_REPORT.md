# Test report

Ngày cập nhật: 2026-08-02

Trạng thái source hiện tại: **61/61 test pass** trên Python 3.11.9, gồm pronunciation,
completed fast-path, batch-local analysis ID/NPC identity, VieNeu preset/emotion adapter,
parser dấu câu/ngoặc kép, cân mức âm lượng/tốc độ, Whisper in-process audio và FFmpeg encode/decode thật.
Các dependency kiểm thử được cài trong thư mục tạm, sau đó đã xóa. `python -m compileall -q _internal` và `git diff --check` cũng pass.
`ruff 0.9.10 check _internal` pass; các dependency kiểm thử tạm cũng đã được xóa.
Setup chỉ cài runtime dependency/model và chạy system check trên máy đích trước khi ghi marker hoàn tất;
pytest/Ruff không được cài hoặc chạy trong luồng mở app của người dùng.

## Phạm vi tự động

- settings bất biến và cấm prompt/silent replacement;
- import nhiều TXT hoặc folder, natural sort và loại file không hợp lệ;
- one-click startup ẩn qua `START.vbs`, chỉ hiện console khi cần setup;
- GUI không còn tiêu đề lớn, tự đổi nút `Bắt đầu`/`Tiếp tục`, tự mở project được chọn gần nhất;
  nút chọn TXT/folder vẫn dùng được khi project cũ đang dừng và chuyển sang book mới sau khi chọn nguồn;
  settings khóa theo project được ghi rõ, danh sách/bảng có alternate-row trung tính và selection xanh;
  nested splitter và từng cột tiến độ kéo được, kích thước cột được lưu, đường dẫn MP3 không bị elide;
  nút chính tự đổi `Bắt đầu`/`Tạm dừng`/`Tiếp tục`, chỉ còn một nút `Dừng` riêng và mặc định chỉ xuất
  MP3 theo chapter; đóng cửa sổ kết thúc cây worker mà không đợi checkpoint;
- bảng chapter hiển thị riêng tiến độ chia đoạn, phân tích, tạo audio, kiểm tra, giai đoạn và MP3;
- progress event bao phủ chuẩn bị văn bản, TTS, Whisper, repair, ghép chapter và xuất báo cáo;
- analysis dùng ID ngắn bị ràng buộc theo batch rồi ánh xạ chính xác về stable ID;
- project lock, voice profile lock và resume;
- Resource Manager: foreground, RAM, SSD và stop policy;
- recovery: kill khi đang ghi `.part`, kill sau atomic replace nhưng trước SQLite commit, checksum và
  giữ nguyên WAV/MP3 đã commit hợp lệ;
- settings tamper, source mutation và khóa độc quyền một worker/project;
- source đổi cùng kích thước trong cửa sổ đọc, CP1258/UTF-16 không BOM và tên output an toàn;
- warning code hợp nhất và pronunciation ưu tiên confidence cao;
- required-analysis batch failure không được fallback ngầm;
- stereo WAV bị từ chối, ASR optional chuyển lỗi inference thành warning;
- cụm từ đặt trong ngoặc kép không bị nhận nhầm thành hội thoại, segment chỉ có dấu câu không đi vào TTS;
- NPC có nhãn cục bộ giữ identity riêng, NPC vô danh tách nam/nữ và catalog đủ 14 preset được dùng hết
  trước khi tái sử dụng nếu book có đủ vai;
- cùng nhân vật giữ nguyên preset khi emotion delivery thay đổi; mức âm lượng trung tính được cân bằng
  còn chỉ dẫn loud vẫn được giữ lớn hơn có chủ đích;
- Whisper nhận waveform mono 16 kHz được đọc/resample trong process, không gọi FFmpeg theo từng WAV;
- thermal hysteresis và cleanup full-book khi FFmpeg lỗi;
- pipeline mock không cần model;
- FFmpeg thật: ghép, khoảng nghỉ, encode và decode verify.
- Windows `fsync` cho WAV/silence dùng descriptor read-write, được bao phủ bởi test FFmpeg thật.

GUI PySide6 đã mở thực tế trên Windows. Ở phiên bản trước refactor này, Qwen3 8B đã phân tích và
checkpoint đủ **599/599 segment**; VieNeu 3.2.3 preset `Phạm Tuyên` đã inference thật bằng PyTorch
CUDA 12.8 trên RTX 5060 Laptop và tạo waveform 48 kHz hữu hạn. Casting VieNeu-only và emotion delivery
mới chưa được inference xuyên suốt chapter thật sau thay đổi này.

## Chưa xác nhận trên máy đích

- chạy VieNeu-only trọn toàn book với nhiều preset và emotion delivery;
- Whisper Turbo GPU;
- Windows Toast và foreground GPU detection;
- kill/resume giữa CUDA inference;
- OOM/backoff và thermal behavior dài giờ;
- startup thực tế sau khi đóng gói release;
- bộ dependency đã pin trên máy đích.

Bắt buộc smoke test một chapter 2.000–5.000 từ trước khi chạy book rất lớn.
