# Các phép đo chỉ-đọc — hỏi gì thì chạy cái nào

21 script `measure_*.py` trong thư mục này. Tất cả **chỉ đọc**: mở project ở chế độ read-only,
quét nguồn, không ghi gì. Chạy được bất cứ lúc nào, kể cả khi một lô đang bay.

Vì sao nhiều thế: luật của dự án là **đo trước khi vá**. Mỗi script ở đây ra đời từ một câu hỏi
thật, và docstring của nó giữ **con số đã đo** cùng ngày giờ — nên đọc docstring trước khi chạy
lại, phần lớn câu trả lời đã có sẵn ở đó.

Ba script trong số này kết thúc bằng **"không vá"**, và chúng ở lại vì thế:
`measure_would_a_name_fold_be_safe.py` (luật gộp tên sẽ gộp sai 47 cặp),
`measure_a_loanword_noun.py` (1.796 lần xuất hiện teo lại thành 1 đoạn hỏng khi so với nền), và
`measure_a_phantom_by_its_own_chapter.py` (thước tốt, nhưng hành động phải khác theo lớp).

## Luật khi viết một phép đo mới

Ba lần trong một buổi sáng ngày 16-09, thước của tôi nói sai, và cả ba lần **đối chứng** bắt được:
thước phantom gắn cờ `LUCIEN` 378 câu; thước nhóm-nhãn gom `KANG` với `KAIN REICHARDT` (hai người
khác nhau); cùng thước ấy gắn cờ `NGUOI TRA LOI` là "không có trong nguồn" khi nguồn viết đủ dấu.

Nên: **chạy thước trên CẢ TẬP, không chỉ trên các nghi can, rồi đọc những ca nó gắn cờ mà bạn biết
là sai.** Một thước đúng trên 25/25 nghi can vẫn có thể sai trên 67/191 nhãn.

## Giọng: ai là ai, và ai giữ giọng nào

Nền tảng: [`docs/WHO_OWNS_A_VOICE.md`](../docs/WHO_OWNS_A_VOICE.md) và
[`docs/TWO_CHARACTERS_ONE_VOICE.md`](../docs/TWO_CHARACTERS_ONE_VOICE.md).

| script | câu hỏi |
|---|---|
| `one_person_one_voice.py` | Một **tên** có mang hai giọng không — cùng chương (nặng) hay khác chương? |
| `measure_who_contends_for_a_voice.py` | Bao nhiêu người mang hai giọng **vì** giọng của họ bị người khác tranh? |
| `measure_did_the_recast_help.py` | Một lượt đúc lại đưa giọng **về** đa số của sách hay đẩy đi xa hơn? |
| `measure_one_person_many_labels.py` | Một **người** nhiều nhãn (gõ sai, thiếu họ) — mỗi nhãn một giọng |
| `measure_a_name_that_is_not_in_the_source.py` | Nhãn nào không tồn tại trong nguồn mà vẫn đang giữ một giọng? |
| `measure_would_a_name_fold_be_safe.py` | Luật gộp tên đề xuất sẽ gộp sai bao nhiêu cặp? (**đã bác bỏ**) |
| `voice_pool_pressure.py` | Kho giọng còn chỗ không — theo **chương đông nhất**, không theo tổng |
| `voice_matches_the_person.py` | Giọng ấy có đúng phái/tuổi của người ấy không? |

## Tên và cách đọc

Nền tảng: [`docs/A_NAME_READ_MANY_WAYS.md`](../docs/A_NAME_READ_MANY_WAYS.md),
[`docs/LOCKED_NAME_ANCHOR_IS_A_SPELLING_TEST.md`](../docs/LOCKED_NAME_ANCHOR_IS_A_SPELLING_TEST.md).

| script | câu hỏi |
|---|---|
| `measure_phantom_speakers.py` | Bao nhiêu "nhân vật" thật ra là chữ mở đầu câu tường thuật sau ngoặc kép? |
| `measure_a_phantom_by_its_own_chapter.py` | Một chương có tự đủ bằng chứng để phán điều đó? |
| `measure_the_first_person_labels.py` | Nhãn `tôi`/`ta`/`me`: bao nhiêu câu, và là lời của ai? |
| `measure_a_name_spelled_two_ways.py` | Nguồn viết sai một cái tên đã có cách đọc — bao nhiêu chỗ? |
| `measure_the_dead_exclusions.py` | Mục nào trong `NAME_CANDIDATE_EXCLUSIONS` chưa từng khớp gì? |
| `measure_a_loanword_noun.py` | Danh từ vay mượn (`amoniac`, `urê`) có thật tốn gì không? |

## Nhịp đọc và bản thu

Nền tảng: [`docs/PACE_METRIC.md`](../docs/PACE_METRIC.md),
[`docs/PACE_COUNTS_THE_WRONG_STRING.md`](../docs/PACE_COUNTS_THE_WRONG_STRING.md).

| script | câu hỏi |
|---|---|
| `measure_pause_budget_vs_silence.py` | Ngân sách nghỉ có khớp khoảng lặng **có thật** trong bản thu? |
| `measure_a_silence_capped_pace.py` | Chặn ngân sách bằng khoảng lặng thật thì cứu bao nhiêu, giết bao nhiêu? |
| `measure_a_number_with_a_unit.py` | `10h` so với `mười giờ`: phép so ASR mất bao nhiêu? |

## Thời gian máy và tài nguyên

Nền tảng: [`docs/WHERE_A_RUN_SPENDS_ITS_TIME.md`](../docs/WHERE_A_RUN_SPENDS_ITS_TIME.md),
[`docs/THROUGHPUT.md`](../docs/THROUGHPUT.md), [`docs/VRAM_AND_CONTEXT.md`](../docs/VRAM_AND_CONTEXT.md).

| script | câu hỏi |
|---|---|
| `measure_critic_free_text.py` | Hai trường tự do của phản biện nặng bao nhiêu token? |
| `measure_ollama_parallel.py` | Chạy song song các lô phân tích có làm pha đắt nhất rẻ hơn? |
| `measure_batched_asr.py`, `measure_concurrent_asr.py`, `measure_beam_vs_greedy.py`, `measure_encoder_window.py` | ASR: gộp lô, chạy song song, beam, cửa sổ encoder |
| `measure_pool_worker_ram.py` | Đỉnh RSS của mỗi worker trong pool, đo lúc lô đang chạy thật |

## Không phải phép đo, nhưng hay cần

| script | dùng khi |
|---|---|
| `heartbeat_tick.py` | Một nhịp: ranh giới ở bước nào, project nào đang bay, cây git sạch chưa |
| `seed_chain.py` | Project nào là "mới nhất" của một lô; `--chain-all` cho sổ cộng dồn |
| `before_a_batch.py` | Cổng trước mỗi lô: cây sạch, hàng chờ rỗng, bộ test đã xanh |
| `assemble_book.py --verify` | Sách đã ghép có lệch gì so với manifest không |
| `resync_spoken_text.py` | Bản vá đổi chuỗi nói: đặt lại đúng những đoạn lệch về chờ thu |
| `pin_the_book_cast.py` | Ghim giọng đa số của cả sách cho người chưa có pin |
| `keep_the_chapter_cast.py` | Đúc lại một chương đã lên sách mà CHỈ đổi người cần đổi (`--chapters` để mô phỏng) |
| `plan_repair_batch.py`, `machine_acceptances.py` | Lô vừa xong: chương nào hỏng vì sao, máy đã nhận gì |
