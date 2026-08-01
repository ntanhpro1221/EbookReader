# E Book Reader v0.2 alpha.8

Ứng dụng Windows chạy local, chuyển một hoặc nhiều chapter `.txt` tiếng Việt thành audiobook MP3 có phân vai và cảm xúc.

## Bắt đầu

1. Giải nén toàn bộ ZIP vào SSD còn đủ dung lượng.
2. Double-click **`START.bat`**.
3. Lần đầu, file này tự cài môi trường và tải model; những lần sau mở ứng dụng trực tiếp.
4. Trong ứng dụng, chọn nhiều file TXT hoặc chọn một folder chứa các chapter TXT.

Không cần mở PowerShell, không cần chạy file setup riêng.

## Những gì nằm ở thư mục gốc

```text
e_book_reader/
├── START.bat     # file duy nhất người dùng cần mở
├── README.md     # hướng dẫn sử dụng
└── _internal/    # source, setup, test, model cache và tài liệu kỹ thuật
```

Người dùng bình thường không cần mở `_internal`. Tài liệu dành cho agent/lập trình viên cũng được giữ bên trong thư mục này.

## Cách xử lý một book

- Tool natural-sort các chapter theo tên file.
- Phân tích toàn book trước để xây character registry, bí danh, cách phát âm và voice casting thống nhất.
- Sau khi khóa settings/giọng, tool tạo và kiểm tra audio theo từng chapter.
- Chapter hoàn tất được xuất MP3 ngay; cuối cùng tạo playlist và MP3 toàn book.
- Trong lúc chạy, tool không dừng để hỏi lựa chọn. Trường hợp mơ hồ được xử lý theo policy và ghi vào report.

## An toàn và phục hồi

- WAV/MP3 ghi qua file `.part`, kiểm tra rồi mới atomic rename.
- SQLite là nguồn trạng thái chính; không coi file tồn tại là đã hoàn tất.
- Mỗi project chỉ cho phép một worker; settings trong SQLite, source hash và runtime/model fingerprint được kiểm tra lại khi resume.
- Có thể đóng hoặc kill app bất kỳ lúc nào; phần đang dở được tạo lại, phần đã commit được giữ.
- Không chèn im lặng để che đoạn TTS bị lỗi.
- Nếu phải tự dừng vì SSD/RAM/GPU/driver hoặc lỗi nghiêm trọng, app checkpoint và gửi Windows notification.
- Resource Manager tự nhường CPU/GPU/RAM/SSD cho ứng dụng foreground, sau đó tự tăng tải lại khi máy rảnh.

## Đầu ra

Mỗi book được lưu thành một project riêng với database, log, audio trung gian và thư mục `output` chứa MP3 chapter, playlist, metadata và report.

## Trạng thái alpha

Kiến trúc, recovery, resource policy và pipeline mock đã có test. Các model thực, Windows notification và hành vi CUDA/RTX 5060 vẫn cần smoke test trên máy đích với một chapter khoảng 2.000–5.000 từ trước khi chạy book rất lớn.

Tài liệu kỹ thuật và kết quả test nằm trong `_internal/docs/`.
