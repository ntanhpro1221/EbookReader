# Vì sao một bản thu tốt bị vứt đi

> **Tiêu đề này sai, và tôi giữ nó lại làm bằng chứng.** Bản đầu của tài liệu này (2026-09-07
> 23:58) kết luận rằng phép kiểm `generation_endpoint_active` bắt nhầm *ngữ điệu chưa hạ giọng*
> thay vì bắt bản thu bị cắt, và tôi đã viết sẵn bản vá nới lỏng nó. **Bản vá đó sai và đã bị
> rút.** Chuyện thật ở dưới, cùng với chỗ tôi trượt chân — vì cách trượt đáng ghi lại hơn cả
> kết luận.

Đo 2026-09-07, trên 956 bản thu bị loại (`dual_failed`) gộp từ alpha.50–55.

## Hiện tượng: một chương bị chặn bởi hai chữ

alpha.55 có 4 chương không xuất được MP3 — cả bốn **đã có file audio**, đều bị chặn ở
`chapter_post_encode_v1` bởi `SEGMENT_QA_REVIEW_REQUIRED`. Chương 016 bị chặn bởi:

```
"Rồi, rồi,"      1,92 giây      ASR_MISMATCH_UNRESOLVED      similarity 0,43
```

Lịch sử thu lại của nó nói khác hẳn cái nhãn:

| vòng | beam | greedy | lý do loại |
|---|---|---|---|
| 0 | 0,43 | **1,00** | `beam=ASR_MISMATCH; greedy=ASR_REPEATED_SHORT_PASS; blocking_signal=generation_endpoint_active` |
| 1 | 0,43 | 0,43 | `beam=ASR_MISMATCH; greedy=ASR_MISMATCH; blocking_signal=…` |
| 2 | **1,00** | 0,83 | `beam=ASR_REPEATED_SHORT_PASS; greedy=…; blocking_signal=…` |
| **3** | **1,00** | **1,00** | **`beam=ok; greedy=ok; blocking_signal=generation_endpoint_active`** |
| **4** | **1,00** | **1,00** | **`beam=ok; greedy=ok; blocking_signal=generation_endpoint_active`** |

Hai bản thu mà cả hai bộ giải mã chép đúng hoàn toàn, WER 0, đều bị vứt. Máy giữ bản 0,43 và
chặn cả chương bằng nhãn `ASR_MISMATCH_UNRESOLVED` — **một cái nhãn mà hồ sơ của chính nó bác
bỏ**.

## Chỗ tôi trượt chân

Tôi đo tương quan giữa việc `generation_endpoint_active` bật và ký tự cuối của câu:

| kết thúc bằng | bị chặn | trên tổng |
|---|---|---|
| `.` | **0** | 662 |
| `!` | **0** | 202 |
| chữ cái | **0** | 35 |
| `,` | **10** | 37 |
| `?` | **4** | 20 |

Tương quan tuyệt đối, và tôi kết luận ngay: *nó bắt ngữ điệu chưa hạ giọng, mà dấu phẩy và dấu
hỏi thì đúng phải thế.* Tôi viết bản vá, viết tài liệu, và báo cho chủ sách.

**Tôi chưa loại biến gây nhiễu.** Một test có sẵn tên là
`test_active_ceiling_endpoint_repairs_are_finite_and_remain_blocking` đỏ lên — có người đã cố ý
ghim đúng hành vi tôi vừa đổi. Đọc nó thì thấy nó dựng ca kèm `generation_ceiling_hit = 1.0`.

Đo lại với biến ấy:

- **Cả 14 ca endpoint bật đều có `generation_ceiling_hit = True`.** Phép thu hẹp tôi định làm
  sẽ không đổi một ca nào.
- Trong cả kho chỉ có **22 bản thu chạm trần khung, và tất cả đều kết thúc bằng `,` hoặc `?`**.

Tương quan với dấu câu là thật, nhưng nó nằm ở **chạm trần khung**, không nằm ở endpoint.

## Chuyện thật

Chuỗi nhân quả đi ngược với những gì tôi viết:

```
câu không hạ giọng  →  mô hình không phát token kết thúc  →  sinh cho tới khi CHẠM TRẦN KHUNG
                    →  bản thu bị cắt thật  →  còn to ở cuối  →  endpoint bật ĐÚNG
```

Bằng chứng dứt điểm — năm bản thu của `"Rồi, rồi,"`:

| vòng | thời lượng | trailing_rms | sàn |
|---|---|---|---|
| 0 | **0,96s** | 0,065 | −51 dBFS ≈ 0,003 |
| 1 | **0,96s** | 0,095 | |
| 2 | **0,96s** | 0,073 | |
| 3 | **0,96s** | 0,095 | |
| 4 | **0,96s** | 0,117 | |

**Cả năm dài đúng 0,96 giây** — bằng trần khung 12. Không phải trùng hợp: mọi vòng bị chặt tại
cùng một chỗ, khi tiếng còn to gấp 20–40 lần sàn. Bản thu **bị cắt thật**, và
`generation_endpoint_active` làm đúng việc của nó.

ASR chép ra đủ chữ chỉ có nghĩa là *các chữ* lọt vào trong 0,96 giây — không có nghĩa là đuôi
không bị chặt.

## Lỗi thật nằm ở đâu

`short_utterance_repair_frame_cap()` trả về hằng số: 12 khung cho đoạn ngắn, 6 cho đoạn cực
ngắn, **chỉ căn theo số ký tự**. Nó không biết vòng trước đã bị cắt.

Nên **năm vòng thu lại đều dùng đúng một trần khung và cho ra năm bản cắt y hệt nhau.** Vòng
sửa không thể sửa được một lỗi do trần khung gây ra, vì nó không bao giờ đổi trần khung — nó
chỉ đổi seed. Đây mới là chỗ hỏng, và nó cũng giải thích vì sao chương bị chặn *vĩnh viễn*
chứ không phải *thỉnh thoảng*.

Và có một chi tiết làm chuyện tệ hơn: **bản thu gốc dài 1,92 giây, còn năm bản sửa lại đều
0,96 giây.** Vòng sửa không chỉ không nới trần — nó *siết xuống một nửa*. `_checkpoint_short_
ceiling_repair` đặt `generation_frame_cap = 12` ngay khi segment mang nhãn
`TTS_GENERATION_CEILING_REACHED`, nên mỗi vòng sửa lại cho ra bản ngắn hơn bản nó định thay.

### Hướng sửa: chưa chốt, và tôi không giả vờ là đã chốt

Ý định của trần khung là **chặn mô hình lảm nhảm vô tận** trên đầu vào hai chữ — một rủi ro
thật, `TTS_GENERATION_CEILING_REACHED` sinh ra vì nó. Nên "nới trần" không hiển nhiên đúng: có
thể ở 0,96 giây mô hình vẫn còn to *vì nó đang sắp lảm nhảm*, và cắt là đúng.

Hai giả thuyết, phân biệt được bằng một phép thử rẻ nhưng **cần GPU**:

1. **Câu cần dài hơn 12 khung.** Sinh lại `"Rồi, rồi,"` với trần 16, 20, 24 và nghe/đo xem nó
   có kết thúc tự nhiên không. Nếu có, trần phải căn theo độ dài lời chứ không phải hằng số.
2. **Mô hình không chịu dừng trên câu không hạ giọng.** Nếu nới tới 24 khung mà nó vẫn còn to
   ở cuối, thì trần đang che một lỗi khác, và sửa đúng là ở chỗ đưa văn bản cho TTS — ví dụ
   thêm một dấu kết thúc cho bản đọc mà không thêm vào bản hiển thị.

Chưa đo thì chưa biết, và đoán bừa ở đây chính là cách tôi đã sai một lần trong tài liệu này.

## Bài học

Ba lỗi tối nay cùng một hình dạng — phép kiểm dựng cho tình huống A, gặp tình huống B trông
giống A, không ai bảo nó cách phân biệt:

| phép kiểm | định bắt | thực tế bắt |
|---|---|---|
| neo tên (`asr_only_failure`) | tên bị đọc sai | mọi đoạn chỉ gồm một tên ngắn |
| `is_vocalization_only` | tiếng cười, tiếng thốt | tiếng cười — trừ khi viết là `Ahaha` |
| trần khung (`generation_frame_cap`) | mô hình lảm nhảm vô tận | câu không hạ giọng |

Còn một bài học thứ tư, đắt hơn ba cái kia: **tôi đã có một tương quan tuyệt đối — 0/899 so với
14/57 — và nó vẫn dẫn tôi tới kết luận sai.** Tương quan đúng, mũi tên nhân quả ngược. Thứ cứu
được là một test mà người trước đã viết, đặt tên thẳng vào cái tôi định phá: *remain blocking*.

Nếu một test đỏ lên đúng chỗ ta vừa đổi, và tên nó mô tả chính hành vi ta vừa bỏ, thì mặc định
là **ta sai**, cho tới khi đọc xong nó và chứng minh được ngược lại.

Xem thêm [LOCKED_NAME_ANCHOR_IS_A_SPELLING_TEST.md](LOCKED_NAME_ANCHOR_IS_A_SPELLING_TEST.md).
