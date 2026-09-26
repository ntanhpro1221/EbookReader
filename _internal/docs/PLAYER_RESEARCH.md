# Học từ các trình nghe sách nói (26-09)

Chủ sách: *"càng học, càng tìm hiểu nhiều càng tốt"*, và hỏi riêng về các app có cả bản Windows lẫn Android. Đã dùng
thử trên máy ảo Android 16 (Play Store): **Smart AudioBook Player** (SABP, 5 triệu lượt tải, 4,8★), **Voice**
(mã nguồn mở, F-Droid). **AntennaPod** đã cài nhưng chưa thử (hạn mức token); phần của nó lấy từ tài liệu. Các app
đa nền tảng (Audible, Libby, Audiobookshelf, Spotify) tìm hiểu qua tài liệu chính thức.

## Tìm được gì

### Smart AudioBook Player - app nhiều tính năng nhất

- **Hẹn giờ ngủ**: mặc định 10 phút; mỗi lần lắc máy thì đặt lại từ đầu. Có **lịch tự bật** (tự bật/tắt theo giờ), độ
  nhạy lắc, "theo dõi chuyển động: luôn / chỉ lúc sắp tắt", báo khi bắt đầu nhỏ dần, rung khi được đặt lại.
- **Force stop sau 2 giờ phát liên tục** - lưới an toàn cho người ngủ quên mà không hẹn giờ.
- **Tự lùi theo độ dài lần dừng**, tối đa 30 giây ("Big"). Đây đúng là cách ta vừa làm (0 / 10 / 30 giây).
- Tự phát khi cắm tai nghe; tạm dừng khi có tin nhắn hoặc chỉ đường; tự phát lại sau cuộc gọi; dừng khi app khác phát.
- Dòng tiến độ **cả cuốn** ngay trên trình phát: "Đã nghe 15:00 / 45:00 · 33% · Còn 30:00".
- Trình phát có: danh sách nhân vật (người dùng tự nhập), dấu trang (nhấn giữ = thêm nhanh), tăng âm lượng, bộ cân bằng,
  lặp đoạn (học ngoại ngữ), **úp máy để dừng, lật lên để nghe tiếp**, khoá nút (bỏ túi), tua 10 giây và 1 phút.
- Nút tai nghe Bluetooth: Trước/Sau = lùi/tới 10 giây (không đổi chương).
- Hỗ trợ chương trong m4b/mp3, **phụ đề .srt** (đọc theo), bỏ đoạn đầu/cuối lặp lại, nén sang Opus để tiết kiệm chỗ.
- Thư viện: Tất cả / Mới / Đang nghe / Nghe xong (ta cũng vậy). Mỗi cuốn phải nằm trong một thư mục riêng.
- Mở app vài lần là hiện hộp thoại chấm sao của Play - khó chịu, ta không làm thế.

### Voice - tối giản, đẹp

- Lúc thêm sách hỏi **"file của bạn sắp xếp thế nào?"** (thư mục con là sách / một thư mục là một sách / tác giả rồi
  sách) và **xem trước ngay** kết quả: "sẽ nhận ra các sách sau: … 3 file âm thanh".
- Hẹn giờ ngủ dạng tấm trượt từ dưới lên, lời chào "Sweet dreams! 🌙": 5/15/30/60 phút, một số tuỳ chỉnh có nút
  "Ngắn hơn / Dài hơn", và "Hết chương".
- Bỏ khoảng lặng, tăng âm lượng. Thư viện chia "Chưa nghe / Đang nghe", có ô tìm ở đầu.
- **Voice đọc tên sách và tên chương từ tag ID3** - và MP3 của ta hiện ra thành sách "lo16", chương "645" (xem mục ⚠).

### AntennaPod (theo tài liệu)

Hẹn giờ ngủ: lắc để đặt lại, rung trước khi hết giờ, **tự bật trong khung giờ**, nút gia hạn nhanh.

### App có cả Windows và Android

- **Audible (Whispersync for Voice)**: vị trí đẩy lên mây mỗi lần dừng. Mở trên thiết bị khác thì **hỏi "tới vị trí xa
  nhất?"** thay vì lặng lẽ nhảy. Chuyển qua lại **đọc ebook ⇄ nghe** đúng chỗ (Kindle + Audible).
- **Libby**: ghép thiết bị bằng **mã cài đặt** (giống mã 6 số của ta). Vị trí, dấu trang, ghi chú đồng bộ. Thanh tiến độ
  cả cuốn hiện vạch chương và dấu trang. Có **Timeline** (lịch sử mượn/đọc), xuất ra được.
- **Audiobookshelf** (máy chủ tự dựng + web + Android, gần kiến trúc của ta nhất): tải về nghe offline, vị trí lưu trên
  máy và **gửi lên khi máy chủ liên lạc lại được**, ghi **phiên nghe** (thiết bị, bắt đầu/kết thúc, vị trí) và thống
  kê nghe. Người dùng than một lỗi: chuyển từ máy tính sang điện thoại thì điện thoại vẫn ở vị trí cũ tới khi thoát ra vào
  lại → **đồng bộ phải xảy ra lúc mở sách, không chỉ lúc mở app**.
- **Spotify Connect**: điều khiển thiết bị đang phát từ thiết bị khác, chuyển phát liền mạch giữa các thiết bị.

## ⚠ Lỗi của chính ta lộ ra khi nghe bằng app khác

MP3 chương mang tag ID3 của dây chuyền: **album = tên project lô ("lo16"), title = tên file nguồn ("645")**, không
tên sách, không tên chương thật ("Chương 646 - Trở về (1)"), không ảnh bìa, không số thứ tự. Ai chép MP3 sang điện
thoại hay mở bằng trình nghe khác sẽ thấy rác. Code ghi MP3 nằm trong file bị khoá (đang chạy sách) nên **không sửa ở
dây chuyền**; sửa ở khâu **xuất**: một lệnh "Xuất sách" ghi bản sao MP3 có tag đúng (album, title, artist = giọng kể,
track, ảnh bìa) hoặc gộp thành một file M4B có mốc chương.

## Áp dụng - theo thứ tự đáng làm

Đã làm ngay tối 26-09 (nhánh ui/redesign): #1 (máy tính + lõi Android), #2, #3 (máy tính), #4 (chế độ đọc),
#5, #6 (xuất MP3 có tag). Còn lại: #7 trở đi.

| # | Ý tưởng | Học từ | Vì sao với ta |
|---|---|---|---|
| 1 | **Tự dừng khi nghe liên tục quá lâu mà không chạm máy** (mặc định 2 giờ), ghi luôn mốc "tự dừng" vào nhật ký đêm | SABP | Ngủ quên KHÔNG hẹn giờ là trường hợp tệ nhất cho nỗi đau "sáng dậy tìm chỗ"; lưới này làm thẻ "Tối qua" chạy cả khi quên hẹn giờ |
| 2 | **Lịch tự bật hẹn giờ** (vd 22:00-06:00) | SABP, AntennaPod | Người nghe buồn ngủ hay quên bấm hẹn giờ |
| 3 | **Hỏi khi thiết bị kia nghe xa hơn**: "Trên điện thoại bạn đã nghe tới Chương 726 · 12:40 (23:41 tối qua) - Nghe tiếp từ đó?" | Audible, Audiobookshelf | Hiện ta lặng lẽ lấy bản mới hơn khi đồng bộ; hỏi thì không ai bị nhảy chỗ bất ngờ. Đồng bộ lúc mở sách |
| 4 | **Đọc ⇄ nghe cùng một chỗ**: chế độ đọc sách (không tiếng) đi theo đúng câu đang nghe, và ngược lại | Whispersync (Kindle + Audible) | Ta đã có văn bản kèm mốc từng câu - thứ Audible phải bán hai sản phẩm mới có. App tên "Ebook Reader" |
| 5 | **Tiến độ cả cuốn trên trình phát** ("Đã nghe 5 giờ 12 / 9 giờ · Còn 3 giờ 48 ở 1,5×") | SABP, Libby | Người nghe muốn biết còn bao lâu hết sách |
| 6 | **Xuất sách có tag đúng / M4B** | (lỗi phát hiện được) | Mục ⚠ |
| 7 | **Lịch sử nghe** theo ngày (phiên: giờ, thiết bị, từ đâu tới đâu) + thống kê | Audiobookshelf, Libby | Cũng là một cách tìm lại chỗ; nền cho thống kê |
| 8 | Lắc để **đặt lại** (thay vì cộng thêm) - để người dùng chọn | SABP | Hai thói quen khác nhau; ta đang cộng 10 phút |
| 9 | Úp máy để dừng / lật lên nghe tiếp; khoá nút khi bỏ túi | SABP | Điện thoại |
| 10 | Tấm hẹn giờ có số tuỳ chỉnh + "Ngắn hơn/Dài hơn"; báo rung khi bắt đầu nhỏ dần | Voice, SABP | Tinh chỉnh |
| 11 | Nút tai nghe Bluetooth Trước/Sau = lùi/tới (tuỳ chọn) | SABP | Sách nói ít khi cần nhảy chương |
| 12 | Điều khiển điện thoại đang phát từ máy tính | Spotify Connect | Làm sau cùng |

Không học: hộp thoại xin chấm sao, lặp đoạn (học ngoại ngữ), cân bằng âm (giọng đọc đã được cân mức ở dây chuyền).
