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
