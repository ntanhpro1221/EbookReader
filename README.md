# Ebook Reader

Ứng dụng Windows chạy local, chuyển một hoặc nhiều chapter `.txt` tiếng Việt thành audiobook MP3 có phân vai và cảm xúc.

## Bắt đầu

1. Giải nén toàn bộ ZIP vào SSD còn đủ dung lượng.
2. Double-click shortcut **`Ebook Reader`** ở thư mục gốc hoặc mở **Ebook Reader** từ Start Menu.
3. Lần đầu, file này tự cài môi trường và tải model; khi nâng cấp, setup tái sử dụng venv/model cache thay vì xóa runtime cũ.
4. Trong ứng dụng, chọn nhiều file TXT hoặc chọn một folder chứa các chapter TXT.

Khi muốn chuyển từ project đang mở sang đầu vào khác, bấm **Book mới**. Settings hiển thị của project cũ
được đồng bộ từ cấu hình đã khóa, nên thay đổi control trên màn hình không thể âm thầm đổi giọng khi resume.

Không cần tự mở PowerShell hoặc chạy file setup riêng. Launcher hiện một console ngay khi bắt đầu,
liên tục báo trạng thái trong lúc GUI đang nạp và tự đóng console ngay khi chính GUI báo đã hiển thị.
Nếu source mới chỉ thiếu dependency Python, launcher repair tăng dần mà không cài lại PyTorch/model.
Mọi phiên khởi động được ghi vào `_internal/runtime/logs/startup.log`; khi lỗi, console không tự đóng.
Nếu Ebook Reader đã chạy, lần mở tiếp theo chỉ đưa cửa sổ hiện có lên trước thay vì tạo instance thứ hai.

## Những gì nằm ở thư mục gốc

```text
Ebook Reader/
├── Ebook Reader.lnk  # shortcut ứng dụng có icon, trỏ thẳng tới _internal\Ebook Reader.vbs
├── README.md     # hướng dẫn sử dụng
└── _internal/    # chứa Ebook Reader.vbs, source, setup, test, model cache và tài liệu kỹ thuật
```

Người dùng bình thường không cần mở `_internal`. Tài liệu dành cho agent/lập trình viên cũng được giữ bên trong thư mục này.

## Cách xử lý một book

- Tool natural-sort các chapter theo tên file.
- Phân tích toàn book trước để xây character registry, bí danh, cách phát âm và voice casting thống nhất.
- Nếu stream Ollama kết thúc dở, app chia đôi batch hiện tại và tiếp tục với các batch nhỏ hơn thay vì
  lặp lại nguyên batch lớn ba lần. Ollama do app tự chạy ghi stdout/stderr vào
  `_internal/runtime/logs/ollama-server.log` để chẩn đoán runner/GPU khi có lỗi.
- Người dùng lọc preset người kể theo giới tính và miền ngay trong Thiết lập; dropdown chỉ hiện tên của
  toàn bộ giọng Bắc, Nam và Trung không thuộc kiểu tin tức. Label `Giọng kể chuyện` là header foldout
  với chevron nhỏ cùng style dropdown ở đầu; bên dưới có ba dòng con thụt vào khoảng chiều rộng bốn chữ `o`
  và có ba dòng con theo thứ tự: `Nghe thử`, `Giới tính`, `Miền`. Phạm Tuyên và Ngọc Linh
  đứng đầu danh sách. Hai dòng lọc giới tính/miền chỉ hiện khi giọng kể chuyện còn được chỉnh sửa;
  dòng nghe thử vẫn giữ lại khi thiết lập sách đã khóa.
- Chọn một preset trong dropdown sẽ tự phát WAV preview; nút `Nghe thử` cho phép nghe lại. App đóng gói
  sẵn preview cho cả 10 preset hợp lệ nên không nạp model TTS chỉ để nghe thử.
- Chất lượng và giọng người kể được lưu cùng sách và khóa sau khi sách bắt đầu. Chế độ tài nguyên
  và ngưỡng GPU là setting global, không tạo sách mới khi thay đổi và được worker nhận tại checkpoint kế tiếp.
  Bấm `Sách mới` đặt lại thiết lập sách về `Cân bằng`, mọi giới tính, mọi miền và giọng `Phạm Tuyên`,
  nhưng giữ nguyên hai thiết lập global này. Nút này chỉ bật khi đang mở một sách đã tồn tại; trong bản
  nháp sách mới chưa chạy, nút bị vô hiệu hóa vì không có sách cũ nào cần rời khỏi.
- Nhân vật có tên được ưu tiên giọng theo thứ tự Bắc → Nam, rồi tự nhiên → kể chuyện. Preset tin tức không được
  phân vai; giọng Trung chỉ tham gia pool NPC vô danh/cục bộ ngắn sau các giọng phổ thông để tăng đa dạng có kiểm soát.
- Nhân vật phụ có dấu hiệu cục bộ như “áo xanh”, “áo đỏ” được giữ thành hai vai riêng trong cuộc thoại;
  trường hợp thực sự không phân biệt được vẫn tách tối thiểu theo nam/nữ/chưa rõ.
- Mỗi nhân vật giữ nguyên một preset và một biến thể cao độ. Khoảng hạ giọng được giới hạn
  theo cao độ median đo từ preview: Phạm Tuyên không bị hạ, Xuân Vĩnh/Thái Sơn/Ngọc Trân chỉ hạ tối đa
  `-1`, các preset còn lại hạ tối đa `-2`; mọi preset chỉ nâng tối đa `+2` bán âm. Khi nhiều vai
  dùng chung preset, biến thể này tạo khác biệt vừa phải mà không đổi tốc độ; cảm xúc không đổi
  sang người đọc khác giữa chừng.
- Độc thoại nội tâm ưu tiên bắt buộc giọng đã khóa của nhân vật đang nghĩ; chỉ sau khi phân tích hết số
  lần thử mà vẫn không xác định được nhân vật thì mới fallback sang giọng người kể và ghi warning.
- Tên tiếng Anh được đối chiếu với CMU Pronouncing Dictionary đóng gói cục bộ; chuỗi âm vị tiếng Anh
  được Qwen chuyển thành âm tiết thuần Việt như `Michael → Mai-cồ`, `Gary → Ga-ri`. Tên fantasy không có
  trong từ điển vẫn được xét theo ngữ cảnh. Cách đọc được khóa trong SQLite theo sách, áp dụng đồng nhất
  cho mọi giọng, chapter, lần resume và câu đối chiếu ASR.
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
- Mức âm lượng được cân bằng theo K-weighted LUFS của từng segment trước khi ghép chapter;
  giọng kể chuyện có anchor nhỉnh hơn hội thoại trung tính, còn khoảng cách của `loud` được giữ nhỏ. Chỉ các
  chỉ dẫn như thì thầm, quát hoặc cao trào mới chủ động lệch khỏi mức chuẩn.
- Xử lý pitch dùng WORLD vocoder chuyên cho tiếng nói: tách F0, spectral envelope và aperiodicity,
  chỉ thay đường F0 rồi tổng hợp lại để giữ formant/chất giọng và nguyên thời lượng. Nếu đoạn
  phi ngôn ngữ không có đủ voiced frame hoặc bước pitch hiếm khi lỗi, app giữ waveform gốc và ghi warning
  thay vì tạo lại lời đọc hoặc làm hỏng chapter.
- Giới hạn sinh audio được tính theo độ dài và pace của từng segment để một câu rất ngắn không chạy tới
  trần toàn cục của model. Ngân sách frame VieNeu và giới hạn kiểm tra dùng chung một chính sách thời lượng,
  nên app không thể vừa cho model sinh dài hơn rồi tự từ chối chính kết quả đó. Sai lệch tốc độ nhẹ được ghi
  warning và chuyển qua Whisper; chỉ sai lệch cực đoan mới retry.
- Vocal-effect và từ tượng thanh có giới hạn thời lượng riêng, không bị đánh giá bằng số ký tự/giây và không đưa qua
  Whisper. Nếu runtime vẫn trả một hiệu ứng quá dài, app fade-out riêng hiệu ứng đó và ghi warning; lời kể,
  hội thoại và nội tâm không bao giờ bị cắt để lách kiểm tra.
- Whisper đọc và resample WAV ngay trong process, không bật FFmpeg console theo từng segment.
- Phản hồi JSON từ Ollama có giới hạn schema, token và thời gian theo batch. Trong lúc chờ, app ghi
  nhịp hoạt động mỗi phút; bấm **Dừng** sẽ đóng stream thay vì đợi hết timeout dài.
- Khi Ollama chưa chạy, Ebook Reader tự mở `ollama serve` ở chế độ ẩn và tự dừng tiến trình đó sau khi
  phân tích/phân vai xong. Một Ollama đã chạy từ trước được coi là tiến trình bên ngoài và không bị tự ý kill.
- Sau mỗi lần VieNeu tạo audio hoặc trả lỗi, app thu hồi cache inference. Nếu RAM tụt tới mức critical giữa hai
  segment, app unload model/cache rồi đo lại; chỉ tự dừng, giữ checkpoint và gửi Windows notification khi RAM
  vẫn không hồi phục. Critical SSD/GPU/driver và lỗi nghiêm trọng vẫn dừng ngay tại ranh giới an toàn.
- Resource Manager tự nhường CPU/GPU/RAM/SSD cho ứng dụng foreground, sau đó tự tăng tải lại khi máy rảnh.

## Đầu ra

Mỗi book được lưu thành một project riêng với database, log, audio trung gian và thư mục `output` chứa MP3 chapter,
playlist, `pronunciations.json`, metadata tùy chọn và report. Project đã hoàn tất chỉ xác minh MP3/checksum rồi thoát nhanh,
không cần khởi động Ollama, không băm lại toàn bộ WAV hoặc ghép lại full-book nếu artifact vẫn nguyên vẹn.

## Trạng thái alpha

Kiến trúc, recovery, resource policy và pipeline mock đã có test. Các model thực, Windows notification và hành vi CUDA/RTX 5060 vẫn cần smoke test trên máy đích với một chapter khoảng 2.000–5.000 từ trước khi chạy book rất lớn.

Tài liệu kỹ thuật và kết quả test nằm trong `_internal/docs/`.
