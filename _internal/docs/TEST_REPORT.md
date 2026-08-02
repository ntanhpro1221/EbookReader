# Test report

Ngày cập nhật: 2026-08-02

Trạng thái source hiện tại: **88/88 test pass** trên Python 3.11.9, gồm pronunciation,
completed fast-path, batch-local analysis ID/NPC identity, VieNeu preset/emotion adapter,
parser dấu câu/ngoặc kép, cân mức âm lượng/tốc độ, Whisper in-process audio và FFmpeg encode/decode thật.
Các dependency kiểm thử được cài trong thư mục tạm, sau đó đã xóa. Compileall cho source/test và `git diff --check` cũng pass.
`ruff 0.9.10 check _internal` pass; các dependency kiểm thử tạm cũng đã được xóa.
Setup chỉ cài runtime dependency/model và chạy system check trên máy đích trước khi ghi marker hoàn tất;
pytest/Ruff không được cài hoặc chạy trong luồng mở app của người dùng.

## Phạm vi tự động

- settings bất biến và cấm prompt/silent replacement;
- import nhiều TXT hoặc folder, natural sort và loại file không hợp lệ;
- one-click startup qua shortcut `Ebook Reader` ở root/Start Menu trỏ thẳng tới `_internal\Ebook Reader.vbs`;
  console hiện ngay, báo tiến độ và tự đóng theo ready marker do GUI ghi sau khi render, còn lỗi giữ console để đọc;
- single-instance dùng local IPC: lần mở thứ hai chỉ kích hoạt/đưa cửa sổ đang chạy lên trước rồi đóng launcher;
- system tray có hành động hiện/ẩn/thoát hoàn toàn; nút `X` chỉ ẩn và giữ worker chạy, còn thoát từ tray
  kết thúc cây worker ngay;
- GUI không còn tiêu đề lớn, tự đổi nút `Bắt đầu`/`Tiếp tục`, tự mở project được chọn gần nhất;
  `Bắt đầu` bị vô hiệu hóa khi chưa có chapter nguồn và mỗi dòng Log có timestamp;
  nút chọn TXT/folder vẫn dùng được khi project cũ đang dừng và chuyển sang book mới sau khi chọn nguồn;
  khối `Thiết lập` chỉnh được ngay sau khi mở lại và thay đổi sẽ tạo project mới theo settings hash;
  thêm/xóa TXT tạo draft mới mà không sửa sách cũ; bốn nút nguồn có cùng kích thước; danh sách/bảng
  có alternate-row tối hơn nền thường và selection dùng đúng màu highlight của ô Log kể cả khi mất focus;
  nested splitter và từng cột tiến độ kéo được, kích thước cột được lưu, đường dẫn MP3 không bị elide;
  nhấn lặp vào ô MP3 dài không làm bảng tự kéo thanh cuộn ngang sau độ trễ double-click;
  nút chính tự đổi `Bắt đầu`/`Tạm dừng`/`Tiếp tục`, chỉ còn một nút `Dừng` riêng và chỉ xuất MP3
  theo từng chapter nguồn; WAV checkpoint bắt buộc được giữ nội bộ, không hiển thị như một tùy chọn;
  đóng cửa sổ kết thúc cây worker mà không đợi checkpoint;
- bảng chapter hiển thị riêng tiến độ phân tích, tạo audio, kiểm tra, giai đoạn và MP3;
- double-click ô MP3 trống không mở Explorer;
- progress event bao phủ chuẩn bị văn bản, TTS, Whisper, repair, ghép chapter và xuất báo cáo;
- analysis dùng ID ngắn bị ràng buộc theo batch rồi ánh xạ chính xác về stable ID;
- Ollama analysis/alias chạy dạng stream có thể hủy khi dừng, giới hạn schema/token/wall-time và ghi
  heartbeat vào Log mỗi phút để không còn im lặng trong một request dài;
- Ollama server do worker tự khởi động chạy ẩn, được theo dõi quyền sở hữu và chỉ tiến trình do app tạo
  mới bị dừng sau giai đoạn phân tích;
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
- vocal-effect (`ha...`, `haiz...`, thẻ VieNeu) và từ tượng thanh (`rầm`, `uỳnh`...) được tách thành
  segment checkpoint riêng; effect dùng giới hạn thời lượng riêng và bỏ qua kiểm tra tốc độ/Whisper;
- giới hạn frame VieNeu thay đổi theo độ dài/pace để câu ngắn không chạy tới trần model; lệch pace nhẹ
  trở thành warning còn sai lệch cực đoan vẫn bị từ chối;
- NPC có nhãn cục bộ giữ identity riêng, NPC vô danh tách nam/nữ; phân vai loại hoàn toàn preset tin tức,
  ưu tiên Bắc → Nam và tự nhiên → kể chuyện, chỉ đưa giọng Trung vào pool NPC ngắn;
- dropdown người kể có đủ 10 preset không phải tin tức; bộ lọc giới tính và miền không làm thay đổi
  preset đang chọn nếu preset đó vẫn còn trong kết quả lọc; label `Giọng người kể` là header foldout có
  chevron nhỏ ở cuối, bên dưới là ba dòng con chỉ thụt nhẹ và có label riêng cho giới tính, miền và nghe thử;
  Thái Sơn và Ngọc Linh đứng đầu danh sách;
- thay đổi narrator trực tiếp tự phát preview, nút preview phát lại; 10 WAV không phải tin tức được đóng gói
  bằng package-data và mapping preset nào cũng phải trỏ tới file tồn tại;
- profile chất lượng và narrator được khóa theo sách; resource mode và ngưỡng GPU là global, không detach
  sách đang mở và có thể cập nhật AdaptiveResourceManager khi worker đang chạy;
- cùng nhân vật giữ nguyên preset và biến thể cao độ tối đa ±2 bán âm; thought thử lại đủ số lần để tìm
  speaker nhân vật, chỉ fallback sang NARRATOR kèm warning khi vẫn không xác định được;
  mức âm lượng trung tính được cân bằng
  còn chỉ dẫn loud vẫn được giữ lớn hơn có chủ đích;
- Whisper nhận waveform mono 16 kHz được đọc/resample trong process, không gọi FFmpeg theo từng WAV;
- thermal hysteresis, atomic chapter assembly và cleanup file `.part` trong recovery;
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
