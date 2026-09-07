# Xuất bản khi không có ai để hỏi

Chủ sách ra lệnh 2026-09-07: *"tôi không muốn phải tự nghe, project phải hoạt động toàn bộ cho
ra sản phẩm"*.

Tài liệu này ghi thiết kế cho nửa còn lại của lệnh ấy — **chưa cài**, và ghi lại cả những
hướng đã loại cùng lý do.

## Hiện trạng: chương bị chặn ở đâu, và chỉ ở đó

Đo trên alpha.55 (chín chương mới, không phán quyết nào mang sang). Bốn chương không xuất được
MP3 — nhưng **cả bốn đều đã có file audio**. Chúng dừng ở đúng một chỗ:

```
chapter_post_encode_v1  →  SEGMENT_QA_REVIEW_REQUIRED
```

sinh ra bởi `_high_quality_blocking_segment_warnings()`, và chỉ bởi **hai mã**:

- `ASR_LOCKED_NAME_ANCHOR_MISMATCH`
- `ASR_MISMATCH_UNRESOLVED`

Năm mã cảnh báo khác **không** chặn: chúng nằm trong `HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS`,
với lý lẽ đã ghi ngay tại chỗ khai báo — *phép kiểm không có ý kiến thì không được chặn*.

Nói cách khác: **cơ chế cần thiết đã có sẵn và đã đúng.** Việc còn lại không phải dựng cái mới
mà là hỏi cho đủ: hai mã kia có luôn luôn mang thông tin không?

Ba trong sáu đoạn chặn của alpha.55 thì không, và ba bản vá đang chờ nhắm vào đúng chúng
(đoạn chỉ gồm một tên ngắn; tiếng cười viết là `Ahaha`). Còn lại là những đoạn ASR **thật sự
nhìn được** và **thật sự không khớp**.

## Hướng đã loại: thăng bản thu "ít tệ nhất"

Nhìn lịch sử thu lại thì thấy trong cả bốn ca, bản được giữ **không phải bản điểm cao nhất** máy
đã tạo ra. Cám dỗ hiển nhiên: hết ngân sách thì thăng bản tốt nhất trong đám.

**Không làm, vì đó là quyết định cố ý của người trước**, ghim bằng
`test_candidate_exhaustion_keeps_incumbent_and_uses_incumbent_evidence`. Và lý lẽ của nó đúng:
một bản thu đã trượt cổng không phải bằng chứng nó khá hơn — nó chỉ là một cách hỏng khác.
Thăng nó lên là để máy đưa vào sách một bản thu **không phép kiểm nào tán thành**, dựa trên
việc so hai con số mà cả hai đều dưới ngưỡng.

Đêm 2026-09-07 tôi đã một lần đè lên đúng loại quyết định như thế — xem
[WHY_A_GOOD_TAKE_GETS_THROWN_AWAY.md](WHY_A_GOOD_TAKE_GETS_THROWN_AWAY.md) — nên lần này
thiết kế **theo** nó.

## Hướng chọn: chấp nhận có nguồn gốc "máy", ghi rõ là máy

Bảng `listener_audio_acceptances` đã cho phép một chương xuất bản mang theo segment `failed`,
khoá theo `(segment_stable_id, wav_sha256, warning_code)`. Chương 013 và 014 của alpha.56 đi
qua đúng đường ấy, và **bản thu vẫn mang trạng thái `failed`** — máy không đổi ý điều gì, nó
chỉ được cho phép đi tiếp.

Thiết kế: một bản ghi **song song**, cùng khoá, khác nguồn gốc.

| | `listener_audio_acceptances` | (mới) chấp nhận của máy |
|---|---|---|
| ai quyết | người, đã nghe | máy, vì hết cách hỏi |
| khi nào | bất cứ lúc nào | **chỉ sau khi hết ngân sách thu lại** |
| bản thu | giữ nguyên bản đang giữ | giữ nguyên bản đang giữ |
| ghi vào báo cáo | không cần | **bắt buộc**, kèm điểm số và lời gốc |

Ba ràng buộc, và chúng là phần đáng giá nhất của thiết kế:

1. **Không bao giờ trộn hai nguồn gốc.** Phải luôn trả lời được "cái này có người nghe chưa?".
   Một bảng chung với cột `source` cũng được, miễn không có truy vấn nào quên lọc.
2. **Chỉ sau khi hết ngân sách.** Chấp nhận sớm là bỏ qua vòng sửa còn có thể cứu — mà đo được
   là vòng 2 trở đi cứu **106/641 segment (16,5%)**, xem
   [OPTIMISATION_QUEUE.md](OPTIMISATION_QUEUE.md).
3. **Không im lặng.** Mỗi chương xuất bản kiểu này phải mang con số "N đoạn chưa ai xác nhận"
   trong metadata, và một báo cáo liệt kê chúng kèm mốc thời gian trong file MP3 — để chủ sách
   nghe *nếu muốn*, chứ không có gì đứng chờ.

## Thứ tự làm, và vì sao không làm ngay

Tám bản vá đang chờ áp đã nhắm vào ba trong sáu ca chặn. **Áp chúng trước, chạy chương mới
(`019+`), rồi mới đo lại còn bao nhiêu ca thật sự cần tới cơ chế này.** Dựng nó ngay bây giờ là
định cỡ một cái van cho một dòng chảy sắp đổi.

Con số cần đo lại sau khi áp: alpha.55 chặn 4/9 chương bằng 6 đoạn. Nếu ba bản vá ăn đúng,
phần còn lại là 2–3 đoạn trên chín chương — và khi đó mới biết cơ chế này phải chịu tải bao
nhiêu trên 478 chương.
