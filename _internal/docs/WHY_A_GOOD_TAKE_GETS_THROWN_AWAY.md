# Vì sao một bản thu tốt bị vứt đi

Đo 2026-09-07, trên 956 bản thu bị loại (`dual_failed`) gộp từ alpha.50–55.

## Chuyện bắt đầu từ một chương không xuất được

alpha.55 có 4 chương không xuất được MP3. Cả bốn đều **đã có file audio**; chúng bị chặn ở
`chapter_post_encode_v1` bởi mã `SEGMENT_QA_REVIEW_REQUIRED`. Một trong bốn là chương 016, bị
chặn bởi một đoạn hai chữ:

```
"Rồi, rồi,"      1,92 giây      ASR_MISMATCH_UNRESOLVED      similarity 0,43
```

Nhìn vào lịch sử thu lại của nó thì thấy chuyện khác hẳn cái nhãn:

| vòng | trạng thái | beam | greedy | lý do loại |
|---|---|---|---|---|
| 0 | dual_failed | 0,43 | **1,00** | `beam=ASR_MISMATCH; greedy=ASR_REPEATED_SHORT_PASS; blocking_signal=generation_endpoint_active` |
| 1 | dual_failed | 0,43 | 0,43 | `beam=ASR_MISMATCH; greedy=ASR_MISMATCH; blocking_signal=…` |
| 2 | dual_failed | **1,00** | 0,83 | `beam=ASR_REPEATED_SHORT_PASS; greedy=ASR_REPEATED_SHORT_PASS; blocking_signal=…` |
| **3** | dual_failed | **1,00** | **1,00** | **`beam=ok; greedy=ok; blocking_signal=generation_endpoint_active`** |
| **4** | dual_failed | **1,00** | **1,00** | **`beam=ok; greedy=ok; blocking_signal=generation_endpoint_active`** |

**Hai bản thu mà cả hai bộ giải mã chép đúng hoàn toàn, WER bằng 0, đều bị vứt.** Máy giữ lại
bản gốc 0,43, dán nhãn `ASR_MISMATCH_UNRESOLVED`, và chặn cả chương — bằng một lý do **không
phải là lý do thật**. Nhãn nói ASR không khớp; hồ sơ nói ASR khớp tuyệt đối.

## Thủ phạm đo nhầm thứ

`generation_endpoint_active` bật khi `trailing_rms` còn cao hơn ngưỡng ở cuối file
(`segment_endpoint_floor_dbfs: -51,0`). Ý định của nó: bắt bản thu **bị cắt giữa chừng**.

Nó không làm việc ấy. Nó bắt **ngữ điệu chưa hạ giọng**:

| văn bản kết thúc bằng | số lần bị chặn | trên tổng |
|---|---|---|
| `.` | **0** | 662 |
| `!` | **0** | 202 |
| chữ cái | **0** | 35 |
| `,` | **10** | 37 (27%) |
| `?` | **4** | 20 (20%) |

**Không một lần nào trên dấu chấm, dấu chấm than, hay chữ cái.** Cả 14 lần nó bật đều là câu
kết thúc bằng dấu phẩy hoặc dấu hỏi — mà dấu phẩy nghĩa là câu còn tiếp, dấu hỏi thì lên giọng
ở cuối. **Cả hai đều đúng phải còn năng lượng ở cuối.**

Trong 14 lần ấy, **2 lần cả hai bộ giải mã đều đã qua**.

## Vì sao bản vá là thu hẹp chứ không phải bỏ

Bằng chứng ASR **bác bỏ trực tiếp** giả thuyết mà tín hiệu này tồn tại để bắt: nếu cả hai bộ
giải mã chép ra đủ lời mong đợi, thì không có gì bị cắt. Nên:

> `generation_endpoint_active` thôi chặn **khi và chỉ khi** cả hai lần giải mã đều qua.

Còn giải mã trượt thì nó vẫn chặn như cũ. `pace_outlier`, `pitch_variant_skipped`,
`pitch_variant_mixed` không đụng tới trong mọi trường hợp.

`_validated_dual_failed_candidate_conn` **cố ý giữ cách nhìn cũ**, không thu hẹp: nó kiểm tra
*lịch sử đã ghi* dưới luật cũ, và phải tiếp tục kiểm được. Thu hẹp cả chỗ đó thì mọi project cũ
sẽ ném `dual-failed candidate has neither an ASR nor signal blocker` khi resume.

## Bài học rộng hơn

Ba lần trong một tối tôi gặp cùng một hình dạng lỗi: **một phép kiểm dựng cho tình huống A, gặp
tình huống B trông giống A, và không ai bảo nó cách phân biệt.**

| phép kiểm | định bắt | thực tế bắt |
|---|---|---|
| `generation_endpoint_active` | bản thu bị cắt | dấu phẩy và dấu hỏi |
| neo tên (`asr_only_failure`) | tên bị đọc sai | mọi đoạn chỉ gồm một cái tên ngắn |
| `is_vocalization_only` | tiếng cười, tiếng thốt | tiếng cười — trừ khi viết là `Ahaha` |

Cả ba đều không phải "ngưỡng đặt sai". Cả ba là **một lớp ca chưa ai nghĩ tới**, và cả ba đều
lộ ra bằng cùng một cách: nhìn vào những ca bị chặn rồi hỏi *chúng có điểm gì chung*.

Xem thêm [LOCKED_NAME_ANCHOR_IS_A_SPELLING_TEST.md](LOCKED_NAME_ANCHOR_IS_A_SPELLING_TEST.md).
