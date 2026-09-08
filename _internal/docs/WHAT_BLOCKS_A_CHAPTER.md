# Cái gì chặn một chương

Đêm 2026-09-07/08 tôi phải đào từng cổng một mới biết có **sáu** cơ chế chặn khác nhau, và một
script tôi tự viết để đo đã đếm sai vì chỉ biết một trong số đó. Tài liệu này là bản đồ ấy, để
người sau không phải đào lại.

## Sáu cổng, theo thứ tự một chương đi qua

| # | cổng | ở đâu | chặn khi |
|---|---|---|---|
| 1 | chia đoạn | `text_processing.segment_chapter_text` | **không còn chặn nữa** — ngoặc kép treo tự phục hồi từ 2026-09-08 |
| 2 | sinh TTS | `pipeline._process_single_segment` | segment không sinh nổi audio sau 11 lần thử ⇒ `SEGMENT_FAILED` |
| 3 | cảnh báo segment | `pipeline._high_quality_blocking_segment_warnings` | segment mang mã **không** nằm trong `HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS` và chưa có phán quyết ⇒ `SEGMENT_QA_REVIEW_REQUIRED` |
| 4 | bằng chứng segment | `pipeline._chapter_has_current_segment_audio_qa` | thiếu bằng chứng ASR/cảm thụ cho một segment ⇒ `SEGMENT_QA_EVIDENCE_MISSING` |
| 5 | QA tầng chương | `audio_io._evaluate_chapter_quality` | chỗ nối, im lặng, độ to, đỉnh, lệch DC… ⇒ `CHAPTER_QA_REVIEW_REQUIRED` |
| 6 | cổng xuất bản | `database.chapter_is_publishable` | segment ở trạng thái `failed` mà không có phán quyết khớp checksum |

**Cổng 5 là cái dễ bỏ sót nhất.** Nó nằm hoàn toàn ngoài cổng 3, và `scripts/machine_credit.py`
mù với nó cho tới 2026-09-08 — đếm 5 chương chặn trong khi thật ra 6.

## Mã cảnh báo segment: cái nào chặn, cái nào không

Đếm trên alpha.50–60:

| mã | số lần | chặn? |
|---|---|---|
| `ASR_LOCKED_NAME_ANCHOR_REVIEW` | 158 | **không** |
| `ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE` | 70 | **không** |
| `ASR_UNVERIFIABLE_SHORT_TEXT` | 43 | **không** |
| `ASR_LOCKED_NAME_ANCHOR_MISMATCH` | 24 | **CÓ** |
| `PERCEPTUAL_NATURALNESS_REVIEW` | 15 | **CÓ** |
| `TTS_SPLIT_RECOVERY` | 15 | **không** |
| `ASR_MISMATCH_UNRESOLVED` | 11 | **CÓ** |
| `TTS_GENERATION_CEILING_REACHED` | 5 | **không** |
| `SEGMENT_FAILED` | 2 | **CÓ** |
| `TTS_PACE_OUTLIER` (chỉ thấy trong mã ghép) | 1 | **CÓ** |

Mã ghép bằng `|` được tách ra và **lọc từng cái**, nên `TTS_SPLIT_RECOVERY|TTS_PACE_OUTLIER`
vẫn chặn: nửa đầu được cho qua, nửa sau thì không.

Nguyên tắc phân loại đã được dự án chốt từ lâu và đáng giữ: **một phép kiểm không có ý kiến thì
không được chặn.** Năm mã "không chặn" đều thuộc loại ấy — chúng ghi rằng ASR *không phán xử
được*, chứ không phải ASR *phán là hỏng*.

## Phép kiểm nào đáng tin, phép kiểm nào đo nhầm thứ

Đêm 2026-09-07/08 tìm được năm phép kiểm đo nhầm thứ nó nói, và **một** phép kiểm đo đúng. Khác
biệt ấy quan trọng hơn danh sách:

| phép kiểm | định đo | thực tế đo | đã sửa |
|---|---|---|---|
| neo tên (`asr_only_failure`) | tên đọc sai | mọi đoạn **chỉ gồm** một tên ngắn | rồi |
| `is_vocalization_only` | tiếng cười | tiếng cười — trừ khi viết `Ahaha` | rồi |
| nhịp đọc | đọc quá chậm | **văn bản có chữ số** | rồi |
| âm vị neo tên | cùng âm thì khớp | `k` và `c` bị coi là khác âm | rồi |
| `repeated_utterance_score` | hai nửa giống nhau đến đâu | bị khoảng lặng **ngoài rìa** bóp méo | **chưa** |
| `max_join_jump` | tiếng click ở chỗ nối | **đúng thế** — bắn 1/107, vào cực trị thật | không cần |

Xem [WHY_A_GOOD_TAKE_GETS_THROWN_AWAY.md](WHY_A_GOOD_TAKE_GETS_THROWN_AWAY.md),
[PACE_COUNTS_THE_WRONG_STRING.md](PACE_COUNTS_THE_WRONG_STRING.md),
[LOCKED_NAME_ANCHOR_IS_A_SPELLING_TEST.md](LOCKED_NAME_ANCHOR_IS_A_SPELLING_TEST.md),
[ONSET_CLICK.md](ONSET_CLICK.md).

## Cách đo "chương nào chặn vì cái gì"

```bash
_internal/.venv/Scripts/python.exe scripts/machine_credit.py <project> [--compare <project trước>]
```

Nó tách **công của máy** khỏi **công của phán quyết cũ**, và đếm cả cổng 5. Con số so được giữa
hai phiên bản là cột "công của máy"; con số chương xuất bản thì không, vì phán quyết tích luỹ
làm nó tăng kể cả khi mã không đổi một dòng.

## Cập nhật 2026-09-08: ai được mở cổng 3 và cổng 6

Từ [cơ chế xuất bản khi không có ai để hỏi](SHIPPING_WITHOUT_A_LISTENER.md), **cổng 3 và cổng
6 nhận phán quyết từ hai nguồn** thay vì một:

| nguồn | bảng | khi nào |
|---|---|---|
| người nghe | `listener_audio_acceptances` | bất cứ lúc nào, qua `cli accept` |
| **máy** | `machine_audio_acceptances` | sau khi vòng sửa cạn, và **chỉ** khi ASR là nhân chứng duy nhất |

Cổng 4 (`_chapter_has_current_segment_audio_qa`) cũng đọc cả hai, vì nó vốn đã có ngoại lệ cho
phán quyết người nghe và ngoại lệ ấy giờ rộng ra.

**Đọc bảng nào ở đâu, và đừng nhầm:**

- mọi **cổng** gọi `ProjectDB.ruled_segment_warnings()` / `ruled_segment_takes()` — hợp hai
  nguồn, vì câu hỏi của cổng là *"còn phải quyết lại gì không"*;
- mọi **báo cáo** gọi `accepted_segment_warnings()` — chỉ người nghe, vì câu hỏi của báo cáo là
  *"cái này đã có tai người nào chưa"*.

Trộn hai hàm là cách duy nhất cơ chế này có thể nói dối chủ sách, nên chúng cố ý mang hai cái
tên và không hàm nào gọi hàm kia ngoài `ruled_`.

Có **sáu** chỗ đọc phán quyết, không phải một, và đó là lý do phải có một accessor chung:
`chapter_is_publishable`, `chapter_segments_have_current_audio_qa`,
`pipeline._listener_ruled_on_this_take`, tiền điều kiện perceptual,
`_high_quality_blocking_segment_warnings`, và bản quét trong `recovery.py`. Mỗi cái từng được
vá riêng sau khi làm mất một chương. Cổng thứ bảy chỉ cần gọi `ruled_` và không phải biết có
mấy bảng.

**Máy không mở cổng 2 và cổng 5.** `SEGMENT_FAILED` (không có audio) và QA tầng chương nằm
ngoài `MACHINE_ACCEPTABLE_SEGMENT_WARNINGS` — cả hai đều là bằng chứng về chính file âm thanh,
không phải về việc ASR đọc được hay không.

## Bản vá trần khung vẫn chưa có bằng chứng trên audio thật (2026-09-08)

alpha.62 chạy lại đúng dải 019..027 để đo bản vá `_segment_generation_hit_ceiling` — thứ cho
phép thu lại một bản thu chạm trần khung dù ASR không phán xử được. Ca mục tiêu là `"Gì cơ?"`
chương 026, đoạn có **0 ứng viên** ở alpha.60 vì đúng lỗ hổng ấy.

Kết quả: **bản vá không được kích hoạt, vì lỗi không tái diễn.**

```
alpha.60: 1,92s  chạm trần  ->  failed,  0 ứng viên   (lỗ hổng)
alpha.62: 0,56s  KHÔNG chạm ->  warning, 0 ứng viên   (không có gì để sửa)
```

Không chạm trần thì `_segment_generation_hit_ceiling` trả `False` và đường thu lại không mở —
đúng như thiết kế. Lỗi biến mất vì **model giọng đã đổi**
([AUDIO_IS_NOT_ALWAYS_REPRODUCIBLE.md](AUDIO_IS_NOT_ALWAYS_REPRODUCIBLE.md)), không vì bản vá.

Nên bản vá vẫn chỉ có **ba unit test** đứng sau nó. Ghi lại đây thay vì để nó lẳng lặng được
coi là đã chứng minh — một bản vá chưa bao giờ chạy thì không khác gì một bản vá chưa viết, và
sự khác biệt ấy chỉ lộ ra khi lỗi tái diễn.

Điều kiện để có bằng chứng thật: một lượt chạy nào đó sinh ra bản thu chạm trần **và** ASR
không phán xử được. Đó là lỗi phụ thuộc seed, đo được **2 ca trên 38.520 đoạn**
([OPTIMISATION_QUEUE.md](OPTIMISATION_QUEUE.md)), nên nó sẽ tự đến trong 16 lô sản xuất chứ
không cần dựng riêng.

### Whisper ảo giác câu mời đăng ký kênh, và nó lặp lại qua hai model

Cùng đoạn `"Gì cơ?"` ấy, hai lượt chạy, hai model khác nhau:

```
alpha.60  "Các bạn hãy đăng ký kênh để ủng hộ kênh của mình nhé."          WER 6,5
alpha.62  "Hãy subscribe cho kênh Ghiền Mì Gõ Để không bỏ lỡ những video"  WER 7,5
```

Một câu hai từ, 0,5–2 giây, và Whisper rơi vào cùng một hố cả hai lần — chỉ khác tên kênh. Đó
là bằng chứng cho chính lý lẽ đặt `ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE` vào nhóm không chặn:
transcript ấy nói về **Whisper**, không nói gì về bản thu.
