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
| nhịp đọc | đọc quá chậm | **câu toàn từ ngắn** — 2,25 chữ/từ so với trung vị 3,33; theo âm tiết đọc gần trung vị kho | hàng chờ (`patch_pace_counts_syllables_too`) |
| âm vị neo tên | cùng âm thì khớp | `k` và `c` bị coi là khác âm | rồi |
| `repeated_utterance_score` | hai nửa giống nhau đến đâu | bị khoảng lặng **ngoài rìa** bóp méo | **chưa** |
| `max_join_jump` | tiếng click ở chỗ nối | **đúng thế** — bắn 1/107, vào cực trị thật | không cần |

Xem [WHY_A_GOOD_TAKE_GETS_THROWN_AWAY.md](WHY_A_GOOD_TAKE_GETS_THROWN_AWAY.md),
[PACE_COUNTS_THE_WRONG_STRING.md](PACE_COUNTS_THE_WRONG_STRING.md),
[LOCKED_NAME_ANCHOR_IS_A_SPELLING_TEST.md](LOCKED_NAME_ANCHOR_IS_A_SPELLING_TEST.md),
[ONSET_CLICK.md](ONSET_CLICK.md).

## Mọi nguyên nhân từng thấy, và cái gì đang đỡ nó (2026-09-09)

Gộp `last_error` của hai lô đã chạy về **nguyên nhân** (`plan_repair_batch.py` in ra bảng này),
rồi đối chiếu với những gì đã vào cây:

| nguyên nhân | ở đâu | cái đỡ nó | đã chứng minh trên audio thật? |
|---|---|---|---|
| `ASR_MISMATCH_UNRESOLVED` | alpha.60 ch 019, 021, 024 | `MACHINE_ACCEPTABLE_SEGMENT_WARNINGS` | **có** — lô 1, 13 lần cho qua có ghi sổ |
| `ASR_LOCKED_NAME_ANCHOR_MISMATCH` | alpha.60 ch 020 | `MACHINE_ACCEPTABLE_SEGMENT_WARNINGS` | **có** — cùng cơ chế |
| chạm trần khung, 0 ứng viên | alpha.60 ch 026 (`"Gì cơ?"`) | `patch_ceiling_repairable` | **chưa** — lỗi không tái diễn |
| `join discontinuity` | lô 1 ch 003, 016 | `patch_edge_fade` | **có** — 0,219 → 0,0215 ở lô vá |
| `loudness delta` | lô 1 ch 000 | `patch_loudness_review_ships` | **có** — cờ vẫn ghi, chương vẫn xuất |
| `TTS_PACE_BAND_RELAXED` | lô 1 ch 007 | `patch_pace_relaxed_is_a_decision` | **chưa** — lần chạy lại ra 14,07 nên đường nới không mở |
| `ASR_TRANSCRIPT_RATE_IMPOSSIBLE` | lô 2 ch 031, 043 | `patch_rate_impossible_is_the_same_family` | **có** — ch031 chạy lại, Whisper vẫn lặp 19 lần, mã vẫn nổ, giờ là `warning` và chương xuất bản được |
| trần khung + ASR không phán xử được | lô 2 ch 053 | `patch_finished_take_beats_a_cut_off_one` | **chưa** — lần chạy lại đoạn ấy dài 1,36s và không chạm trần |
| surrogate lạc giết cả cuốn | lô 1, lần chạy đầu | `patch_lone_surrogate` | **có** — lô1b qua đúng đoạn đã giết lần trước |
| giới tính không phân giải được (cổng 7) | alpha.5x | `patch_casting_gate_no_halt` | **chưa** — chưa gặp lại |
| `SEGMENT_FAILED` — nhịp 10,6–11,8 chars/s 10/10 lần, câu 38 ký tự không chia được, dải đã `normal` | lô 3 ch 075 | `patch_pace_counts_syllables_too` | **có** — ch075 chạy lại qua lần đầu ở 10,64 kt/s, 4,50 âm tiết/giây |
| `SEGMENT_FAILED` — cách đọc nối gạch đếm 1 âm tiết (`I-xờ-hờ-ta-ra`, `A-lờ-va-ra`) | lô 3 ch 084, lô 4 ch 097 | `patch_a_transliteration_is_many_syllables` | **có** — ch097 chạy lại qua lần đầu ở 10,74 kt/s, 4,73 âm tiết/giây; ch084 đúc lại: bản đọc-ghim qua nhịp ở 12,47 kt/s / 4,99 âm tiết/giây rồi chết ở neo tên, bản lên sách là bản đọc theo chữ viết |
| `SEGMENT_FAILED` — chữ số dài + tiếng Anh chưa có cách đọc (`password`, `123456`, `qwerty`) | lô 4 ch 106 | `patch_a_number_is_read_in_full` (xếp hàng 5 → 6) | **chưa** — 11 lần ở 12,35 kt/s; sau bản vá đoạn ấy đo 15,5 kt/s / 4,6 at/s; đúc lại bằng `--recast 4:106` |

Tám nguyên nhân ở tầng chương, hai ở tầng cuốn sách. **Năm đã chứng minh trên audio thật, năm
chỉ có unit test đứng sau.**

Ba trong năm cái "chưa" nằm đó vì cùng một lý do, không phải vì ai lười: lỗi phụ thuộc seed thì
một lô vá là chỗ **tệ** để chứng minh, vì chạy lại là rút một lá khác. Xem
[PRODUCTION_PLAN.md](PRODUCTION_PLAN.md), mục *"Lô vá là chỗ TỆ để chứng minh một bản vá"*.

Điều bảng này *không* nói: rằng danh sách đã đủ. Nó là danh sách những nguyên nhân đã **xảy
ra**, trên 39 chương đã chạy của một cuốn 478 chương. Lô 2 tồn tại một phần để hỏi xem cái đuôi
ấy còn dài bao nhiêu — xem [PRODUCTION_PLAN.md](PRODUCTION_PLAN.md), mục dự đoán viết trước.

## Lô 2 thêm hai nguyên nhân vào bảng, và một cái đã ở đó rồi (2026-09-10)

Lô 2 mất **ba** chương trên ba mươi, vì **hai** nguyên nhân:

| ch | mã | là gì |
|---|---|---|
| 031, 043 | `ASR_TRANSCRIPT_RATE_IMPOSSIBLE` | **mới** — nhưng là em ruột của một mã đã có trong danh sách không-chặn, bị bỏ sót khi mã kia được nâng từ chuỗi trần thành hằng số |
| 053 | trần khung + ASR không phán xử được | **đã có trong bảng trên**, ở dòng ghi "chưa chứng minh" |

Cả hai đoạn của 031 và 043 là **tiếng cười**: `'"Ahaha! Hahahaha!"'` và
`'"Aaahahahaha! Hahahahaha!"'`. Whisper rơi vào vòng lặp, phiên ra `'huff huff huff…'` mười lăm
lần và `'ah ah ah…'` hai mươi sáu lần — dài hơn thứ mà 2,3 giây audio chứa được, nên phép kiểm
nổ **đúng** và nói một điều thật về *phiên bản*. Nó không nói gì về *bản thu*.

Còn chương 053 là ca thứ ba của một họ đã biết, và nó **minh oan cho `patch_ceiling_repairable`**:
đoạn `'"Bất bại?"'` có đủ năm ứng viên, tức đường thu lại **đã mở** — lần đầu bản vá ấy chạy
ngoài unit test. Vấn đề nằm sau đó: hai ứng viên tự kết thúc bị xử bằng `ASR_MISMATCH` trên một
văn bản sáu ký tự chữ-số, tức bằng một phép kiểm mà dự án đã đo là trượt 75% số lần ở độ dài ấy.

## Dự đoán viết trước lô 2, và nó **sai**

[PRODUCTION_PLAN.md](PRODUCTION_PLAN.md) ghi trước khi chạy: *"lô 2 phải hỏng 0–1 chương, và bất
kỳ chương nào hỏng cũng phải hỏng vì một nguyên nhân chưa từng thấy"*. Kết quả: **3 chương, 2
nguyên nhân, và một trong hai đã từng thấy**.

Cả hai cách đọc tôi đăng ký trước đều không khớp: không phải "0–1 nên đuôi đang cạn", cũng không
phải "3–5 toàn nguyên nhân mới nên đuôi vô hạn". Cách đọc đúng là cái thứ ba tôi không viết ra:

> Tôi ngầm coi "đã có bản vá" là "sẽ không tái diễn", trong khi **chính bảng ở trên** đã ghi rõ
> bốn trong tám nguyên nhân chỉ có unit test đứng sau. Một trong bốn ấy nổ.

Bài học cụ thể: cột "đã chứng minh trên audio thật?" trong bảng trên không phải để trang trí.
Khi nó ghi "chưa", con số phải được đếm vào dự đoán chứ không được trừ ra.

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

## Cổng thứ bảy, và nó chặn cả CUỐN SÁCH chứ không chặn một chương (2026-09-08)

Lô 1b chết lần thứ hai, sau **4 giờ phân tích trọn vẹn 3.727 đoạn**, ngay tại cổng đúc giọng:

```
RuntimeError: Casting input quality gate failed:
gender conflicts={'SỐ SÁU': {'female': 1, 'male': 1, 'text_evidence': {'female': 3}}}
```

Một nhân vật **phụ, hai câu thoại**, model gán một câu nữ một câu nam. `resolve_gender` hỏi tới
văn bản, văn bản trả lời **3 nữ / 0 nam** — nhất trí tuyệt đối — nhưng
`GENDER_EVIDENCE_MINIMUM_HITS = 5` nên `_decisive` trả `None`, và cổng giết cả lượt chạy.

Đọc sách thì chuyện rõ ràng:

> *"…**người phụ nữ** đầu tiên bắt bẻ… Mang số sáu, **cô ta** cho rằng mình hoàn toàn có quyền
> nhìn kẻ hậu bối bằng nửa con mắt."*

`SỐ SÁU` là nữ, và nhãn `male` là model gán sai. Bằng chứng văn bản **đúng**; ngưỡng chặn một
quyết định đúng.

### Hạ ngưỡng là hướng sai — số liệu nói thế

Cám dỗ hiển nhiên: 3 hit nhất trí thì cho quyết luôn. Đo trên **mọi project đã lưu**, so bằng
chứng văn bản nhất trí (`loser = 0`) với những nhân vật mà model cũng nhất trí:

```
1 hit : khớp 17, lệch 18      ← đúng bằng tung đồng xu
2 hit : khớp  6, lệch  0
3 hit : khớp  8, lệch  5      ← lệch 38%
4 hit : khớp  8, lệch  0
5 hit : khớp  3, lệch  0      ← ngưỡng hiện tại
```

Ở 3 hit, bằng chứng văn bản **mâu thuẫn với model 5 lần trên 13**. Ngưỡng 5 không phải con số
tuỳ tiện. Hạ nó là mua một lỗi im lặng để tránh một lỗi ồn ào.

### Cách gỡ đã dùng, và cách sửa đúng

**Gỡ ngay:** `cli cast --character "SỐ SÁU" --gender female`. Đó là **đọc sách**, không phải
đoán — và quan trọng hơn, nó **không đổi mã**, nên `resume` giữ trọn 4 giờ phân tích. Thiệt hại
thật của sự cố: ~20 phút.

**Sửa đúng, chưa làm:** cổng này vi phạm chính nguyên tắc dự án đã chốt ở
[SHIPPING_WITHOUT_A_LISTENER.md](SHIPPING_WITHOUT_A_LISTENER.md) — *một phép kiểm không phán xử
được thì không được chặn*. Ở đây nó còn tệ hơn cổng cảnh báo segment: chương hỏng thì mất một
chương, còn cổng này hỏng thì **mất cả cuốn sách**, sau khi đã tiêu hết phần đắt nhất của lượt
chạy.

Hình dạng bản vá: không `raise`, mà ghi log to, phát `db.event`, đúc bằng câu trả lời tốt nhất
còn lại, và liệt kê nhân vật ấy trong báo cáo để người nghe khoá lại sau bằng `cli cast`. Giống
hệt cơ chế máy tự cho qua: **không đợi ai, nhưng không bao giờ im lặng.**

## Cổng 5 cũng là một bức tường, và nó chặn vì một phép đo sát ngưỡng (2026-09-09)

Chương đầu tiên của lô 1 hỏng ngay:

```
temporary MP3 requires review under high-quality policy: loudness delta 0.62 LU
```

Cả hai đoạn của nó đều `verified`. Cái chặn là QA tầng chương, và cụ thể là một **cờ review**
chứ không phải lỗi cứng: `CHAPTER_LOUDNESS_REVIEW_TOLERANCE_LU = 0.30`,
`CHAPTER_LOUDNESS_HARD_TOLERANCE_LU = 0.75`, và số đo là **0,62** — nằm giữa. Nghĩa đen của nó
là *"có thể đáng nghe, hỏi một người"*, mà không có người nào.

### Hai giả thuyết, cả hai chết khi đo

**"Chương quá ngắn nên LUFS không đo nổi."** Chương 000 dài 7,5 giây. Nghe hợp lý — LUFS tích
hợp cần vài giây. Đếm trên mọi bản đã lưu: **24 chương dưới 30 giây, chỉ 1 bị gắn cờ**. Không
phải hiệu ứng độ dài.

**"Nội dung này có gì đó bất thường."** Đếm kỹ hơn thì 24 chương ngắn ấy hoá ra là **cùng một
chương 000**, chạy lại qua 24 phiên bản — và nó vượt ngưỡng **đúng một lần trong 24**. Cùng
chữ, cùng giọng, 24 lần đúc, một lần rơi sang bên kia vạch.

Đó là một **phép đo sát ngưỡng**, không phải một khiếm khuyết.

### Vì sao đây vẫn là bức tường phải sửa

Vì hậu quả không tương xứng với nguyên nhân: 0,62 LU là chênh lệch dưới hoặc quanh ngưỡng nghe
thấy được của tai người, và nó làm một chương **không bao giờ xuất bản** khi không có ai để hỏi.
Đúng hình dạng mà [cơ chế máy tự cho qua](SHIPPING_WITHOUT_A_LISTENER.md) sinh ra để phá, chỉ
khác tầng.

Và ở đây có sẵn một ranh giới **không phải do tôi bịa ra**: chính dự án đã đặt
`CHAPTER_LOUDNESS_HARD_TOLERANCE_LU = 0.75` làm vạch "quá mức này thì chắc chắn có vấn đề".
Một cờ review nằm dưới vạch cứng ấy là thứ chính phép kiểm tự nhận là chưa chắc — cùng lý lẽ
với *"ASR là nhân chứng duy nhất"*, chỉ khác là ở đây nhân chứng thứ hai là **ngưỡng cứng của
chính phép kiểm**.

### Ngoài lề, nhưng đáng cho chủ sách biết

Chương 000 **không phải nội dung sách**. Nó là ghi chú của người đăng:

> *"Chuyên mục bổ mắt"* · *"Lưu ý: các bức ảnh trên đều là hàng fan art, do mình thấy đẹp và bổ
> mắt…"*

Bảy giây rưỡi nói về mấy tấm ảnh không tồn tại trong file text. Có nên nằm trong audiobook
không là quyết định của chủ sách, không phải của máy — nên nó được ghi ở đây chứ không bị âm
thầm bỏ.
