# E Book Reader

Ứng dụng Windows chạy local, chuyển một hoặc nhiều chapter `.txt` tiếng Việt thành audiobook MP3 có phân vai và cảm xúc.

## Bắt đầu

1. Giải nén toàn bộ ZIP vào SSD còn đủ dung lượng.
2. Double-click **`E Book Reader.vbs`** hoặc mở **E Book Reader** từ Start Menu.
3. Lần đầu, file này tự cài môi trường và tải model; khi nâng cấp, setup tái sử dụng venv/model cache thay vì xóa runtime cũ.
4. Trong ứng dụng, chọn nhiều file TXT hoặc chọn một folder chứa các chapter TXT.

Khi muốn chuyển từ project đang mở sang đầu vào khác, bấm **Book mới**. Settings hiển thị của project cũ
được đồng bộ từ cấu hình đã khóa, nên thay đổi control trên màn hình không thể âm thầm đổi giọng khi resume.

Không cần mở PowerShell, không cần chạy file setup riêng.

## Những gì nằm ở thư mục gốc

```text
e_book_reader/
├── E Book Reader.vbs  # launcher có tên ứng dụng; shortcut Start Menu dùng icon riêng
├── README.md     # hướng dẫn sử dụng
└── _internal/    # source, setup, test, model cache và tài liệu kỹ thuật
```

Người dùng bình thường không cần mở `_internal`. Tài liệu dành cho agent/lập trình viên cũng được giữ bên trong thư mục này.

## Cách xử lý một book

- Tool natural-sort các chapter theo tên file.
- Phân tích toàn book trước để xây character registry, bí danh, cách phát âm và voice casting thống nhất.
- Người dùng lọc preset người kể theo giới tính và miền ngay trong Thiết lập; dropdown giọng chứa
  toàn bộ giọng Bắc, Nam và Trung không thuộc kiểu tin tức. Bên dưới dropdown là foldout `Tùy chọn giọng`:
  hai bộ lọc và nút preview nằm trên một hàng thụt vào; Thái Sơn, Ngọc Linh đứng đầu danh sách.
- Chọn một preset trong dropdown sẽ tự phát WAV preview; nút `Phát preview` cho phép nghe lại. App đóng gói
  sẵn preview cho cả 10 preset hợp lệ nên không nạp model TTS chỉ để nghe thử.
- Chất lượng và giọng người kể được lưu cùng sách và khóa sau khi sách bắt đầu. Chế độ tài nguyên
  và ngưỡng GPU là setting global, không tạo sách mới khi thay đổi và được worker nhận tại checkpoint kế tiếp.
- Nhân vật có tên được ưu tiên giọng theo thứ tự Bắc → Nam, rồi tự nhiên → kể chuyện. Preset tin tức không được
  phân vai; giọng Trung chỉ tham gia pool NPC vô danh/cục bộ ngắn sau các giọng phổ thông để tăng đa dạng có kiểm soát.
- Nhân vật phụ có dấu hiệu cục bộ như “áo xanh”, “áo đỏ” được giữ thành hai vai riêng trong cuộc thoại;
  trường hợp thực sự không phân biệt được vẫn tách tối thiểu theo nam/nữ/chưa rõ.
- Mỗi nhân vật giữ nguyên một preset và một biến thể cao độ tối đa ±2 bán âm. Khi nhiều vai dùng chung preset,
  biến thể cao độ tạo khác biệt vừa phải mà không đổi tốc độ; cảm xúc không đổi sang người đọc khác giữa chừng.
- Độc thoại nội tâm ưu tiên bắt buộc giọng đã khóa của nhân vật đang nghĩ; chỉ sau khi phân tích hết số
  lần thử mà vẫn không xác định được nhân vật thì mới fallback sang giọng người kể và ghi warning.
- Từ điển phát âm có confidence được checkpoint trong SQLite, áp dụng đồng nhất cho TTS và câu đối chiếu ASR.
- Sau khi khóa settings/giọng, tool tạo và kiểm tra audio theo từng chapter.
- Mỗi file TXT luôn tạo đúng một MP3 chapter tương ứng; app không tự ghép thêm MP3 toàn book.
- Vocal-effect đứng riêng như `ha...`, `haiz...`, `[cười]`, `[thở dài]`, `[hắng giọng]` và từ tượng thanh
  như `rầm`, `uỳnh` được tách thành segment độc lập, giữ đúng vị trí khi ghép chapter.
- Vocal-effect dùng thẻ phi ngôn ngữ gốc của VieNeu. Từ tượng thanh vẫn do TTS đọc, không giả làm file hiệu ứng âm thanh thật.
- Giao diện hiển thị tiến độ riêng cho chuẩn bị văn bản, phân tích, phân vai, tạo audio, Whisper,
  sửa lỗi, ghép MP3 và xuất báo cáo.
- Nút **Bắt đầu** chỉ bật khi đã có chapter nguồn. Mỗi dòng Log có timestamp để phân biệt tiến trình
  đang chạy với thông tin cũ.
- Trong lúc chạy, tool không dừng để hỏi lựa chọn. Trường hợp mơ hồ được xử lý theo policy và ghi vào report.

## An toàn và phục hồi

- WAV/MP3 ghi qua file `.part`, kiểm tra rồi mới atomic rename.
- SQLite là nguồn trạng thái chính; không coi file tồn tại là đã hoàn tất.
- Mỗi project chỉ cho phép một worker; settings trong SQLite và source hash được kiểm tra lại khi resume.
- Byte TXT dùng để segment phải khớp đúng hash đã khóa; source đổi ngay trong lúc đọc cũng làm job dừng.
- Có thể đóng hoặc kill app bất kỳ lúc nào; phần đang dở được tạo lại, phần đã commit được giữ.
- Giao diện chỉ có một nút **Dừng**; worker kết thúc ở ranh giới gần nhất và lần sau có thể tiếp tục.
- Bấm `X` chỉ ẩn cửa sổ xuống system tray để worker tiếp tục. Chọn **Thoát hoàn toàn** trong menu tray
  mới kết thúc app và cả cây process con; transaction SQLite, file `.part`, atomic replace và recovery
  bảo vệ dữ liệu đã commit.
- Không chèn im lặng để che đoạn TTS bị lỗi.
- Mức âm lượng được cân bằng theo từng segment trước khi ghép chapter; chỉ các chỉ dẫn như thì thầm,
  quát hoặc cao trào mới chủ động lệch khỏi mức chuẩn.
- Giới hạn sinh audio được tính theo độ dài và pace của từng segment để một câu rất ngắn không chạy tới
  trần toàn cục của model. Sai lệch tốc độ nhẹ được ghi warning và chuyển qua Whisper; chỉ sai lệch cực đoan mới retry.
- Vocal-effect và từ tượng thanh có giới hạn thời lượng riêng, không bị đánh giá bằng số ký tự/giây và không đưa qua Whisper.
- Whisper đọc và resample WAV ngay trong process, không bật FFmpeg console theo từng segment.
- Phản hồi JSON từ Ollama có giới hạn schema, token và thời gian theo batch. Trong lúc chờ, app ghi
  nhịp hoạt động mỗi phút; bấm **Dừng** sẽ đóng stream thay vì đợi hết timeout dài.
- Khi Ollama chưa chạy, E Book Reader tự mở `ollama serve` ở chế độ ẩn và tự dừng tiến trình đó sau khi
  phân tích/phân vai xong. Một Ollama đã chạy từ trước được coi là tiến trình bên ngoài và không bị tự ý kill.
- Nếu phải tự dừng vì SSD/RAM/GPU/driver hoặc lỗi nghiêm trọng, app checkpoint và gửi Windows notification.
- Resource Manager tự nhường CPU/GPU/RAM/SSD cho ứng dụng foreground, sau đó tự tăng tải lại khi máy rảnh.

## Đầu ra

Mỗi book được lưu thành một project riêng với database, log, audio trung gian và thư mục `output` chứa MP3 chapter,
playlist, `pronunciations.json`, metadata tùy chọn và report. Project đã hoàn tất chỉ xác minh MP3/checksum rồi thoát nhanh,
không cần khởi động Ollama, không băm lại toàn bộ WAV hoặc ghép lại full-book nếu artifact vẫn nguyên vẹn.

## Trạng thái alpha

Kiến trúc, recovery, resource policy và pipeline mock đã có test. Các model thực, Windows notification và hành vi CUDA/RTX 5060 vẫn cần smoke test trên máy đích với một chapter khoảng 2.000–5.000 từ trước khi chạy book rất lớn.

Tài liệu kỹ thuật và kết quả test nằm trong `_internal/docs/`.
