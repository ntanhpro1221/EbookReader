# Giao diện: Nghe (máy tính + Android) và Studio (máy tính)

Ngày 26-09 chủ sách yêu cầu làm lại UI/UX thành một sản phẩm: *"không chỉ đẹp về mặt giao diện mà luồng dùng,
cách dùng của app cũng phải ngon, phải trực quan"*, rồi thêm một trình nghe Android, rồi tách phần sản xuất và
phần tiêu thụ *"để phần tiêu thụ sẽ có sự đồng nhất với bản trên android"*. Tài liệu này là kiến trúc kết quả.

## Hai khu, một mã Nghe

| khu | ở đâu | làm gì |
|---|---|---|
| **Nghe** | máy tính **và** Android, cùng một mã React (`ui/src/listen`) | thư viện, trang sách, trình phát, đọc theo, dấu trang, nhân vật |
| **Studio** | chỉ máy tính (`ui/src/studio`) | dự án, trình tạo 4 bước, tiến trình sản xuất, nhật ký |

Phía Nghe không biết dữ liệu đến từ đâu: nó nói chuyện với `ListenSource` (`ui/src/listen/source.tsx`) và phát
bằng `AudioEngine` (`ui/src/listen/engine.ts`).

| | máy tính | Android |
|---|---|---|
| `ListenSource` | HTTP tới server cục bộ (`desktop/httpSource.ts`) | sách đã tải trên máy (`android/androidSource.ts`) |
| `AudioEngine` | `<audio>` của trình duyệt | lõi Media3 native (`android/nativeEngine.ts` -> `Playback.kt`) |

Hợp đồng dữ liệu chung là `book.json` (`ebook_reader/webui/listen_view.py`): tên, người đọc, các chương nghe
được kèm thời lượng, trạng thái nghe. Máy tính dựng nó từ project đang sản xuất (chương nào xong là nghe được
chương đó); điện thoại tải nó về cùng các file.

## Những gì người dùng có (26-09)

Nghe (máy tính + Android):
- Thư viện gom các tập cùng bộ, thẻ "Đang nghe dở" nói chương + giờ + lần nghe cuối, thẻ "Tối qua" buổi sáng, sách
  đang làm mà chưa có chương nào hiện dạng "Đang làm · chương đầu sau khoảng X"; tìm không dấu.
- Trình phát: hẹn giờ ngủ chỉ đếm khi đang phát, nhỏ dần theo dB, nghe thêm bằng phím/chuột (máy tính) hoặc lắc máy
  (điện thoại); lịch đêm tự hẹn giờ; lưới an toàn: phát liên tục N giờ không ai chạm máy thì tự dừng và ghi nhật ký
  đêm; tự lùi theo độ dài lần dừng (0/10/30 giây); "Quay lại chỗ vừa nghe" sau cú nhảy xa; hỏi khi thiết bị khác đã
  nghe xa hơn; tiến độ cả cuốn; nghe xong một tập thì mời tập kế.
- Chế độ đọc (`/book/:id/read/:chapterId`): đọc cả chương chưa thu âm, nhớ chỗ đọc, "Nghe từ đây" đúng câu.
- Dấu trang kèm câu văn, gộp dấu trùng, hoàn tác khi xoá; phím Space/←/→/Shift/B/M/[ ]/Esc.

Studio (máy tính):
- Trình tạo 4 bước: bước nằm trong URL, nháp giữ khi rời trang, gợi ý thư mục con, ước lượng thời gian đo trên máy
  này, cảnh báo đừng ngắt pha phân tích.
- Hàng đợi sản xuất: cuốn thứ hai xếp hàng, tự chạy khi cuốn kia xong.
- "Cần nghe lại" (`webui/reviews.py`): câu hỏng / chưa kiểm được / tên riêng lệch nhiều, nghe từng câu, bấm Ổn hoặc
  Cần thu lại; phán quyết ở `reviews.json` (không ghi vào SQLite của sách).
- "Xuất MP3 để nghe ở app khác" (`webui/export.py`): chép luồng âm thanh kèm tag ID3 đúng + bìa + `.m3u8`.
- Cài đặt: điện thoại (ghép bằng mã 6 số, huỷ mã sau 5 lần sai), hẹn giờ ngủ, lịch đêm, lưới an toàn.

## Máy tính: web trong Qt WebEngine

- Cửa sổ: `ebook_reader/desktop.py` - `QWebEngineView` (PySide6 đã có sẵn, **không thêm gói Python**: đổi
  `pyproject.toml`/`uv.lock` là đổi hash chất lượng của dây chuyền giữa cuốn sách).
- Server: `ebook_reader/webui/server.py`, stdlib `ThreadingHTTPServer`, chỉ nghe `127.0.0.1`, mọi `/api` và
  `/media` cần mã phiên, `Host` phải là chính server (chặn DNS rebinding).
- Dữ liệu sách: `webui/store.py` chỉ đọc (`mode=ro` + `query_only`), không dùng `_ReadOnlyProjectDB` của CLI vì
  nó chép cả file DB (136 MB/lô) mỗi lần mở.
- Chạy sách: `background_runner` như CLI - đóng cửa sổ không dừng sách.
- GPU của trang bị tắt (`--disable-gpu`): phân tích cần ~6,2 GB trên card 8 GB (xem THROUGHPUT.md, mục Unity).
- Tên chương lấy từ dòng tiêu đề trong văn bản, không từ tên file: nguồn cuốn 2 đánh số file lệch một.
- Đọc theo: mốc từng câu dựng từ `wav_duration + break_ms` (lệch 0,14 s trên 13 phút), co giãn theo độ dài MP3.

## Android: `mobile/`

Capacitor bọc giao diện Nghe; mọi thứ phải chạy khi tắt màn hình nằm ở native (WebView bị treo lúc đó):

- `Playback.kt` + `PlaybackService.kt` (Media3 1.11.1): cả cuốn là một hàng đợi, lưu vị trí mỗi 5 giây, tự lùi
  khi nghe lại, thông báo + màn hình khoá (lùi 15 / tới 15 / dấu trang / +10 phút khi đang hẹn giờ), nút tai
  nghe, dừng khi rút tai nghe, tiếp tục phát sau khi khởi động lại máy.
- `SleepTimer.kt`: phút hoặc hết chương, nhỏ dần 30 giây, **lắc máy để nghe thêm** (và để phát tiếp trong 2 phút
  sau khi đã tự dừng), rung xác nhận.
- `Bedtime.kt`: nhật ký đêm cho thẻ **"Tối qua bạn nghe tới đâu?"** (`android/MorningRecap.tsx`): lúc hẹn giờ,
  lần cuối chạm/lắc máy, lúc điện thoại bắt đầu nằm yên (cảm biến), lúc tự dừng - mỗi mốc kèm câu văn đang đọc.
- `PlayerWidget.kt`: widget trình phát thu nhỏ (nhỏ: bìa + phát; lớn: chương, tiến độ, lùi/phát/tới, hẹn giờ).
- `LibraryPlugin.kt` + `webui/sync.py`: tìm máy tính bằng UDP broadcast, ghép nối bằng mã 6 số một lần, tải gói
  sách (tải tiếp được), đồng bộ trạng thái nghe hai chiều (mới-hơn-thắng, dấu trang xoá có tombstone).

## Phát triển

```text
# server giao diện trên thư viện sandbox, bộ chạy giả (bấm Bắt đầu không khởi động worker thật)
runtime/.venv/Scripts/python.exe -m ebook_reader.webui --dev --port 8765 --library <thư mục> --preferences <file>
# giao diện có hot reload (proxy /api, /media sang 8765)
node ui/node_modules/vite/bin/vite.js ui
# kiểm thử tự động không phát tiếng ra loa: thêm ?mute=1
http://localhost:5173/?mute=1#/

# bản build nhúng vào app máy tính (ra ebook_reader/webui/static - không đặt tên dist/, .gitignore bỏ qua nó)
npm --prefix ui run build
# app Android
npm --prefix ui run build:android && cd mobile && npx cap sync android && cd android && gradlew assembleDebug
```

Dev server đồng bộ chỉ nghe `127.0.0.1` khi có `--sync-host 127.0.0.1`: máy ảo Android gọi tới qua `10.0.2.2`
mà Windows không hỏi tường lửa. Chế độ thật (`0.0.0.0`) chỉ mở khi người dùng bật trong Cài đặt.

**Không build Gradle, không chạy máy ảo trong pha phân tích của một lô** (AGENTS.md: đừng chạy việc nặng khi
phân tích). Việc nhẹ - sửa mã, hot reload, xem trong trình duyệt - thì được.
