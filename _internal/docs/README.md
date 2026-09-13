# Mục lục: mở file nào cho câu hỏi nào

Ba mươi tài liệu, sắp theo **câu hỏi chúng trả lời** chứ không theo chủ đề — vì lúc cần đọc thì
người ta có một câu hỏi, không có một chủ đề.

## Tôi sắp chạy một lượt

| câu hỏi | file |
|---|---|
| Chạy cả cuốn thì tốn bao nhiêu, đi đường nào? | [PRODUCTION_PLAN.md](PRODUCTION_PLAN.md) |
| Đang sản xuất CUỐN NÀO, đổi cuốn / quay lại cuốn cũ thế nào? | [`scripts/book_paths.py`](../scripts/book_paths.py) (docstring) — gốc sách là tham số `EBOOK_*`; cuốn 2 (915 chương) theo [PRODUCTION_PLAN_book2.md](PRODUCTION_PLAN_book2.md); `source scripts/book1.env` để quay lại cuốn 1 |
| Lệnh cụ thể để tạo và chạy một phiên bản? | [VERSIONS.md](VERSIONS.md) |
| Lượt chạy tốn thời gian vào đâu? | [WHERE_A_RUN_SPENDS_ITS_TIME.md](WHERE_A_RUN_SPENDS_ITS_TIME.md), [THROUGHPUT.md](THROUGHPUT.md) |
| Máy có đủ VRAM không? | [VRAM_AND_CONTEXT.md](VRAM_AND_CONTEXT.md) |
| Mất điện / bấm nhầm Ctrl-C thì sao? | [SURVIVING_AN_INTERRUPTION.md](SURVIVING_AN_INTERRUPTION.md) |
| Lô chạy chậm hơn ước lượng nhiều? | [THE_MACHINE_IS_SHARED.md](THE_MACHINE_IS_SHARED.md) — nhường máy, không phải treo |
| Lượt chạy đứng yên mà nhịp tim vẫn sống? | [A_POOL_THAT_FORBIDS_ITSELF.md](A_POOL_THAT_FORBIDS_ITSELF.md) |
| Ghép MP3 của 16 lô thành một cuốn thế nào? | [PRODUCTION_PLAN.md](PRODUCTION_PLAN.md) — mục *"Ghép cuốn sách"* |
| Ranh giới giữa hai lô tự chạy thế nào, và lô sau gieo từ đâu? | [PRODUCTION_PLAN.md](PRODUCTION_PLAN.md) — mục *"Ranh giới giữa hai lô"*; `scripts/boundary.sh`, `scripts/seed_chain.py` |

## Có gì đó hỏng

| câu hỏi | file |
|---|---|
| **Vì sao chương này không xuất bản được?** | [WHAT_BLOCKS_A_CHAPTER.md](WHAT_BLOCKS_A_CHAPTER.md) — bản đồ sáu cổng |
| Chương bị chặn mà không ai để hỏi thì sao? | [SHIPPING_WITHOUT_A_LISTENER.md](SHIPPING_WITHOUT_A_LISTENER.md) |
| Hai lượt chạy ra audio khác nhau, vì sao? | [AUDIO_IS_NOT_ALWAYS_REPRODUCIBLE.md](AUDIO_IS_NOT_ALWAYS_REPRODUCIBLE.md) |
| Giọng đọc tự nhiên đổi giữa chừng? | [THE_VOICE_MODEL_IS_NOT_PINNED.md](THE_VOICE_MODEL_IS_NOT_PINNED.md) |
| File nguồn giống hệt nhau mà hash khác? | [THE_SOURCE_IS_WATERMARKED.md](THE_SOURCE_IS_WATERMARKED.md) |
| Bản thu tốt bị ném đi? | [WHY_A_GOOD_TAKE_GETS_THROWN_AWAY.md](WHY_A_GOOD_TAKE_GETS_THROWN_AWAY.md) |
| Đầu đoạn có tiếng lách cách? | [ONSET_CLICK.md](ONSET_CLICK.md) |
| Hai nhân vật nói cùng một giọng? | [TWO_CHARACTERS_ONE_VOICE.md](TWO_CHARACTERS_ONE_VOICE.md) |
| **Một nhân vật nói bằng hai giọng?** | [OPTIMISATION_QUEUE.md](OPTIMISATION_QUEUE.md) — mục *"Câu ngược chưa ai hỏi"*; `scripts/one_person_one_voice.py` |

## Phép kiểm nói gì, và có tin được không

| câu hỏi | file |
|---|---|
| Một cái tên có được đọc giống nhau mỗi lần không? | [A_NAME_READ_MANY_WAYS.md](A_NAME_READ_MANY_WAYS.md) — 170 cờ neo tên mỗi lô, và cái nào là lỗi thật |
| Nhịp đọc đo cái gì, và nó từng đo nhầm gì? | [PACE_METRIC.md](PACE_METRIC.md), [PACE_COUNTS_THE_WRONG_STRING.md](PACE_COUNTS_THE_WRONG_STRING.md) |
| Vì sao tên riêng bị chấm sai? | [LOCKED_NAME_ANCHOR_IS_A_SPELLING_TEST.md](LOCKED_NAME_ANCHOR_IS_A_SPELLING_TEST.md) |
| Vì sao 48% đoạn được sửa đọc tên theo chữ viết, và sửa thế nào không cần GPU? | [KEEP_THE_LOCKED_READING.md](KEEP_THE_LOCKED_READING.md) — bản vá giữ cách đọc ghim, lượt đề cử lại, ba điều bất ngờ |
| Giọng ấy có đúng là giọng của người ấy không (phái, tuổi)? | `scripts/voice_matches_the_person.py` — docstring kể luật giọng trẻ con và ca IVAN |
| Ranh giới chạy xong đêm qua, giờ đọc log thế nào? | [READING_A_BOUNDARY_LOG.md](READING_A_BOUNDARY_LOG.md) — tám bước, câu đáng lo của từng bước, và bốn câu hỏi khác nhau về giọng |
| Cách đọc tên tiếng Anh sinh ra thế nào? | [ENGLISH_TO_VIETNAMESE.md](ENGLISH_TO_VIETNAMESE.md), [SHORT_NAME_PRONUNCIATION.md](SHORT_NAME_PRONUNCIATION.md) |
| Cùng một tên đọc hai kiểu? | [PRONUNCIATION_VARIANT_DRIFT.md](PRONUNCIATION_VARIANT_DRIFT.md) |
| Phán quyết của người nghe hoạt động ra sao? | [LISTENER_VERDICTS.md](LISTENER_VERDICTS.md) |
| Chấm cảm thụ (UTMOS) tốn bao nhiêu? | [PERCEPTUAL_QA_COST.md](PERCEPTUAL_QA_COST.md) |
| Bộ test hiện ra sao? | [TEST_REPORT.md](TEST_REPORT.md) |

## Phân tích và diễn xuất

| câu hỏi | file |
|---|---|
| Model bất đồng với nhau thì xử thế nào? | [ANALYSIS_DISAGREEMENT_POLICY.md](ANALYSIS_DISAGREEMENT_POLICY.md) |
| Thử lại phân tích tốn bao nhiêu? | [ANALYSIS_RETRY_COST.md](ANALYSIS_RETRY_COST.md) |
| Cảm xúc có tới được audio không? | [EMOTION_IN_PRODUCTION.md](EMOTION_IN_PRODUCTION.md) |
| Giọng trẻ em làm thế nào? | [CHILD_VOICE_TRANSFORM.md](CHILD_VOICE_TRANSFORM.md) |

## Nền tảng

| câu hỏi | file |
|---|---|
| Dự án phụ thuộc gì, đổi thì sao? | [DEPENDENCIES.md](DEPENDENCIES.md), [THIRD_PARTY.md](THIRD_PARTY.md) |
| Việc gì đáng làm tiếp? | [OPTIMISATION_QUEUE.md](OPTIMISATION_QUEUE.md) |
| Hôm qua đã xảy ra chuyện gì? | [WORK_LOG.md](WORK_LOG.md) |

## Một lời về cách đọc những tài liệu này

Nhiều file ở đây ghi cả những thứ **đã bị bác bỏ** — giả thuyết nghe rất hợp lý rồi chết khi
đo, ngưỡng bịa ra rồi phải bỏ, câu tôi viết buổi sáng rồi tự sửa buổi chiều. Chúng nằm lại có
chủ ý.

Lý do: phần lớn thời gian trong dự án này không tiêu vào việc *sửa* mà vào việc *tìm đúng thứ
cần sửa*, và một kết luận đúng không dạy được điều đó. Bốn giả thuyết chết trước khi tìm ra
model giọng đã tự đổi thì đáng đọc hơn chính câu kết luận — vì lần sau, thứ hỏng sẽ khác, mà
cách đi thì vẫn thế.

- **Fixture cho test:** `D:/Novels/Audiobooks/_fixtures/` (ngoài repo). Test không được trỏ vào project sống; xem `_fixtures/*/README.md` và WORK_LOG 2026-09-12 18:07.
