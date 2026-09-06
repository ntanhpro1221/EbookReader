# Phán quyết của người nghe: đường đi và cái cửa sổ hẹp

Nghe là tài nguyên khan hiếm nhất của dự án này. Máy có thể chạy cả đêm; chủ sách chỉ ngồi
nghe được vài chục đoạn. Nên mỗi phán quyết đã cho phải sống qua được mọi bản kế tiếp — và
suốt alpha.44 → alpha.48 nó liên tục **không** sống được, theo bốn cách khác nhau. Ba cách
đầu đã sửa. Cách thứ tư là một vấn đề về *thời điểm*, không phải về code, và nó là lý do
tồn tại của `scripts/watch_listener_acceptances.py`.

## Một phán quyết là gì

Khoá theo `(segment_stable_id, wav_sha256, warning_code)`. Người ta chấp nhận **một bản
thu**, không phải một dòng trong bảng. Cắt lại đoạn ấy là phán quyết hết hiệu lực — đúng
như vậy, vì bản thu mới chưa ai nghe. Toàn bộ tính an toàn của việc mang phán quyết sang bản
khác nằm ở đây: chỉ mang được sang audio giống **từng byte**.

Có hai hàm ghi, và sự khác nhau giữa chúng đã từng giữ một chương lại:

| hàm | dùng khi | làm gì |
|---|---|---|
| `accept_segment_audio` | dòng đang `warning` | ghi phán quyết |
| `accept_failed_segment_audio` | dòng đang `failed` | ghi phán quyết **và** đưa status về `warning` |

Chương chỉ xuất khi mọi đoạn thuộc `{verified, warning}` và không đoạn nào `failed`. Nên với
một đoạn đã `failed`, chỉ ghi phán quyết là chưa đủ: status phải chuyển. Nó chuyển sang
`warning` chứ không phải `verified` — mã cảnh báo vẫn nằm trên dòng và báo cáo vẫn hiện nó,
vì chuyện đã xảy ra là *một người phủ quyết máy*, không phải máy đổi ý.

## Bốn cửa mà một phán quyết phải đi qua

alpha.46 và alpha.47 lần lượt tìm ra ba cửa đầu, mỗi cửa bằng cách để một chương chết ở đó:

1. **Cửa cảnh báo** (`_high_quality_blocking_segment_warnings`) — trừ đi mã đã được chấp
   nhận. Sửa ở alpha.46.
2. **Cửa bằng chứng** (`chapter_segments_have_current_audio_qa`) — bỏ qua đoạn đã được nghe,
   vì bản thu người ta nghe *là* bằng chứng, và là bằng chứng duy nhất tồn tại cho những
   đoạn ấy. Sửa ở alpha.46.
3. **Cửa ASR** (`mark_failed` sau các vòng sửa) — không đánh `failed` một đoạn người ta đã
   phán quyết trên đúng bản thu này. Sửa ở alpha.47, commit `1bcf1a5`.
4. **Cửa đếm status** (`chapter_is_publishable`) — thuần đếm, không biết gì về phán quyết.
   Không cần dạy nó, vì `accept_failed_segment_audio` đã sửa status ngay từ đầu nguồn.

Cửa 2 kiểm tra status **trước** khi hỏi tới phán quyết, nên với một đoạn `failed` nó từ chối
mà không bao giờ đọc tới bảng chấp nhận. Điều đó không sai: một dòng `failed` thì đúng là
không phải bằng chứng. Nó chỉ có nghĩa là **status phải được sửa ở nguồn**, và cửa 4 tồn tại
để bắt đúng trường hợp đó.

## Cửa sổ hẹp — cái mà alpha.48 tìm ra

Ba bản sửa trên đều đúng, và chương 3 của alpha.48 vẫn chết. Không có gì hỏng cả:

- phán quyết cho `c00003_s0000029` đã có từ 2026-09-04;
- audio alpha.48 dựng ra **giống từng byte** bản đã nghe;
- `port_listener_acceptances.py` chỉ mang được phán quyết sang **sau khi audio tồn tại**;
- nhưng chương bị chấm **ngay khi audio tồn tại**.

Cửa sổ giữa hai mốc đó là chỗ phán quyết bị rơi. Port chạy sau đó sửa được dòng — status về
`warning`, ba cửa thông — nhưng **chỉ một lần `resume` mới xuất được chương**. Với alpha.48
còn bốn chương nữa đang có phán quyết chờ (5, 7, 9, 10), đó là bốn lần chết-rồi-resume.

Cửa sổ ấy đủ rộng để chen vào. Một chương dựng **toàn bộ** đoạn của nó trước, rồi nhả TTS,
rồi mới nạp Whisper chấm cả chương một lượt. Bất cứ phán quyết nào rơi vào giữa đều được
người chấm nhìn thấy: cửa 3 giữ đoạn khỏi `mark_failed`, cửa 1 bỏ mã cảnh báo, và chương
xuất ngay lần đầu.

```
python scripts/watch_listener_acceptances.py <project nguồn> <project đích> --interval 45
```

Nó ghi vào một database đang có tiến trình khác dùng, nên nó làm ít nhất có thể: mỗi vòng là
một phép so **chỉ đọc**, và `ProjectDB` chỉ được dựng — tức chỉ mở transaction ghi — trong
những vòng thực sự có phán quyết vừa dùng được. Trên một run mười chương, đó là vài lần chứ
không phải hàng trăm. Nó tự thoát khi run kết thúc.

## Thứ tự chạy, cho người sau

- Chạy `watch_listener_acceptances.py` **song song với run**, ngay từ lúc khởi động.
- Chạy `port_listener_acceptances.py` thêm một lần **sau mỗi `resume`** và một lần khi run
  xong. Watcher lo cửa sổ trong lúc chạy; port lo phần còn lại.
- Một phán quyết bị từ chối vì "bản mới chưa thu segment này" **không phải lỗi** — chương đó
  chưa tới lượt. Chạy lại sau. Với alpha.46 cùng một lệnh mang 3 phán quyết lúc này và 5
  một tiếng sau, thuần tuý vì có thêm audio.
- Một phán quyết bị từ chối vì "bản thu đã khác" **là hàng rào an toàn đang làm việc**. Đừng
  tìm cách vòng qua nó; đưa đoạn ấy vào trang nghe lại.
