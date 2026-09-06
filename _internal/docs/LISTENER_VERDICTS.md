# Phán quyết của người nghe: đường đi và cái cửa sổ hẹp

Nghe là tài nguyên khan hiếm nhất của dự án này. Máy có thể chạy cả đêm; chủ sách chỉ ngồi
nghe được vài chục đoạn. Nên mỗi phán quyết đã cho phải sống qua được mọi bản kế tiếp — và
suốt alpha.44 → alpha.50 nó liên tục **không** sống được, theo sáu cách khác nhau. Năm cách
là code — sáu cái cổng, mỗi cái tìm ra bằng cách để một chương chết ở đó, và cái sau chỉ lộ
ra khi cái trước đã thông. Cách còn lại là
*thời điểm*, không phải code, và nó là lý do tồn tại của
`scripts/watch_listener_acceptances.py`.

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

## Sáu cửa mà một phán quyết phải đi qua

alpha.46 tới alpha.50 lần lượt tìm ra chúng, mỗi cửa bằng cách để một chương chết
ở đó:

1. **Cửa cảnh báo** (`_high_quality_blocking_segment_warnings`) — trừ đi mã đã được chấp
   nhận. Sửa ở alpha.46.
2. **Cửa bằng chứng** (`chapter_segments_have_current_audio_qa`) — bỏ qua đoạn đã được nghe,
   vì bản thu người ta nghe *là* bằng chứng, và là bằng chứng duy nhất tồn tại cho những
   đoạn ấy. Sửa ở alpha.46.
3. **Cửa ASR** (`mark_failed` sau các vòng sửa) — không đánh `failed` một đoạn người ta đã
   phán quyết trên đúng bản thu này. Sửa ở alpha.47, commit `1bcf1a5`.
4. **Cửa đếm status** (`chapter_is_publishable`) — thuần đếm, không biết gì về phán quyết.
   Không cần dạy nó, vì `accept_failed_segment_audio` đã sửa status ngay từ đầu nguồn.
5. **Cửa quét recovery** (`recovery.py::_segment_has_current_audio_qa`) — chạy ở **mỗi lần
   resume**, duyệt từng segment của cả quyển và đòi một `quality_check` đạt. Sửa ở alpha.48,
   commit `513ef1a`.

6. **Cửa tiền đề của pha cảm thụ** (`_verify_chapter_perceptual_audio`) — đòi một
   `segment_audio_v1` **đạt** trước khi chịu chấm. Tìm ra ở alpha.50, sửa ở nhánh
   `fix/perceptual-precondition`, dành cho alpha.51.

### Cửa thứ sáu: chỉ tới được vì năm cửa trước đã thông

alpha.50 chương 3 chết với một lỗi **chưa từng xuất hiện ở bản nào trước đó**:

```
Perceptual QA requires current ASR evidence for c00003_s0000029_6fca388a80c8
```

Chính chỗ "chưa từng xuất hiện" mới là điều đáng nói. Các bản trước đánh đoạn ấy `failed` và
run dừng ở một cửa xa hơn về trước; giờ nó giữ được `warning`, đi tiếp, và đâm vào một tiền
đề chưa ai dạy về bảng phán quyết. **Sửa xong năm cửa thì cửa thứ sáu mới lộ ra** — đó là
hình dạng bình thường của loại lỗi này, nên đừng cho rằng cửa thứ sáu là cửa cuối.

Nó không phải một cú vấp rồi đi tiếp: không chấm thì đoạn ấy **không có bằng chứng cảm thụ
nào**, và cửa 2 sau đó cũng từ chối chương. Ba trên mười chương của alpha.50 có một đoạn như
vậy (3, 7, 10).

**Và cái giá lớn hơn thế nhiều.** `_verify_chapter_perceptual_audio` raise **giữa vòng lặp**,
nên vòng sửa cảm thụ chạy ngay sau nó không bao giờ được chạy. Đối chiếu cùng chương 3:

| | candidate cảm thụ đã dựng | đoạn còn cảnh báo |
|---|---|---|
| alpha.48 | **13** | 2 |
| alpha.50 | **0** | 5 |

alpha.48 tự cắt lại 11 trên 13 đoạn bị cờ; alpha.50 không cắt lại đoạn nào, vì cửa thứ sáu
bật lên ở đoạn 29 và mọi thứ phía sau chết theo. Nên **ba đoạn "cần tai người" thừa ra ở
chương 3 của alpha.50 là thiệt hại dây chuyền, không phải yêu cầu thật** — sau bản sửa thì
vòng sửa chạy lại và chúng sẽ tự biến mất, đúng như ở alpha.48.

Bài học kèm theo: khi một cổng raise giữa vòng lặp kiểm, đừng chỉ đếm đoạn nó chặn — hãy hỏi
**cái gì lẽ ra chạy sau nó**.

**alpha.50 không bị dừng vì việc này.** Sửa `pipeline.py` là đổi vân tay, tức mất 64 phút
phân tích đã xong để đổi lấy ba chương. Để nó ra bảy chương còn lại, rồi nhập bản sửa ở
alpha.51.

Cửa 2 kiểm tra status **trước** khi hỏi tới phán quyết, nên với một đoạn `failed` nó từ chối
mà không bao giờ đọc tới bảng chấp nhận. Điều đó không sai: một dòng `failed` thì đúng là
không phải bằng chứng. Nó chỉ có nghĩa là **status phải được sửa ở nguồn**, và cửa 4 tồn tại
để bắt đúng trường hợp đó.

### Cửa thứ năm: một lần resume gỡ ngược hai chương đã xuất

alpha.48 xuất chương 7 và 9. Một tiếng sau, `resume` requeue đúng những bản thu đã có phán
quyết — *"Recovery requires ASR and perceptual QA under the current locked quality policy"* —
và cả hai chương quay về `warning: MP3 must be rebuilt`.

**Chưa mất phán quyết nào lần đó**: requeue chỉ chạy lại ASR trên cùng bản thu, không cắt
lại, và cả 7 acceptance vẫn khớp checksum sau khi dừng run. Nhưng vòng sửa chạy *sau* một
lần ASR trượt thì **có** cắt lại, và bản cắt lại làm phán quyết mất hiệu lực vĩnh viễn. Lần
resume kế tiếp sẽ tiêu công nghe của chủ sách chứ không phải một chương.

Kiểm trên chính dữ liệu alpha.48, cả 7 bản thu có phán quyết:

| | trước bản sửa | sau bản sửa |
|---|---|---|
| 7/7 bản thu | **requeue** | giữ nguyên |

Cách đo lại: `scratchpad/verify_recovery_fix.py` (chạy trên **bản sao** database — dựng
`ProjectDB` là có ghi, đừng trỏ vào project thật).

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
python scripts/watch_listener_acceptances.py <project nguồn> <project đích> --interval 15
```

Nhịp 15 giây chứ không phải 45: đo trên alpha.48, ba lần bắt kịp cách cổng lần lượt 44, 66
và 59 giây, nên ở 45 giây thì hai trong ba lần là may rủi.

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
