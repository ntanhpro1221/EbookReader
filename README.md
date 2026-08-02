# E Book Reader

Ứng dụng Windows chạy local, chuyển một hoặc nhiều chapter `.txt` tiếng Việt thành audiobook MP3 có phân vai và cảm xúc.

## Bắt đầu

1. Giải nén toàn bộ ZIP vào SSD còn đủ dung lượng.
2. Double-click **`START.vbs`**.
3. Lần đầu, file này tự cài môi trường và tải model; khi nâng cấp, setup tái sử dụng venv/model cache thay vì xóa runtime cũ.
4. Trong ứng dụng, chọn nhiều file TXT hoặc chọn một folder chứa các chapter TXT.

Khi muốn chuyển từ project đang mở sang đầu vào khác, bấm **Book mới**. Settings hiển thị của project cũ
được đồng bộ từ cấu hình đã khóa, nên thay đổi control trên màn hình không thể âm thầm đổi giọng khi resume.

Không cần mở PowerShell, không cần chạy file setup riêng.

## Những gì nằm ở thư mục gốc

```text
e_book_reader/
├── START.vbs     # file duy nhất người dùng cần mở
├── README.md     # hướng dẫn sử dụng
└── _internal/    # source, setup, test, model cache và tài liệu kỹ thuật
```

Người dùng bình thường không cần mở `_internal`. Tài liệu dành cho agent/lập trình viên cũng được giữ bên trong thư mục này.

## Cách xử lý một book

- Tool natural-sort các chapter theo tên file.
- Phân tích toàn book trước để xây character registry, bí danh, cách phát âm và voice casting thống nhất.
- Toàn bộ vai dùng catalog preset VieNeu: ưu tiên dùng hết các giọng phù hợp giới tính trước khi tái sử dụng.
- Nhân vật phụ có dấu hiệu cục bộ như “áo xanh”, “áo đỏ” được giữ thành hai vai riêng trong cuộc thoại;
  trường hợp thực sự không phân biệt được vẫn tách tối thiểu theo nam/nữ/chưa rõ.
- Mỗi nhân vật giữ nguyên một preset. Cảm xúc chỉ thay đổi cách thể hiện, nhịp và mức âm lượng hợp lý,
  không đổi sang một người đọc khác giữa chừng.
- Từ điển phát âm có confidence được checkpoint trong SQLite, áp dụng đồng nhất cho TTS và câu đối chiếu ASR.
- Sau khi khóa settings/giọng, tool tạo và kiểm tra audio theo từng chapter.
- Mỗi file TXT luôn tạo một MP3 chapter tương ứng. Tùy chọn **Tạo thêm một MP3 toàn book** mặc định tắt;
  khi bật, app ghép thêm một file MP3 toàn book sau khi tất cả chapter hoàn tất.
- Giao diện hiển thị tiến độ riêng cho chuẩn bị văn bản, phân tích, phân vai, tạo audio, Whisper,
  sửa lỗi, ghép MP3 và xuất báo cáo.
- Trong lúc chạy, tool không dừng để hỏi lựa chọn. Trường hợp mơ hồ được xử lý theo policy và ghi vào report.

## An toàn và phục hồi

- WAV/MP3 ghi qua file `.part`, kiểm tra rồi mới atomic rename.
- SQLite là nguồn trạng thái chính; không coi file tồn tại là đã hoàn tất.
- Mỗi project chỉ cho phép một worker; settings trong SQLite và source hash được kiểm tra lại khi resume.
- Byte TXT dùng để segment phải khớp đúng hash đã khóa; source đổi ngay trong lúc đọc cũng làm job dừng.
- Có thể đóng hoặc kill app bất kỳ lúc nào; phần đang dở được tạo lại, phần đã commit được giữ.
- Nút **Dừng** chờ tác vụ inference hiện tại kết thúc rồi dừng ở ranh giới an toàn; ứng dụng không còn
  cung cấp nút kill worker trực tiếp trên giao diện.
- Khi dừng cưỡng bức, app kết thúc cả cây process con (FFmpeg/Ollama helper) để tránh tiến trình mồ côi.
- Không chèn im lặng để che đoạn TTS bị lỗi.
- Mức âm lượng được cân bằng theo từng segment trước khi ghép chapter; chỉ các chỉ dẫn như thì thầm,
  quát hoặc cao trào mới chủ động lệch khỏi mức chuẩn.
- Whisper đọc và resample WAV ngay trong process, không bật FFmpeg console theo từng segment.
- Nếu phải tự dừng vì SSD/RAM/GPU/driver hoặc lỗi nghiêm trọng, app checkpoint và gửi Windows notification.
- Resource Manager tự nhường CPU/GPU/RAM/SSD cho ứng dụng foreground, sau đó tự tăng tải lại khi máy rảnh.

## Đầu ra

Mỗi book được lưu thành một project riêng với database, log, audio trung gian và thư mục `output` chứa MP3 chapter,
playlist, `pronunciations.json`, metadata tùy chọn và report. Project đã hoàn tất chỉ xác minh MP3/checksum rồi thoát nhanh,
không cần khởi động Ollama, không băm lại toàn bộ WAV hoặc ghép lại full-book nếu artifact vẫn nguyên vẹn.

## Trạng thái alpha

Kiến trúc, recovery, resource policy và pipeline mock đã có test. Các model thực, Windows notification và hành vi CUDA/RTX 5060 vẫn cần smoke test trên máy đích với một chapter khoảng 2.000–5.000 từ trước khi chạy book rất lớn.

Tài liệu kỹ thuật và kết quả test nằm trong `_internal/docs/`.
