# Giá của việc chấm điểm cảm thụ

UTMOSv2 là phép kiểm tra chất lượng duy nhất trong dự án nghe được bằng tai thay cho
người. Nó cũng là khoản tốn kém ngoài-TTS lớn nhất. Tài liệu này ghi những gì đã đo về
giá của nó.
## Ba lượt suy luận có cần không? (đo 2026-09-03)

`perceptual_qa.num_repetitions = 3` nằm trong settings mặc định mà không có ghi chú nào
nói tại sao. Đây là khoản tốn kém ngoài-TTS lớn nhất của một lần chạy: alpha.25 tốn
1934s cho 979 lượt chấm trên tổng 5100s, gần bằng toàn bộ TTS (2055s) và lớn hơn TTS ở
chương 8 (287.8s so với 262.6s). Nếu một lượt trả lời cùng một câu hỏi thì hai phần ba
số đó đang tiêu phí.

Đo trên 8 bản thu thật, cùng model, cùng seed, chỉ đổi `num_repetitions`:

| | |
|---|---|
| chênh lệch điểm lớn nhất | **0.208337** |
| chênh lệch trung bình | 0.099490 |
| ngưỡng quyết định (`review_delta`) | 0.8 |

Từng bản: 0.040, 0.048, 0.058, 0.064, 0.115, 0.118, 0.143, 0.208.

**Kết luận: giữ nguyên 3.** Một lượt lệch tới **26% biên quyết định**. Quyết định ở đây là
"tụt bao nhiêu so với bản xem trước của chính preset đó", nên một segment thực sự tụt 0.6
có thể ngẫu nhiên vượt ngưỡng, và một segment thực sự tụt 0.85 có thể ngẫu nhiên không
vượt. Đổi lấy 21 phút mỗi lần chạy để mất một phần tư biên an toàn của phép kiểm tra chất
lượng duy nhất nghe được bằng tai là không đáng — nhất là khi còn một khoản 2055s (40%)
lấy được mà không mất gì, bằng cách chồng lấn QA với TTS.

Cách đo: `scratchpad/utmos_reps.py`. Lưu ý cho người đo lại: `UTMOSNaturalnessVerifier`
nhận **toàn bộ** dict settings rồi tự đọc khoá `perceptual_qa` bên trong; truyền thẳng
dict con vào thì `enabled` thành False và `load()` lặng lẽ trả về False.

## Một worker chấm điểm tốn bao nhiêu RAM thật? (đo 2026-09-03)

`PERCEPTUAL_WORKER_RAM_GB` là con số mà `usable_for()` đem chia RAM trống để quyết định cấp
mấy worker. Nó ghi **1,0 GB**. Đo thật:

| phép đo | kết quả |
|---|---|
| RSS của một worker sau khi nạp UTMOSv2 | 1,87 GB |
| đỉnh RSS khi đang chấm | 2,18 GB |
| chi phí biên (nhìn RAM trống toàn máy), worker 1 | 1,76 GB |
| chi phí biên, worker 2 | 1,52 GB |
| chi phí biên, worker 3 | *nhiễu* (RAM trống **tăng** — job khác nhả bộ nhớ) |

Mọi con số đều cao hơn hẳn 1,0. Với 7,3 GB trống, pool đang cấp **5 worker**, tức khoảng
**8,8 GB worker trên 7,3 GB bộ nhớ**.

Đây không phải lỗi thông lượng, đây là **cách một lần chạy chết**. alpha.26 dừng ở 357/948
segment vì "available RAM 1.1 GB". Và phần chồng lấn mới - chấm điểm chạy cạnh ASR - làm
con số cũ nguy hiểm hơn nữa, vì pool không còn chờ Whisper nhả bộ nhớ trước khi đòi.

Đã sửa thành **1,75 GB**. Sai lệch về phía cao là hướng rẻ: quá lớn thì mất worker, quá nhỏ
thì mất cả lần chạy. Với 7,3 GB trống, giờ cấp 3 worker thay vì 5.

Con số "8 worker đạt 3,68×" vẫn đạt được: 8 worker cần `2 + 8×1,75 = 16 GB` trống, mà máy
31 GB lúc rảnh thì có. Pool chỉ thôi hứa điều đó khi bộ nhớ không có thật.

**Cần đo lại trên máy rảnh.** Lần đo này chạy song song với alpha.28, và số thứ ba đã bị
nhiễm. Cách đo: `scratchpad/worker_ram.py`.

## Pool từng tự chỉnh cỡ vào đúng vùng cấm chính nó

`usable_for()` chừa lại một hằng số **2,0 GB** cứng. `resources.min_free_ram_gb` là **3,5 GB**.
Và trong `AdaptiveResourceManager.decide()`, RAM trống ở hoặc dưới 3,5 GB là "memory
pressure", mà memory pressure tắt **cả hai**:

```python
allow_new_gpu_batch = not (foreground_gpu_pressure or memory_pressure or ...)
allow_cpu_heavy_work = not (foreground_cpu_pressure or ... or memory_pressure or ...)
```

Nên một pool chỉnh cỡ theo quy tắc cũ sẽ tiêu máy xuống còn 2,0 GB trống — tức **tự đặt
mình vào trạng thái cấm đúng loại việc nó sinh ra để làm**. Và từ khi chấm điểm chạy cạnh
ASR, hậu quả nặng hơn: `allow_new_gpu_batch` tắt theo, nên pool sẽ **làm nghẽn chính cái
ASR mà nó định nấp sau**.

Test `test_a_busy_machine_keeps_todays_behaviour_instead_of_stalling_asr` không bắt được
điều này, vì nó chỉ phủ quyết định **lúc khởi động**, không phủ trạng thái pool **tạo ra
sau khi đã chạy**.

Đã sửa: mức chừa lấy từ chính ngưỡng của van tiết lưu (`resources.min_free_ram_gb`), không
phải một con số do module này tự chọn. Với 7,3 GB trống: 2 worker, còn lại 3,8 GB — trên
ngưỡng. Một dự án nâng ngưỡng lên thì được pool nhỏ hơn, thay vì một pool cãi nhau với van
tiết lưu của chính nó.

Một test cũ vỡ vì việc này, và vỡ đúng: nó khẳng định 6 GB trống vẫn đủ cho hai worker —
điều chỉ đúng khi worker được tính 1,0 GB và mức chừa là 2,0. Ý định của test (nhiều chỗ
hơn thì nhiều worker hơn) giữ nguyên; con số sinh ra từ số học cũ thì bỏ.

## Cổng perceptual đòi tai người nghe nhiều hơn hẳn với đoạn ngắn (đo 2026-09-04)

`c00003_s0000014` — *"Tất cả đều đã ra đi."*, **1,5 giây** — chặn chương của nó ở **cả**
alpha.32 lẫn alpha.43, trong khi ASR nghe đúng từng chữ. Vài segment bị chặn khác cũng
ngắn. Đó là đủ dấu hiệu để hỏi cổng có thiên vị theo độ dài không.

Có, trên 2.282 phép chấm của alpha.32:

| độ dài | n | delta trung vị | **độ lệch chuẩn** | gắn cờ |
|---|---|---|---|---|
| <2s | 114 | −0,445 | **0,308** | **14,9%** |
| 2-3s | 395 | −0,389 | 0,276 | 8,4% |
| 3-5s | 502 | −0,386 | 0,247 | 2,2% |
| 5-8s | 490 | −0,388 | 0,209 | 1,0% |
| ≥8s | 781 | −0,397 | **0,189** | 1,8% |

**Trung vị phẳng** — từ −0,386 tới −0,445, không có xu hướng. Chỉ **độ tán** đổi, tăng 63%
khi đoạn ngắn lại. Nên đoạn ngắn *không phải điểm tệ hơn*; chúng **tán rộng hơn**, và một
ngưỡng tuyệt đối cố định thì hớt đúng cái đuôi ấy.

Hệ quả là chữ "tệ nhất" mang hai nghĩa khác nhau trong cùng một cổng: với đoạn dài nó nghĩa
là **1,5% dưới cùng**, với đoạn ngắn là **15% dưới cùng**.

### Nếu áp cùng một mức khắt khe thay vì cùng một con số

Trên đoạn ≥5s, −0,8 nằm ở *trung vị trừ 2,06 sigma*. Áp đúng 2,06 sigma ấy cho từng nhóm:

| độ dài | ngưỡng mới | gắn cờ nay → mới |
|---|---|---|
| <2s | −1,079 | 14,9% → **2,6%** |
| 2-3s | −0,958 | 8,4% → **0,8%** |
| 3-5s | −0,895 | 2,2% → 1,4% |
| 5-8s | −0,819 | 1,0% → 0,8% |
| ≥8s | −0,787 | 1,8% → **2,8%** |

Tổng: **80 → 39 lần gắn cờ.** Đọc cho đúng: đây **không phải nới lỏng**. Nó *siết* đoạn dài
(1,8% → 2,8%) và *nới* đoạn ngắn, để mức khắt khe như nhau ở mọi độ dài.

### Chưa phân giải được, và một phép thử rỗng

Phần tán thêm ở đoạn ngắn là **nhiễu của thước đo** hay là **chất lượng thật sự dao động
hơn**? Dữ liệu này không tách được, và điều đó quan trọng: nếu là cái sau thì cổng đang làm
đúng việc của nó.

Phép thử tự nhiên — so điểm giữa các bản thu **khác seed của cùng một câu** — trả về biên độ
**0,000 ở mọi nhóm**. Không phải vì thước đo ổn định, mà vì các hàng `quality_checks` lặp
lại đang chấm **đúng một file âm thanh**, không phải các bản thu khác nhau. Kết quả rỗng.
Ghi lại để người sau không thử lại đúng cách ấy; muốn phân giải thì phải **tự tổng hợp cùng
một câu ngắn nhiều lần với seed khác nhau rồi chấm**.

`scripts/perceptual_duration_bias.py` dựng lại toàn bộ bảng trên từ bất kỳ project nào.

### Đính chính ba con số của mục trên (2026-09-04)

Đọc kỹ các hàng `quality_checks` của một segment hỏng lặp lại (`c00003_s0000014`, 1,52s,
hỏng ở cả ba lần chạy) lôi ra hai lỗi trong cách tôi đo, và cả hai đều làm phóng đại kết quả.

**1. Candidate sửa làm lệch phân bố.** Phân bố ban đầu gộp cả phép chấm trên *bản thu chính*
lẫn trên *candidate sửa*. Candidate là bản thu lại của những segment vốn đã bị nghi ngờ, nên
chúng nằm thấp hơn hẳn: trung vị ở nhóm <2s là **−0,815** so với **−0,434** của bản thu
chính. Chỉ 4,7% mẫu, nhưng một cái cổng được hiệu chỉnh một phần bằng chính những bản nó đã
loại thì sai về hình dạng bất kể sai số to hay nhỏ.

Bỏ chúng ra, thiên vị vẫn còn nhưng **nhỏ hơn tôi đã báo**:

| độ dài | gắn cờ (có lẫn candidate) | gắn cờ (chỉ bản thu chính) |
|---|---|---|
| <2s | 14,9% | **9,9%** |
| ≥8s | 1,8% | 1,7% |

Tỉ lệ so với đoạn dài vì thế là **~6 lần**, không phải 8-15 lần. Ngưỡng <2s dịch từ −1,079
sang **−1,063**.

**2. Tôi lấy nhầm hàng kiểm.** Câu truy vấn cũ lấy phép chấm perceptual *mới nhất* của mỗi
segment. Nhưng một segment hỏng có nhiều hàng: bản thu chính mang mã chặn, rồi các candidate
sửa mang `PERCEPTUAL_SHORT_AUDIO` với `baseline_delta = null`. Lấy hàng mới nhất là lấy đúng
hàng *không* có số. `c00003_s0000014` vì thế **rơi khỏi** bảng của tôi hoàn toàn, và con số
"3 trong 6" là vô nghĩa.

Đếm đúng - lấy hàng mang mã chặn, dùng phân bố sạch:

    21/40 segment từng bị gắn cờ perceptual sẽ hết chặn

Những segment **vẫn** chặn phần lớn là đoạn **dài** (7,9s / 8,9s / 10,2s / 11,8s / 12,1s),
vì ngưỡng theo sigma **siết** đoạn dài lại (−0,786 thay vì −0,8). Đúng như đã nói: đây là
cân bằng lại, không phải nới lỏng.

**3. Kết luận quan trọng nhất thì không đổi: vẫn 0 chương được mở.** Chạy lại cổng xuất bản
với cách lấy hàng đã sửa cho ra đúng kết quả cũ - mọi chương bị chặn đều còn một segment
`failed` hoặc một segment perceptual vẫn chặn. Tôi đã đi tới kết luận đúng bằng một phép đo
sai, và điều đó không làm phép đo ấy đỡ sai đi.

## Tai người đã phán 14/14: đo được tỉ lệ báo động giả thật (2026-09-04)

Chủ sách nghe hết 14 đoạn bị chặn của alpha.44 và phán từng đoạn. Đây là **ground truth**
đầu tiên của dự án - trước giờ mọi con số đều là máy tự chấm máy.

| cổng | gắn cờ | đọc ĐÚNG | hỏng THẬT | báo động giả |
|---|---|---|---|---|
| `ASR_LOCKED_NAME_ANCHOR_MISMATCH` | 6 | **6** | 0 | **100%** |
| `PERCEPTUAL_NATURALNESS_REVIEW` | 6 | 5 | **1** | **83%** |
| `TTS_PACE_OUTLIER` | 1 | 0 | 1 | 0% |
| `SEGMENT_FAILED` (cổng nhịp) | 1 | 0 | 1 | 0% |

### Neo tên: 6/6 đều là báo động giả

Cả sáu đều đọc đúng. Chủ sách nhận xét ba lần, mỗi lần một đoạn khác nhau:

> *"đọc đúng từ, có vẻ máy nghe sai. có vẻ máy nghe phần tiếng anh convert tiếng việt không tốt"*
> *"những từ được convert từ tiếng anh sang âm tiếng việt thì tool nghe của bạn nghe không tốt"*

Điều này khẳng định lý do `ASR_LOCKED_NAME_ANCHOR_REVIEW` được miễn trừ ngay từ đầu, và
đặt câu hỏi vì sao `..._MISMATCH` lại **chặn**: trên quyển sách này, mọi lần nó chặn đều sai.
Whisper đơn giản là không nghe được tên tiếng Anh đã phiên âm sang âm Việt - đúng cái mà
`scripts/compare_asr_engines.py` đã đo (đổi engine không cứu được lớp này).

### Perceptual: 5 báo động giả cho 1 lần bắt đúng

`c00007_s0000045` bị chủ sách phán **"sai, bị đọc 2 lần"** - giọng đọc lặp nội dung hai lần.
Cổng perceptual bắt được nó. Năm đoạn còn lại đều ổn.

Nên cổng này **không vô dụng**: nó là thứ duy nhất bắt được một lỗi mà không cổng nào khác
thấy. Nhưng nó tốn 5 lần báo nhầm cho mỗi lần bắt đúng, và đó chính là mức giá mà mục
"ngưỡng theo sigma" đang định giảm.

### Cổng nhịp: 2/2 đều đúng

Cả hai ca đều là lỗi thật, và cùng một nguyên nhân: ký tự `»` lọt tới giọng đọc nên không
có chỗ ngắt nghỉ. Cổng nhịp phát hiện đúng triệu chứng của một lỗi nằm ở tầng văn bản.

## Câu hỏi mở của mục 5 đã trả lời được — bằng dữ liệu có sẵn, không cần GPU (06/09/2026)

`docs/OPTIMISATION_QUEUE.md` mục 5 đề xuất đổi ngưỡng perceptual từ số tuyệt đối
(`review_delta = -0.8`) sang **cùng một số sigma** cho từng nhóm độ dài, và để lại một câu
hỏi quyết định mục ấy đúng hay sai:

> phần tán thêm ở đoạn ngắn là **nhiễu thước đo** hay **chất lượng thật sự dao động hơn**?
> Cách đo: tự tổng hợp vài câu ngắn nhiều lần với seed khác nhau rồi chấm perceptual.
> Chưa chạy được vì cần GPU.

**Không cần tổng hợp gì cả.** Vòng sửa chữa đã làm đúng thí nghiệm ấy hàng trăm lần và lưu
kết quả: `segment_candidates` giữ `generation_seed`, `wav_duration` và `perceptual_result_json`
cho từng bản thu. Cùng một câu, cùng giọng, chỉ khác seed.

Gộp bốn lần chạy alpha.32/43/44/46, lấy những segment có **từ hai seed khác nhau trở lên**,
rồi **khử trùng lặp theo văn bản** (cùng một câu xuất hiện ở nhiều lần chạy chỉ tính một):

| độ dài | số câu | biên độ `baseline_delta` trung vị | lớn nhất |
|---|---|---|---|
| **< 4s** | 8 | **0,178** | **0,703** |
| **≥ 4s** | 3 | **0,047** | 0,304 |

Đoạn ngắn dao động **gấp ~3,8 lần** đoạn dài, trên đúng cùng một câu chữ.

### Vì sao con số 0,703 mới là điều đáng sợ

Câu `"Thương hại? Ta sao?"` dài 1,60s có `baseline_delta` **dịch 0,703 chỉ vì đổi seed**.
Ngưỡng gắn cờ là **−0,8**. Nghĩa là **88% toàn bộ ngưỡng có thể bị vượt bởi việc tung lại
xúc xắc**, trên một bản thu mà văn bản, giọng và mọi tham số đều y hệt.

Với một cổng dùng số tuyệt đối cho mọi độ dài, đó không phải là đo chất lượng nữa.

### Điều này KHÔNG phân biệt được, và đừng nói là có

Seed khác nhau tạo ra audio **thật sự khác nhau**, nên phép đo này không tách được:

- thước đo UTMOSv2 nhiễu hơn trên đoạn ngắn, hay
- bản thu ngắn thật sự dao động chất lượng nhiều hơn.

Cả hai đều dẫn tới cùng một kết luận cho mục 5 — ngưỡng tuyệt đối là sai với đoạn ngắn — nên
câu hỏi ấy không chặn quyết định. Nhưng đừng trích tài liệu này như bằng chứng "thước đo bị
nhiễu"; nó chỉ chứng minh **biến động giữa các lần thu của cùng một câu**.

### Giới hạn cỡ mẫu, nói thẳng

**8 câu ngắn và 3 câu dài.** Đó là tất cả những gì bốn lần chạy để lại có từ hai seed trở
lên, vì chỉ segment bị vòng sửa chữa đụng tới mới được thu lại — nên mẫu còn **thiên về
những câu vốn đã có vấn đề**. Hiệu ứng 3,8 lần đủ lớn để không phải ngẫu nhiên, nhưng con số
chính xác thì đừng tin quá ba chữ số.

Muốn chắc hơn thì vẫn là thí nghiệm cũ: tổng hợp một câu ngắn ~20 lần với 20 seed rồi chấm.
Chỉ khác là bây giờ ta đã biết nó sẽ cho ra cái gì.

## Cờ cảm thụ dẫn tới đâu? (đo 2026-09-06, alpha.43 → alpha.48)

Tài liệu này vẫn chỉ đo *giá*. Đây là nửa còn lại: khi nó lên tiếng, nó có đúng không?

| bản | bị cờ | thay bản thu | giữ nguyên | còn cảnh báo |
|---|---|---|---|---|
| alpha.43 | 44 | 35 | 0 | 9 |
| alpha.44 | 41 | 35 | 6 | 0 |
| alpha.46 | 37 | 32 | 0 | 5 |
| alpha.47 | 38 | 33 | 0 | 5 |
| alpha.48 | 20 | 17 | 0 | 3 |

**Điểm chấm là tất định.** 10 file được chấm lại trong cùng một lần chạy, **0 lần đổi phán
quyết**. Nên cờ không phải nhiễu — giả thuyết đầu tiên của tôi, và nó sai. (Con số lệch
0,208 đo trước đây là giữa `num_repetitions` 1 và 3, không phải giữa hai lần chạy cùng cấu
hình.)

Vậy 84% cờ dẫn tới một bản thu **khác thật**, và bản mới chấm đạt. Đó là một lời khẳng định
rằng phép kiểm tra đáng đồng tiền — và **chưa lời nào từng được kiểm chứng bằng tai**.

Bằng chứng người thật, tất cả những gì có: **22 cờ đi hết vòng sửa mà vẫn còn cảnh báo, 10
cái tới được tai chủ sách, cả 10 đều được chấp nhận là đọc đúng.** Không một cờ nào từng
được người xác nhận là bắt đúng lỗi. Nhưng đó là mẫu thiên lệch — chúng đúng là những ca
vòng sửa chịu thua.

**Thí nghiệm làm được, và không thiếu vật liệu.** Sổ cái `segment_candidates` ghi mọi lần
sửa vì cảm thụ: `candidate_repair_requirement='naturalness_improvement_v1'`, `state='promoted'`,
với `incumbent_sha256` là bản bị loại và `wav_sha256` là bản được đưa lên thay. **Cả hai bản
đều còn trên đĩa, 30/30 ở alpha.47.** Tổng cộng 140 cặp trên năm bản.

> **Sửa lại một khẳng định sai của chính tài liệu này.** Bản trước ghi "chỉ còn 13 cặp" và
> "~90% bằng chứng đã bị xoá". Cả hai đều sai, và cùng một nguyên nhân: tôi dựng đường dẫn
> thư mục candidate từ `seq` của segment, trong khi thư mục được đặt tên theo `segment_id`.
> Hai số ấy trùng nhau đủ thường xuyên để không lộ ra ngay. Không có bằng chứng nào bị xoá
> cả. Bài học: `segment_candidates` có sẵn checksum của cả hai bản — **tra theo checksum,
> đừng đoán đường dẫn**, và kiểm lại chiều của mỗi cặp (bản bị loại phải có phán quyết
> `review`, bản giữ phải `ok`) trước khi đưa cho ai nghe.

Cách đo lại: `scratchpad/perceptual_outcomes.py`, `same_audio_two_verdicts.py`,
`how_flags_clear.py`, `perceptual_pairs2.py`.

---

## Kết quả: phép kiểm cảm thụ không có tín hiệu đo được (2026-09-07)

Thí nghiệm mà tài liệu này hẹn ở trên đã chạy xong. **Mười cặp to nhất, nghe mù, chủ sách
chấm.**

Cách dựng: `scripts/build_perceptual_ab_page.py` lấy mười lần loại có `drop` lớn nhất trong
năm bản (0.974–1.208, trên ngưỡng 0.8), ghép mỗi cặp thành A/B, **xáo ngẫu nhiên chiều** rồi
cất khoá giải mã sang `_versions/_listening/perceptual_ab_key.json`. Chủ sách nghe mà không
biết bên nào là bản máy đã loại, và trả lời được phép chọn "=" khi không phân biệt được.

Đáp án: `1:B 2:A 3:A 4:= 5:= 6:A 7:B 8:A 9:= 10:B`

| kết cục | số cặp |
|---|---|
| máy loại đúng bản dở hơn | **4/10** |
| máy loại **nhầm bản hay hơn** | **3/10** |
| chủ sách không phân biệt được | **3/10** |

**Đọc cho đúng: đây không phải "máy chấm ngược", mà là "máy không có tín hiệu".** Bốn đúng
ba sai trên bảy cặp phân biệt được là đúng bằng tung đồng xu — P(≥4 trong 7) = 0,50 chẵn.
Ba cặp còn lại chủ sách nghe hai lần không thấy khác nhau, dù máy chấm chúng lệch tới
1,038 / 1,035 / 0,979.

Và cần nhớ đây là **mười lời chê to nhất** phép kiểm từng đưa ra. Nếu có tín hiệu ở đâu thì
phải là ở đây. Không có.

> **Sửa một con số tôi đã nói sai trong phiên này.** Lần đầu tôi báo "3 đúng / 4 ngược" —
> tôi đảo hai cột khi so `rejected_is` với câu trả lời. Số đúng là 4/3/3. Kết luận không đổi
> về bản chất (vẫn là ngang đồng xu), nhưng con số thì phải đúng.

### Cái giá đã trả cho chỗ không có tín hiệu này

- Là khoản tốn lớn nhất ngoài TTS trong mỗi lượt chạy.
- Đã loại và cắt lại khoảng 150 bản thu qua năm phiên bản.
- Mỗi lần cắt lại là thêm một vòng TTS **và** một vòng ASR xác minh.

### Việc phải quyết

Đây là quyết định của chủ sách, không phải của tôi, nên chỉ ghi lựa chọn:

1. **Tắt hẳn** — lấy lại toàn bộ thời gian đó, chấp nhận mất một phép kiểm chưa chứng minh
   được là mình có tác dụng.
2. **Nâng ngưỡng rất cao** — chỉ giữ lại những ca cực đoan hơn cả mười ca này. Nhưng mười ca
   này *đã là* cực đoan nhất, nên gần như chắc chắn tương đương với tắt hẳn.
3. **Giữ nguyên** — trả giá đã biết để đổi lấy lợi ích chưa đo được.

Chưa có bằng chứng nào ủng hộ (3). Muốn cứu phép kiểm này thì phải có một thí nghiệm mù
thứ hai cho thấy nó ăn đứt đồng xu — mà lần thử tốt nhất vừa rồi thì không.

n = 10, và đó là hạn của kết luận này: nó không chứng minh phép kiểm *vô dụng*, nó chỉ nói
rằng ở chỗ đáng ra phải rõ nhất, **không đo được tác dụng nào**.

Khoá giải mã và câu trả lời: `_versions/_listening/perceptual_ab_key.json`,
`scratchpad/ab_decoded.json`.
