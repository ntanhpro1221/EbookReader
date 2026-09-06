# Một lần chạy tiêu thời gian vào đâu

Đo trên alpha.25 (10 chương, 948 segment, 5.100 giây tổng). `quality_checks` không có cột
thời lượng, nên thời gian được quy theo đúng cách một pipeline tuần tự tiêu nó: mỗi khoảng
trống giữa hai check liên tiếp trong cùng một chương thuộc về giai đoạn của check sau.
Khoảng trống trên 600 giây bị loại vì đó là lúc nghỉ giữa các pha, không phải công việc.

## Bảng

| giai đoạn | lượt | giây | phần |
|---|---:|---:|---:|
| `segment_asr_decode_v1` | 2.032 | **3.870,4** | **60%** |
| `segment_perceptual_v1` | 979 | 2.537,9 | 39% |
| `chapter_post_encode_v1` | 10 | 50,1 | 1% |
| `segment_audio_v1` | 1.074 | 31,8 | 0% |

## Điều bất ngờ: ASR đắt hơn TTS

Cả dự án vẫn ngầm coi TTS là phần đắt nhất. Không phải. **Whisper tốn 3.870 giây, còn TTS
tốn 2.055 giây** — ASR gần gấp đôi TTS và là khoản lớn nhất của một lần chạy.

2.032 lượt giải mã cho 948 segment, tức 2,14 lượt mỗi segment. Đây **không** phải lãng phí:
lượt xác nhận chỉ chạy khi lượt đầu cho verdict MISMATCH hoặc INCONCLUSIVE
(`pipeline.py`, `verify_rows(..., confirmation=True)`), và các vòng sửa chữa thì đương nhiên
phải giải mã lại bản thu mới. Đã kiểm tra trước khi kết luận.

Đòn bẩy còn lại của ASR là `beam_size = 5` ở lượt chính (lượt xác nhận mới là greedy). Đảo
lại - greedy trước, beam khi nghi ngờ - có thể cắt lớn, nhưng nó đổi cả tập segment được
cho qua, nên đó là thay đổi ảnh hưởng chất lượng và phải đo, không phải khoản lấy không.

## Khoản lấy không: chồng lấn cảm thụ với ASR

Chấm điểm cảm thụ là **đọc thuần túy** - vào một file WAV, ra một con số - và chạy trên
**CPU**. Whisper chạy trên **GPU**. File WAV đã có từ lúc TTS xong, tức là trước khi Whisper
bắt đầu. Nhưng hiện tại chúng xếp nối tiếp: ASR xong hết chương mới tới chấm cảm thụ.

Trong **chín trên mười chương, thời gian ASR dài hơn thời gian cảm thụ**, nên toàn bộ phần
chấm điểm lọt được vào trong đó:

| chương | ASR (GPU) | cảm thụ (CPU) | lấy được |
|---|---:|---:|---:|
| 1 | 1,2s | 51,7s | 1,2s |
| 2 | 811,4s | 308,2s | 308,2s |
| 3 | 422,9s | 334,9s | 334,9s |
| 4 | 327,3s | 305,1s | 305,1s |
| 5 | 349,5s | 307,8s | 307,8s |
| 6 | 246,0s | 209,4s | 209,4s |
| 7 | 394,8s | 189,1s | 189,1s |
| 8 | 643,2s | 355,7s | 355,7s |
| 9 | 341,6s | 254,4s | 254,4s |
| 10 | 332,5s | 221,8s | 221,8s |
| **tổng** | | | **2.507,4s** |

Chương 1 là ngoại lệ vì đó là lần nạp model UTMOSv2 duy nhất (25,7s cho một check).

**Khoảng 42 phút mỗi lần chạy, không đổi một quyết định chất lượng nào**, vì các verdict
vẫn chạy trong tiến trình chính, theo đúng thứ tự cũ, với đúng ngưỡng cũ. Chỉ có việc chấm
điểm dời sớm lên.

## Cái bẫy phải tránh khi làm

Vòng sửa chữa của ASR **thu lại** segment, nên WAV đổi. Một điểm số chấm trước lúc sửa là
điểm của bản thu cũ. Hiện tại code không dính bẫy này chỉ vì prefetch xảy ra *sau* ASR;
dời nó lên trước thì bẫy mở ra. `prefetched_scores` đang khoá theo `wav_path`, mà đường dẫn
không đổi khi thu lại - **phải khoá theo `wav_sha256`** và bỏ mọi điểm có sha đã khác. Segment
bị sửa sẽ tự chấm trong tiến trình chính, đúng như đường đã có sẵn cho các file mà pool
không trả về.

Cách đo lại: `scratchpad/asr_vs_qa.py`. Lưu ý: check theo segment để `chapter_id` NULL và chỉ
ghi `segment_id`, nên phải nối qua bảng `segments`; và `created_at` là **float unix**, không
phải chuỗi ISO như tên cột gợi ý.

## Beam search: đo rồi, và nó không chỉ đắt - ở câu ngắn nó còn sai (2026-09-03)

Lượt giải mã chính dùng `beam_size = 5`; lượt xác nhận dùng greedy. Câu hỏi đặt ra không
phải "greedy nhanh hơn bao nhiêu" (hiển nhiên là nhanh hơn) mà **"hai lối có bất đồng về
bản thu nào chấp nhận được không"** - vì một lượt giải mã cho lọt bản tồi hoặc đánh trượt
bản tốt sẽ tốn một lần thu lại, xoá sạch phần tiết kiệm gấp nhiều lần.

Đo bằng `scripts/measure_beam_vs_greedy.py` trên chính WAV của alpha.25, cùng văn bản mong
đợi, qua đúng `verify()` mà pipeline dùng.

### 160 bản thu mọi độ dài

beam chậm hơn **1,84 lần** (0,92s so với 0,50s mỗi segment). Bất đồng đỗ/trượt 3/160.

| văn bản mong đợi | beam | greedy | ai đúng |
|---|---|---|---|
| "Hờ." | *"Hãy subscribe cho kênh Để không bỏ lỡ những video hấp dẫn"* | "Họ" | greedy |
| "tôi" | "Đôi." | "Tôi..." | greedy |
| câu dài về Rồng | nghe ra "rồng" | nghe ra "dòng" | **beam** |

### 120 bản thu ngắn hơn 2,5 giây

beam chậm hơn **1,47 lần**. Bảy bất đồng verdict, ba lần lật đỗ/trượt - **cả ba đều nghiêng
về greedy, không một ca nào beam thắng.** Thêm một ca nữa: tiếng thở dài "Haaa." được beam
đọc thành "Ah yeah.".

### Cơ chế, không phải trùng hợp

Beam mang nhiều giả thuyết rồi giữ chuỗi xác suất cao nhất. Với audio ít nội dung, **chuỗi
xác suất cao nhất là câu mẫu** - và câu mẫu của Whisper là câu mẫu YouTube. Đây là chế độ
hỏng đã được biết đến của Whisper, và phép đo tái hiện nó đúng như dự đoán.

### Đã làm

`beam_minimum_seconds = 2.5`: lượt chính dùng beam khi bản thu dài hơn ngưỡng, dùng greedy
khi ngắn hơn. Giữ tìm kiếm ở nơi có nội dung nuôi nó, bỏ ở nơi nó tự bịa nội dung. Nhanh
hơn là lý do nhỏ hơn; **đúng hơn mới là lý do chính**.

Lượt xác nhận vẫn greedy ở mọi độ dài - nó tồn tại để đưa ra một ý kiến *khác*, không phải
một ý kiến *dài hơn*.

### So hai lần chạy thì không kết luận được về bộ giải mã (alpha.32 vs alpha.25)

Chương 2, 77 segment, chỉ lượt giải mã đầu tiên (không xác nhận, không vòng sửa):

| | đỗ | lệch | không kết luận |
|---|---|---|---|
| alpha.25 (beam mọi độ dài) | 47 (61%) | 29 (38%) | 1 (1%) |
| alpha.32 (greedy dưới 2,5s) | 44 (57%) | 31 (40%) | 2 (3%) |

Thoạt nhìn tưởng thay đổi beam làm tệ đi. Xem từng ca thì **không ca nào chống lại greedy**:

- `c00002_s0000037` (2,48s): alpha.32 có similarity **cao hơn** (0,833 so với 0,800) nhưng
  vẫn trượt, vì trượt ở **neo tên khoá** chứ không ở similarity. Giọng đọc chữ "Rare" khác
  nhau giữa hai lần thu - alpha.25 nghe ra "ra", alpha.32 nghe ra "Gai".
- `c00002_s0000042` (**12,80s**): trên ngưỡng, nên **beam ở cả hai lần chạy**. Không thể do
  thay đổi này.
- `c00002_s0000067` (0,48s): văn bản chỉ là một chữ **"S"**. Cả hai đều cho ra vô nghĩa;
  alpha.25 ra "ừ ừ" và lọt qua, alpha.32 ảo giác một câu dài. Đây là lớp
  `ASR_UNVERIFIABLE_SHORT_TEXT` đã biết, không phải chuyện beam.

**Bài học về phương pháp:** alpha.32 thu lại toàn bộ âm thanh với seed và casting riêng, nên
đây là hai *tập bản thu* khác nhau chứ không phải hai *bộ giải mã* trên cùng bản thu. Một
so sánh giữa hai lần chạy không tách được bộ giải mã khỏi giọng đọc. Bằng chứng có kiểm
soát - 120 bản thu **giống hệt**, ba lần lật verdict, cả ba nghiêng về greedy - vẫn là bằng
chứng tốt hơn hẳn, và nó không mâu thuẫn với bảng trên.

## Chồng lấn cảm thụ với ASR: đo trên lần chạy thật (alpha.32, 2026-09-03)

Thời gian cảm thụ **còn nằm trên dòng thời gian tuần tự** (tức phần chưa nấp được sau ASR):

| chương | alpha.25 | alpha.32 | số worker chồng lấn |
|---|---:|---:|---|
| 4 | 305,1s | **77,7s** | 8 |
| 5 | 307,8s | **57,0s** | 8 |
| 6 | 209,4s | **39,0s** | 8 |
| 2 | 308,2s | 270,7s | chỉ 2 (RAM thiếu) |
| 3 | 334,9s | **995,3s** | **bỏ qua** (5,1 GB trống) |
| 1 | 51,7s | 31,6s | 2 (chương 2 segment) |

**Ba chương chạy đủ 8 worker: 822,3s → 173,7s, giảm 79%.** Chiếu ra mười chương thì vào
khoảng 2.000 trên 2.538 giây - gần bằng dự đoán ban đầu.

ASR thì đứng yên (có chương tăng, có chương giảm, không lệch hệ thống), đúng dấu hiệu cần
thấy: **chồng lấn không lấn sang thời gian của cái nó nấp sau.**

### Ba chương còn lại giải thích hết phần còn lại của bảng

- **Chương 2 chỉ giảm 12%** vì pool chỉ được 2 worker: lúc ấy máy còn 8,4 GB trống, mà
  ngân sách 1,75 GB/worker trên nền `min_free_ram_gb` cho ra `(8,4−3,5)/1,75 = 2`. Đúng
  công thức, chỉ là máy chật.
- **Chương 3 tệ gấp ba** vì chồng lấn **bị bỏ qua hoàn toàn** (5,1 GB trống, không đủ cho
  hai tiến trình - và nó **ghi rõ lý do** vào log, đúng chỗ mà trước đây nó im lặng), cộng
  bốn lần sửa naturalness phải chấm lại trong tiến trình chính.
- **Chương 1 chỉ có 2 segment**, và 31,6s còn lại gần như toàn bộ là lần nạp model UTMOSv2
  duy nhất trong tiến trình chính.

### Điều đáng ghi cho người sau

Khoản tiết kiệm **phụ thuộc trực tiếp vào RAM trống** khi chương bắt đầu ASR, và nó phụ
thuộc theo bậc: 8 worker giảm ~79%, 2 worker giảm ~12%, 0 worker thì không giảm gì. Trên
máy này ranh giới là khoảng 17 GB trống cho đủ 8 worker, 7 GB cho 2. Đó không phải khuyết
điểm của thiết kế - đó là nó từ chối hứa phần bộ nhớ không có thật, đúng bài học đã trả giá
bằng alpha.26.

## Một con số viết hai cách từng làm hỏng cả chương (alpha.32, 2026-09-03)

Chương 6 của alpha.32 bị từ chối vì một segment:

```
văn bản : "Hôm nay là ngày 24 tháng Mười hai."
nghe ra : "Hôm nay là ngày 24 tháng 12."
```

**Giọng đọc đúng từng chữ.** Whisper viết chữ số ở chỗ sách viết chữ, và `_fold_number_digits`
chỉ có bảng **mười một mục** (0–10), nên "mười hai" so với "12" bị tính là sai. Cùng lỗ hổng
ấy biến "thứ Mười" thành gần-lệch và "bốn mươi mốt" thành lệch hẳn.

`vietnamese_number_words()` đã tồn tại và đọc được tới 999, kể cả những dạng mà một cái bảng
làm sai — "hai mươi mốt" chứ không "hai mươi một", "mười lăm" chứ không "mười năm". Giờ
`normalize_transcript` gọi nó thay vì giữ một câu trả lời thứ hai, ngắn hơn, cho cùng câu hỏi.

Đo trên chính các segment bị đánh dấu của alpha.32: **27/39 tăng similarity.** Hai segment
chặn chương 6:

| segment | trước | sau |
|---|---:|---:|
| `c00006_s0000089` ("tháng Mười hai") | 0,833 | **0,932** |
| `c00006_s0000021` ("bốn mươi mốt") | 0,902 | **0,956** |

Ba segment hỏng còn lại **không đổi** — chúng thuộc lớp "ngoặc tiếng Anh", một vấn đề khác.

Giữ nguyên hai giới hạn có chủ đích: trên 999 thì không gộp (một năm không có dạng đọc cố
định để gộp về, và gộp bừa sẽ khiến hai thứ khác nhau so bằng nhau), và số có số 0 đứng đầu
thì không gộp — "007" là một cái tên viết bằng chữ số, không phải một phép đếm.

### Tôi đã kết luận sai một nhịp trước

Nhịp trước tôi viết rằng các segment `failed` "có phần nội dung ngoài tên **cũng** bị nghe
sai", dựa trên canonical CER 0,235–0,333. Đọc bản ghi thật thì **phần tiếng Việt được phiên
âm hoàn hảo**; CER cao vì chính cái chữ số viết hai cách này, cộng phần vô nghĩa mà cụm
tiếng Anh để lại. Chỉ số thống kê đúng, cách đọc nó của tôi thì sai. Bài học: đọc bản ghi
trước khi kết luận về nó.

## Máy rảnh mà lần chạy không vắt kiệt: GPU 16% suốt pha đắt nhất (đo 2026-09-03)

Lấy mẫu 12 lần trong 24 giây, giữa pha ASR của alpha.32, trên máy đã rảnh:

```
16, 1437     16, 1437     0, 1433      16, 1435
0, 1531      16, 1433     14, 1435     15, 1431
16, 1435     16, 1435     16, 1541     16, 1437
       (utilization.gpu %, memory.used MiB)
```

**GPU ghim ở 14–16%, VRAM dùng 1,43 trên 8,15 GB.** Trong pha chiếm 60% thời gian của một
lần chạy, GPU **rảnh 87%** và **82% VRAM để không**. Whisper giải mã một file một lần.

Đó là câu trả lời cho "nó có vắt kiệt tài nguyên không": **không**, và chỗ không vắt kiệt
nằm đúng ở khoản đắt nhất.

## faster-whisper: nhanh 2,07 lần, nghe giống hệt

Cùng trọng số `large-v3-turbo`, khác runtime (CTranslate2 thay vì PyTorch). Cùng bản thu,
cùng văn bản mong đợi (dựng lại bằng `spoken_text_with_anchors`), cùng luật beam theo độ
dài, chấm qua cùng một ngưỡng.

| mẫu | openai-whisper | faster-whisper | bất đồng đỗ/trượt |
|---|---:|---:|---|
| 60 bản thu | 1,18s/bản | 0,70s/bản | **0/60** |
| **200 bản thu** | **0,77s/bản** | **0,37s/bản** | **0/200** |

200 mẫu: 196 đỗ/đỗ, 4 trượt/trượt. **Không một verdict nào khác nhau.** Trên 3.870 giây ASR
của alpha.25 thì 2,07× là khoảng **2.000 giây mỗi lần chạy**.

Giới hạn của bằng chứng, nói cho đúng: 200 bản thu từ **một** cuốn sách, một giọng, tiếng
Việt. Không bất đồng là dấu hiệu mạnh, không phải chứng minh cho cả 948 segment.

### Đổi sang nó là một sự kiện phiên bản

`docs/DEPENDENCIES.md` viết: *"Upgrading any pinned dependency changes the quality-policy
hash and therefore requires a clean project."* Thêm `faster-whisper` + `ctranslate2` là
đúng loại thay đổi đó. Không có ghi chép nào nói openai-whisper được **chọn** thay nó — nó
chỉ là thứ đã được ghim.

Một chi tiết cài đặt phải ghi lại: **CTranslate2 liên kết cuBLAS và cuDNN lúc nạp và không
kèm chúng.** torch thì có, trong `torch/lib`. Trong venv scratchpad tôi phải chép
`cublas64_12.dll`, `cublasLt64_12.dll` và `cudnn*64_9.dll` sang cạnh `ctranslate2`. Trên
venv chính thì torch đã ở đó, nhưng đây là thứ sẽ hỏng trên máy mới nếu không biết trước.
`os.add_dll_directory` **không** đủ, và PATH kiểu POSIX của Git Bash cũng không.

### Hai đòn bẩy này cộng được với nhau

2,07× là đổi runtime, **chưa** chạm tới chỗ GPU rảnh 87%. faster-whisper có
`BatchedInferencePipeline` cho phép giải mã nhiều file một lượt, tức đúng thứ để lấp phần
rảnh ấy. Làm cả hai thì ASR có thể xuống dưới một phần tư thời gian hiện tại — nhưng đó là
phép đo tiếp theo, không phải một con số để hứa bây giờ.

## Vì sao hai chương vẫn hỏng: một phép đo tự mâu thuẫn (chẩn đoán 2026-09-03, CHƯA sửa)

Sau khi `retry` + `resume` với bản sửa gộp số, alpha.32 vẫn hỏng chương 2 và 3 vì đúng hai
segment cũ. Nhưng lần này chẩn đoán đi tới tận gốc, và gốc **không phải** chính sách.

```
văn bản : Hắn là Hoàng Tử Quỷ Thứ Mười (Tenth Demon Prince).
nghe ra : Hắn là hoàng tử quỷ thứ 10, tên Demon Prince.
```

Phần tiếng Việt **hoàn hảo** ("thứ 10" giờ đã gộp về "thứ mười"), và Whisper còn viết đúng
chính tả tiếng Anh gốc. Vậy mà:

| | canonical WER (≤0,30) | canonical similarity (≥0,78) |
|---|---|---|
| `Spirit Essence Units` | 0,222 ✓ | **0,765 ✗** |
| `Tenth Demon Prince` | 0,250 ✓ | **0,667 ✗** |

Hai chỉ số cùng đo "nội dung ngoài tên" mà nói ngược nhau. Lý do nằm trong
`_minimum_cost_locked_name_alignment`: nhánh `substitute_anchor` chuyển
`(unit+1, transcript_index+1)` — **tiêu đúng một token** — trong khi `match_anchor` tiêu
`len(form_tokens)`. Một cái tên nhiều chữ bị nghe khác chiếm nhiều token ("tên demon prince"
= 3); một token thành neo, **hai token còn lại bị tính vào nội dung thường**. Nên một câu
đọc đúng hoàn toàn trượt canonical similarity **vì cái tên của nó trượt**. WER thoát vì nó
chuẩn hoá theo độ dài; similarity ở mức ký tự thì không.

### Bản sửa hiển nhiên là sai, và một test cũ đã chứng minh

Cho `substitute_anchor` tiêu đúng số token nó được nghe thành (rộng tới 1..N theo dạng dài
nhất của neo, cùng chi phí). Nó đưa cả hai ca lên `review_eligible` — tức
`ASR_LOCKED_NAME_ANCHOR_REVIEW`, cảnh báo **được phép xuất bản**.

Nhưng `test_clarity_final_gate_preserves_anchor_failure_from_either_decode` vỡ, và nó vỡ
**đúng**. Kịch bản của nó: bản ghi *"Anh Lucien nói sai phần còn lại"* cho văn bản
*"Anh Lu-si-en đã đến"* — nội dung thường **cũng sai**. Với bản sửa, neo hút luôn ba token
sai đó và `ASR_MISMATCH` biến mất.

Tôi đã lập luận rằng phần thưởng cho khớp chính xác `(0,-1,0,0)` sẽ ngăn việc hút bừa. Lập
luận ấy **thiếu**: nó chỉ bảo vệ nội dung **đúng**. Khi xung quanh cũng sai thì không có
khớp nào để mất, và việc hút là miễn phí.

**Đã hoàn nguyên.** Vấn đề là thật và đã được mô tả chính xác, nhưng ràng buộc đúng thì tôi
chưa có, và đây là lõi của phép so sánh bảo vệ 900 segment còn lại.

### Hướng cho lần sau

Câu hỏi phải trả lời: *token bản ghi nào thuộc về cái tên?* Vài ý, chưa cái nào được đo:

- Giới hạn bề rộng bằng số token của **dạng neo**, và chỉ hút khi các token bị hút **không
  khớp** bất kỳ token thường nào đang chờ — tức phân biệt "rác của tên" với "nội dung sai".
- Tính chi phí theo bề rộng để việc hút không còn miễn phí, rồi đo lại trên cả hai ca.
- Hoặc bỏ hẳn hướng gióng hàng: nếu `canonical_wer` đạt mà `canonical_similarity` trượt
  **và** neo không khớp, thì chính sự chênh lệch ấy là dấu hiệu rác-của-tên đang bị tính
  hai lần. Cần đo trên corpus để biết nó có phân biệt được hay không.

### Và một kết quả âm quan trọng

faster-whisper nghe **y hệt** trên đúng hai bản thu này: `S.P.Z.E.S.N.U.N.D.` và
`tên Demon Perrin`. **Engine tốt hơn không sửa được lớp này.** Vấn đề không phải chất lượng
bộ phiên âm mà là một cụm tiếng Anh phiên sang âm Việt không có bản ghi ổn định ở bất kỳ
engine nào. Nên 2,07× vẫn đáng đổi vì tốc độ, nhưng đừng mong nó gỡ được các chương này.

### Dữ liệu cho lần thử sau: phân bố canonical trên 46 ca neo thật

`scripts/replay_anchor_alignment.py` chạy trên alpha.25 + alpha.32. Chỉ các ca **neo không
khớp** (các ca neo khớp không đi qua nhánh này):

| segment | canonical sim | canonical wer | trạng thái | |
|---|---:|---:|---|---|
| `c00010_s0000016` | 0,526 | **0,600** | fail | WER cũng trượt |
| `c00007_s0000074` | 0,556 | 0,167 | fail | **WER đạt / sim trượt** |
| `c00002_s0000062` | 0,618 | **0,444** | fail | WER cũng trượt |
| `c00003_s0000029` | 0,667 | 0,250 | fail | **WER đạt / sim trượt** |
| `c00006_s0000024` | **0,770** | 0,172 | fail | **WER đạt / sim trượt**, trượt đúng 0,01 |
| `c00002_s0000034` | 0,810 | 0,172 | review_eligible | |
| … 37 ca còn lại | 0,812 – 1,000 | 0,000 – 0,225 | review_eligible | |

Tổng: **38 review_eligible / 8 fail** (có trùng stable_id giữa hai lần chạy vì cùng segment
hỏng ở cả hai).

**Điều dữ liệu nói:**

- Dạng "WER đạt mà sim trượt" phủ **5 trên 8** ca hỏng. Đó là chữ ký của rác-tên bị tính
  hai lần: rác của một cái tên là **nhiều ký tự nhưng ít token**, nên nó đánh vào similarity
  mức ký tự mạnh hơn hẳn WER mức token.
- Hai ca hỏng cả WER (`Tai Ương Bình Minh` nghe thành "Tài hương bình mình", và
  `Spirit Essence Units` trên bản thu của alpha.25) **phải ở lại hỏng** — nội dung thường
  của chúng thật sự sai.
- Nhưng `c00006_s0000024` trượt đúng **0,01**. Nên **không có khoảng trống sạch** giữa hai
  lớp; ngưỡng 0,78 đang làm việc trên lưỡi dao. Nhìn riêng alpha.25 thì tưởng có (0,667 →
  0,810), thêm alpha.32 vào thì hết.

**Chưa ship gì.** Tám điểm là quá mỏng để dựng một luật, và một luật sai ở đây cho qua một
lần đọc sai thật. Nhưng dữ liệu giờ đã có, bộ đo dùng lại được, và lần thử sau đo được ngay
bằng một câu: *fail có giảm dưới 8 mà dòng chốt vẫn nguyên không?*

## Ba segment không có audio: hai giả thiết của tôi đều sai, và cái đúng là một xung đột tự gây

alpha.32 kết thúc `completed_with_errors`, 3/10 chương (alpha.25: 2/10). Trong 13 chỗ chặn
xuất bản, **ba segment chưa từng có audio** — thu 5 đến 15 lần, không lần nào được commit:

```
high-quality TTS retry required: speech pace 12.25 chars/s;
split=segment too short to split safely
```

| segment | pace đo được | văn bản |
|---|---:|---|
| `c00005_s0000013` | 12,25 | Tên tôi là **Samael Kaizer Theosbane**. |
| `c00010_s0000017` | 12,13 | Ông ta chính là cha tôi, **Arthur Kaizer Theosbane**. |
| `c00009_s0000008` | 9,36 | Cấp Linh Hồn … **C » B » A » S » SS » SSS** |

Cả ba đều **quá chậm** so với cận dưới 12,5 của nhịp `normal`.

### Giả thiết 1: đo sai đơn vị — SAI

Tôi nghĩ cổng đếm **ký tự** trong khi giọng tốn thời gian theo **âm tiết**, và tên chuyển tự
có tỉ lệ âm-tiết-trên-ký-tự cao bất thường ("Thê-ô-xờ-ben": 4 âm tiết / 10 ký tự, so với
tiếng Việt thường ~1 âm tiết / 5 ký tự). Đo trên 350 segment lành mạnh: hệ số biến thiên
của ký-tự/s là **0,085**, của âm-tiết/s là **0,080**. Gần như nhau. Đổi đơn vị không mua
được gì.

### Giả thiết 2: cận dưới đặt sai — SAI

Lần đo đầu cho p5 = 11,43 ký tự/s, thấp hơn cận 12,5, nghe như cận đặt quá cao. Nhưng tôi
đã chia cho **thời lượng thô** trong khi cổng chia cho **thời gian nói đã trừ khoảng lặng**.
Tính đúng như cổng tính, trên 807 segment `normal` đã đạt:

| | |
|---|---|
| trung vị | 15,82 |
| p5 | **13,69** |
| dưới cận 12,5 | **0 (0,0%)** |
| trên cận 24,5 | 0 (0,0%) |

**Cận đặt đúng.** Ba ca hỏng thật sự chậm hơn *mọi* bản thu trong 807 bản được chấp nhận.

### Cái đúng: dự án tự đánh nhau

Bản thu **thật sự chậm**, và nó chậm vì đúng thứ dự án tự tạo ra: chính dự án biến
"Samael Kaizer Theosbane" thành "Xa-ma-eo Cai-dơ Thê-ô-xờ-ben", giọng đọc từng âm tiết có
gạch nối một cách chậm rãi, rồi **cổng nhịp từ chối kết quả**. Hai trong ba ca là câu có tên
chuyển tự; ca thứ ba là một chuỗi chữ cái đánh vần, cùng cơ chế ở dạng cực đoan.

Cổng không phân biệt được "chậm vì tên khó" với "chậm vì model lê thê", và với ba câu này
thì không có đường ra: quá ngắn để chia, hết lượt thu, **không có audio nào cả**. Sách thiếu
ba câu.

Đây là ranh giới giữa hai tính năng của cùng một dự án, không phải lỗi của bên nào. Cần đo
thêm trước khi sửa: một segment mang tên chuyển tự có **hệ thống** chậm hơn không, hay ba ca
này chỉ là đuôi phân bố? n=3 thì chưa trả lời được.

## Vì sao không dùng số tổng của alpha.32 để đo chồng lấn

alpha.32 chạy hết, nhưng tôi đã bắt nó **xác minh lại cả sách ba lần** (mỗi lần sửa
`pipeline.py`/`database.py` là một lần đổi policy hash). Hậu quả trên số liệu:

| | alpha.25 | alpha.32 |
|---|---:|---:|
| lượt giải mã ASR | 2.032 | **4.918** |
| lượt chấm cảm thụ | 979 | **2.513** |

Nên **mọi con số tổng đều không so được**. Tính theo mỗi lượt:

| | alpha.25 | alpha.32 |
|---|---:|---:|
| cảm thụ | 2,59 s/lượt | **0,85 s/lượt** |
| ASR | 1,90 s/lượt | 2,50 s/lượt |

Cảm thụ giảm **3,05×** — phù hợp với chồng lấn. Nhưng ASR **tăng 0,60 s/lượt**, và tôi
**không tách được** hai cách giải thích:

- pool chấm điểm tranh CPU với Whisper (tức chồng lấn có lấy sang thời gian của ASR), hay
- các lượt xác minh lại giải mã đi giải mã lại đúng những segment khó nhất, nên trung bình
  mỗi lượt nặng hơn — 5,2 lượt/segment so với 2,14 của alpha.25.

Cách thứ hai đủ sức giải thích toàn bộ, và dữ liệu này không phân biệt được.

**Bằng chứng tốt hơn vẫn là phép đo sạch trước đó**: ba chương chạy đủ 8 worker trong
alpha.32 khi chưa có lượt xác minh lại nào, 822,3s → 173,7s (giảm 79%), ASR đứng yên. Ghi
lại điều này để người sau không trích nhầm bảng tổng ở trên.

**Bài học phương pháp:** sửa code giữa chừng làm hỏng chính phép đo mà lần chạy ấy sinh ra
để phục vụ. Nếu cần một con số so sánh sạch thì phải để một lần chạy đi hết mà không đụng
vào bất kỳ file nào trong `QUALITY_IMPLEMENTATION_FILES`.

### Giả thiết 3: tên chuyển tự đọc chậm hơn — CŨNG SAI

Nhịp trước tôi kết luận rằng đây là "xung đột tự gây": dự án biến
"Samael Kaizer Theosbane" thành "Xa-ma-eo Cai-dơ Thê-ô-xờ-ben", giọng đọc từng âm tiết có
gạch nối chậm rãi, rồi cổng nhịp từ chối. Nghe rất thuyết phục, và **hai trong ba ca hỏng
đúng là câu có tên**.

Hỏi cả hai cuốn thay vì ba câu (`scripts/pace_of_transliterated_names.py`), chia theo việc
segment có neo tên khoá hay không, tính nhịp **đúng như `audio_io` tính**:

| | n | trung vị | p5 | p25 | dưới cận 12,5 |
|---|---:|---:|---:|---:|---|
| **có** tên chuyển tự | **341** | 15,85 | 13,91 | 15,01 | **0 (0,0%)** |
| không có | 1.276 | 15,79 | 13,65 | 15,00 | 0 (0,0%) |

Chênh lệch trung vị **−0,05 ký tự/s**, tức **−0,03 sigma**. Nhóm có tên nếu có khác thì
**nhỉnh hơn**, không chậm hơn. Với 341 mẫu thì đây không phải chuyện thiếu dữ liệu.

**Ba giả thiết, ba lần sai.** Đơn vị đo không sai, cận không đặt sai, và tên chuyển tự
không đọc chậm hơn. Ba segment ấy chỉ là **đuôi phân bố**: những lần bốc thăm chậm mà năm
lượt thu lại không lần nào rơi vào khoảng cho phép. Việc "hai trong ba là câu có tên" là
trùng hợp ở n=3.

**Đừng nới cổng vì chúng.** Nếu muốn cứu, hướng đúng là cho thêm lượt thu hoặc đổi seed cho
đúng những segment quá ngắn để chia — chứ không phải hạ một ngưỡng mà 1.617 bản thu khác
đều vượt qua thoải mái.

### Ràng buộc suy ra từ đại số chi phí: tính giá theo bề rộng (đo xong, CHƯA ship)

Bảng chi phí của DP, tối thiểu hoá theo thứ tự từ điển:

| phép | chi phí |
|---|---|
| `match_anchor` | **(0, 0, −1, 0)** |
| `substitute_anchor` | (1, 0, 0, 0) |
| `insert_transcript` / `delete_*` | (1, 0, 0, 1) |
| `match_token` | (0, −1, 0, 0) |

Khớp neo luôn thắng thế ở thành phần đầu, **nếu** bề rộng thay thế cố định ở 1. Nới nó với
giá phẳng `(1,0,0,0)` phá điều đó: hút ba token với giá 1 có thể làm cả đường rẻ hơn là
khớp neo rồi trả riêng cho các chữ đọc sai — đúng cách ca chốt mất lần khớp của nó.

**Ràng buộc:** thay thế w token thì tốn `(w, 0, 0, 0)`. Suy ra từ chính bảng trên, không
phải đoán. Hút thêm token không bao giờ rẻ hơn gióng hàng chúng; còn một cái tên thật sự bị
nghe thành nhiều token thì tốn đúng bằng "thay-một cộng chèn", nhưng ghi điểm tốt hơn ở
thành phần thứ tư.

Đo bằng `scripts/replay_anchor_alignment.py` với bản vá tại chỗ (`scratchpad/try_width.py`,
không đụng `asr.py` vì alpha.43 đang chạy):

| | review_eligible | fail | chốt |
|---|---:|---:|---|
| hiện tại | 20 | **4** | giữ |
| tính giá theo bề rộng | 23 | **1** | **giữ** |

Chốt giữ nguyên: neo vẫn khớp chính xác, verdict vẫn `mismatch`, không promoted.

### Nhưng một ca đổi chiều, và tôi chưa chắc chiều nào đúng

Trên mẫu gộp hai cuốn, ca duy nhất còn hỏng là `c00007_s0000074` (Juliana), còn
`c00010_s0000016` **chuyển thành review_eligible ở canonical sim 0,947**:

```
mong đợi : Tai Ương Bình Minh (Đon Xờ-cớt).
nghe ra  : Tài hương bình mình đon sờ cướp.
```

Trước đây tôi xếp ca này vào loại "tiếng Việt **cũng** nghe sai, hỏng đúng, không bản sửa
gióng hàng nào nên cứu". Nhìn kỹ thì "Tai Ương Bình Minh" → "Tài hương bình mình" **chủ yếu
là khác thanh điệu**, mà `_tone_folded_words` **cố ý bỏ qua thanh điệu** vì "một khác biệt
thanh điệu ở các chữ quanh một cái tên không nói gì về chất lượng bản thu". Theo chính luật
ấy thì cho nó qua có thể **đúng**.

Tôi không phân xử được bằng phép đo: câu hỏi "Tài hương bình mình có phải một bản đọc chấp
nhận được của Tai Ương Bình Minh không" cần một đôi tai. Đó cũng chính là thứ lệnh `accept`
tồn tại để trả lời.

**Chưa ship.** `asr.py` nằm trong `QUALITY_IMPLEMENTATION_FILES` và alpha.43 đang chạy phép
đo faster-whisper; sửa nó bây giờ là hỏng đúng lần chạy ấy, đúng sai lầm đã mắc với alpha.32.
Ràng buộc và số đo đã ghi ở đây; merge sau khi alpha.43 xong, và nghe `c00010_s0000016`
trước khi quyết.

## `BatchedInferencePipeline` không lấp được GPU rảnh (đo 2026-09-04)

Tồn đọng ghi nó là đòn bẩy lớn kế tiếp: GPU chỉ 14–16% suốt pha ASR, VRAM 1,43/8,15 GB, mà
Whisper giải mã một file một lần — nên giải mã nhiều file cùng lúc *hẳn* phải lấp chỗ trống.
"Hẳn phải" đúng là thứ dự án này liên tục sai, và xây nó nghĩa là sửa `asr.py`, một file mà
mỗi lần sửa tốn cả lượt xác minh lại. Nên đo trước khi viết.

48 bản thu của alpha.32, cùng tuỳ chọn, cùng luật beam-theo-độ-dài, hai lần chạy:

| | một-lần-một | theo lô (batch 8) | nhanh hơn |
|---|---:|---:|---:|
| lần 1 | 1,075 s/bản | 0,898 s/bản | 1,20× |
| lần 2 | 1,046 s/bản | 0,938 s/bản | **1,11×** |

**Không phải 3–5× như chỗ GPU rảnh gợi ý.** Nếu thời gian nằm ở phần tính toán GPU song
song hoá được thì gộp lô đã ăn hết chỗ đó; nó không ăn, nên **thời gian nằm ở chỗ khác** —
nạp và resample audio phía CPU, tính mel, VAD, hoặc phí tổn mỗi lời gọi. Con số này bác bỏ
cách hiểu "GPU rảnh nên cứ song song hoá là xong".

### Chất lượng thì không đổi

| | |
|---|---|
| bản ghi **thô** khác nhau | 4/48 (8,3%) |
| sau **chuẩn hoá** còn khác | **0/48 (0,0%)** |

Khác biệt thô chỉ là ngắt câu — *"thất bại, và"* so với *"thất bại. Và"* — mà pipeline không
bao giờ so văn bản thô: `normalize_transcript` bỏ hết dấu câu trước khi so. Nên gộp lô
không đổi một verdict nào.

### Kết luận: chưa đáng

1,11× trên phần ASR còn lại sau faster-whisper (~1.870s) là khoảng 170 giây, đổi lấy một
thay đổi trong `asr.py` cộng một lượt xác minh lại cả sách. **Không đáng bây giờ.**

Câu hỏi hay hơn mà phép đo này mở ra: **nếu không phải tính toán GPU thì thời gian ASR nằm
ở đâu?** Đó mới là phép đo tiếp theo đáng làm, và nó rẻ hơn nhiều so với việc xây một cái lô.

*Lưu ý về điều kiện đo:* alpha.43 đang dùng GPU cho Ollama lúc chạy phép đo này, nên con số
tuyệt đối bị ảnh hưởng. Tỉ lệ giữa hai cách trên cùng một máy cùng một lúc thì vẫn so được,
và đó là thứ câu hỏi này cần.

## Thời gian ASR nằm ở đâu: gần một nửa là phí cố định mỗi lời gọi (đo 2026-09-04)

Phép đo trước bác bỏ "GPU rảnh nên cứ song song hoá". Câu hỏi kế tiếp rẻ hơn nhiều so với
việc xây bất cứ thứ gì: **thời gian ấy nằm ở đâu?** 60 bản thu của alpha.32, tách phần nạp
audio khỏi phần gọi model, rồi khớp bình phương tối thiểu theo độ dài:

| | |
|---|---|
| nạp + resample (soundfile + polyphase) | 0,36s tổng — **0,7%**, 6 ms/bản |
| giải mã | 54,48s tổng — **99,3%**, 908 ms/bản |
| tỉ lệ thời gian thực | 0,153× |

```
giải mã ≈ 369 ms  +  90 ms × (số giây âm thanh)
```

Với bản thu trung vị **4,8 giây**, phần cố định chiếm **46%**.

### Ba hệ quả

1. **Nạp audio không phải chỗ tốn.** 0,7% — đừng tối ưu nó.
2. **Phép đo này giải thích vì sao batching chỉ được 1,11×.**
   `BatchedInferencePipeline` gộp các *cửa sổ trong một file*, không gộp *giữa các file*,
   nên nó không chia sẻ được đúng cái phí đang chiếm gần nửa chi phí.
3. **Con số đáng nhớ:** 2.032 lượt giải mã của alpha.25 × 369 ms ≈ **750 giây**, tức khoảng
   **19%** của 3.870s ASR, tiêu vào phí gọi chứ không vào tiếng nói.

### Cơ chế: encoder tính tiền theo cửa sổ 30 giây, không theo lượng âm thanh

Whisper đệm mọi đầu vào lên 30 giây trước khi qua encoder. Giả thuyết ấy khớp với hình dạng
đo được, nhưng khớp không phải là chứng minh, nên `scripts/measure_encoder_window.py` kiểm
thẳng: **một bản thu duy nhất, đệm bằng im lặng tới nhiều độ dài khác nhau.** Tiếng nói y
hệt nhau nên decoder có đúng bấy nhiêu token phải sinh; chỉ phần đệm thay đổi.

| đệm tới | giải mã | ký tự thu được |
|---|---|---|
| 3,0s | 272 ms | 33 |
| 6,0s | 249 ms | 33 |
| 12,0s | 273 ms | 33 |
| 20,0s | 275 ms | 33 |
| 28,0s | 258 ms | 33 |
| **31,0s** | **544 ms** | 103 |
| 45,0s | 560 ms | 104 |
| 58,0s | 573 ms | 104 |
| **61,0s** | **874 ms** | 174 |

Phẳng trong khoảng 10,7% suốt từ 3 đến 28 giây, rồi **gấp đôi ở 31 giây và gấp ba ở 61
giây**. Encoder tính tiền theo cửa sổ 30 giây và hoàn toàn mù với lượng âm thanh thật bên
trong: một bản thu 2 giây trả đúng bằng một bản 28 giây.

Một điều cần nói thẳng: số ký tự tăng 33 → 103 → 174, tức **Whisper bịa chữ vào phần im
lặng**, nên chiều cao của bậc có lẫn token decoder chứ không thuần encoder. Phần phẳng dưới
30 giây mới là bằng chứng sạch. Còn việc nó bịa chữ trong im lặng lại là một cảnh báo cho
chính hướng đi mà phép đo này chỉ ra.

### Cái giá đang trả, và cái giá để lấy lại

Bản thu trung vị 4,8 giây, cửa sổ 30 giây: **84% mỗi lượt encoder là phần đệm.** Một cửa sổ
chứa được sáu segment.

| | hiện nay | nếu gói 6 segment/cửa sổ |
|---|---|---|
| một lượt ASR (948 segment) | 760s | 468s (**−38%**) |
| alpha.25 (2.032 lượt giải mã) | — | tiết kiệm ~625s trên 3.870s (**−16%**) |

16% là thật, nhưng nó **không rẻ**. Gói nhiều segment vào một cửa sổ trộn ranh giới bản ghi,
và mọi thứ phía sau đều giả định một bản ghi thuộc về đúng một segment: neo tên khoá, phép
kiểm dòng thời gian ảo giác, similarity theo từng segment. Phép đo trên còn cho thấy Whisper
sẵn sàng bịa chữ ở chỗ không có tiếng nói, nên chỗ nối giữa hai segment là đúng nơi nguy
hiểm nhất. Đây là thay đổi kiến trúc, không phải một tối ưu - và `asr.py` nằm trong
`QUALITY_IMPLEMENTATION_FILES`, nên mỗi lần sửa nó là một lần xác minh lại cả quyển sách.

Ghi lại ở đây để lần sau ai đó hỏi "sao ASR chậm thế" thì có sẵn câu trả lời đã đo, và biết
đòn bẩy nằm ở đâu cùng cái giá của nó - chứ không phải để làm ngay.

## faster-whisper: ~2,25 lần trên pha ASR, đo bằng một biến kiểm nội bộ (tạm thời, 2026-09-04)

alpha.43 chạy `asr.engine = faster`; alpha.32 chạy engine cũ. Cùng quyển sách, cùng máy,
tính theo thời gian mỗi việc giữa hai bước liên tiếp cùng nhãn:

| pha (mỗi việc) | alpha.32 (openai) | alpha.43 (faster) | tỉ lệ |
|---|---|---|---|
| **Kiểm tra phát âm** (ASR) | 1,54s | **0,56s** | **2,75×** |
| Kiểm tra candidate clarity (ASR) | 0,85s | 0,48s | 1,77× |
| Tạo candidate clarity (**TTS — biến kiểm**) | 5,45s | 4,46s | 1,22× |

**Hàng TTS là chỗ giữ cho con số trung thực.** Sinh candidate không dính gì tới engine ASR,
nên 1,22× của nó đo phần cải thiện đến từ việc *máy rảnh hơn* chứ không từ engine — chủ sách
có nói "giờ máy rảnh rồi" trước khi alpha.43 chạy. Chia nó ra:

    pha ASR chính : 2,75 / 1,22 ≈ **2,25×** thuộc về engine
    kiểm candidate: 1,77 / 1,22 ≈ **1,45×**

Hai pha ASR lệch nhau, và điều đó khớp với phép đo cửa sổ 30 giây ở trên: bản kiểm candidate
là những đoạn rất ngắn, mà đoạn ngắn thì chi phí bị phần encoder cố định chi phối - phần
faster-whisper cải thiện ít hơn. Đoạn dài hơn ở pha chính mới cho decoder chỗ để nhanh hơn.

Chiếu lên alpha.32: pha ASR chính 4.252s → ~1.550s, kiểm candidate 2.325s → ~1.600s. Khoảng
**3.400s trên ~15.600s công việc**.

**Có một phép đo cũ xác nhận.** Docstring của `asr.engine` trong `config.py` đã ghi
**"2,07× trên 200 bản thu, không lệch phán quyết lần nào"**. Con số của tôi - 2,25× sau khi
chia biến kiểm ra - khớp với nó, và tỉ lệ 78/79 bản ghi giống hệt khớp với "không lệch phán
quyết". Lần này phép đo có sẵn trong kho *xác nhận* kết quả thay vì bác nó, nhưng bài học
vẫn thế: đọc nó **trước**.

**Tạm thời.** alpha.43 mới xong 1 chương rưỡi (n=179 so với 2.311). Trung vị có thể dịch khi
chạy xong, và con số cuối phải lấy từ lần chạy đầy đủ.

### Đổi engine có làm máy nghe khác đi không? Chương 1-2, gần như không

Tốc độ chỉ là nửa câu hỏi. `scripts/measure_batched_asr.py` đã đặt ra tiêu chuẩn: *"một bản
giải mã làm đổi điều máy nghe thấy thì không phải một tối ưu, nó là một engine khác."* Hai
chương đầu đã xong ở cả hai lần chạy nên so được trực tiếp, trên 79 segment có bản ghi ở cả
hai:

| | alpha.32 (openai) | alpha.43 (faster) |
|---|---|---|
| bản ghi khác nhau sau chuẩn hoá | — | **1/79 = 1,3%** |
| `ASR_LOCKED_NAME_ANCHOR_MISMATCH` | 1 | 1 |
| `ASR_LOCKED_NAME_ANCHOR_REVIEW` | 5 | 5 |
| `ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE` | 2 | 2 |
| `ASR_UNVERIFIABLE_SHORT_TEXT` | 1 | 1 |
| `TTS_SPLIT_RECOVERY` | 2 | 2 |

**Mọi lớp cảnh báo ASR giữ nguyên.** Đúng cái tiêu chuẩn đặt ra.

Segment duy nhất khác - `c00002_s0000037`, văn bản `Rare (Hiếm - B): Mạnh hơn / khó tìm
hơn.` - thì faster-whisper nghe **tệ hơn**, không phải tốt hơn:

    openai : "Rai hiếm B mạnh hơn trên khó tìm hơn."     similarity 0,86   WER 0,125
    faster : "ra hiếm, bê mạnh hơn trên khó tìm hơn."    similarity 0,80   WER 0,25

### Và một chỗ suýt quy sai nhân quả

Chương 2 của alpha.43 hỏng vì `PERCEPTUAL_NATURALNESS_REVIEW` đúng trên segment ấy, nên rất
dễ kết luận "engine mới làm hỏng chương". So từng trường thì không phải:

    generation_delivery_mode :  clarity  ->  primary
    wav_sha256               :  04e5fd80 ->  69838cd7   (cùng voice, cùng 2,56s)

alpha.32 nhận một bản đã **qua sửa clarity**; alpha.43 đang cầm bản **primary**. Hai bản thu
khác nhau thì điểm perceptual khác nhau - và perceptual chấm *âm thanh*, không chấm bản ghi.
Trên bằng chứng này, chỗ hỏng ấy **không quy được cho engine**.

**Tạm thời và phải làm lại khi chạy xong:** n=79 trên 948, và một quyển sách đang chạy dở
thì các segment còn lại chưa qua hết vòng sửa.

### ASR tốt hơn có thể làm **mất** một chương, và đây là cơ chế

alpha.43 hỏng chương 6 trong khi alpha.32 **xuất bản được** chương ấy. Đây là khác biệt kết
quả đầu tiên giữa hai lần chạy, và nó không phải chuyện engine nghe tệ hơn — ngược lại hẳn.

Segment `c00006_s0000001`, văn bản `"Mẹ kiếp! A a a! Khốn nạn!"` (một tiếng gào):

| | máy nghe | similarity | kết cục |
|---|---|---|---|
| alpha.32 (openai) | *"Cảm ơn các bạn đã theo dõi và hẹn gặp lại."* | **0,00** | `TIMELINE_IMPOSSIBLE` → warning → **xuất bản** |
| alpha.43 (faster) | *"Mày tiếp, á á khốn nặng"* | **0,59** | `MISMATCH_UNRESOLVED` → failed → **chặn** |

Bản của alpha.32 là ảo giác kinh điển của Whisper (đoạn kết video YouTube). faster-whisper
nghe **tốt hơn nhiều** — và bị phạt vì điều đó.

**Cơ chế nằm trong danh sách miễn trừ.** `HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS` tha
`ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE` với lý do hoàn toàn đúng — comment trong `pipeline.py`
còn nêu **đúng câu này** làm ví dụ: mốc thời gian chạy quá cuối file nghĩa là bộ giải mã đã
lạc khỏi âm thanh, nên bản ghi *không mang thông tin gì* về bản thu. Nhưng khi engine mới
không ảo giác nữa, cùng segment ấy cho ra một bản ghi **có** thông tin, và thông tin ấy nói
"chưa khớp lắm" (0,59 so với ngưỡng 0,78 của high_quality). Thế là chặn.

Nói gọn: **danh sách miễn trừ được hiệu chỉnh quanh kiểu hỏng của openai-whisper.** Bản ghi
sai đến mức vô nghĩa thì được tha; bản ghi gần đúng thì chặn.

Đếm được (alpha.43 mới xong 6/10 chương, nên là tỉ lệ chứ không phải tổng):

| | `TIMELINE_IMPOSSIBLE` (được tha) | `ASR_MISMATCH_UNRESOLVED` (chặn) |
|---|---|---|
| alpha.32, 10 chương | **9** (0,9/chương) | 0 |
| alpha.43, 6 chương | **2** (0,33/chương) | 1 |

**Đừng đọc thành "quay lại engine cũ".** Ít ảo giác đi là tốt hơn thật; chương 6 của alpha.32
xuất bản được *nhờ* Whisper ảo giác, và đó không phải một bảo đảm chất lượng. Bản thu gần
như chắc chắn ổn: "Mẹ kiếp"→"Mày tiếp", "khốn nạn"→"khốn nặng" là kiểu nghe nhầm rất hợp lý
với một câu **gào lên**.

Cái còn thiếu là một hạng mục: `ASR_UNVERIFIABLE_SHORT_TEXT` đã thừa nhận "quá ngắn nên phán
quyết vô nghĩa", nhưng không có tương đương cho **"cách diễn đạt khiến bản ghi không đáng
tin"** — gào, hét, chuỗi thán từ. Trước mắt thì đúng loại việc cần **tai người nghe**, và
`accept` có sẵn cho đúng việc đó.

#### Theo dõi cả lớp, không chỉ ca gây chú ý: 1 trên 5, không hệ thống

Mục trên viết từ **một** ca. Đó là đủ để chỉ ra cơ chế nhưng không đủ để nói lớp ấy lớn cỡ
nào, nên theo dấu cả 9 segment `TIMELINE_IMPOSSIBLE` của alpha.32 sang alpha.43 (5 cái đã
được xử lý tới thời điểm này):

| segment | similarity 32 → 43 | kết cục ở alpha.43 |
|---|---|---|
| ch2 `s0000067` | 0,00 → 0,00 | vẫn ảo giác, vẫn được tha |
| ch2 `s0000071` | 0,00 → 0,00 | vẫn ảo giác, vẫn được tha |
| ch4 `s0000099` | 0,00 → 0,00 | vẫn ảo giác, vẫn được tha |
| ch6 `s0000066` | 0,00 → **0,50** | **verified** — nghe rõ hơn thì *cứu* được segment |
| ch6 `s0000001` | 0,00 → **0,59** | **failed** — ca đã nêu ở trên |

**1/5 chuyển từ "được tha" thành "chặn".** Ba cái không đổi gì, và một cái nghe rõ hơn lại
đi qua cổng thay vì bị chặn. Vậy đây **không phải một lớp hỏng hệ thống**, mà là một cái
răng cưa: bản ghi tốt hơn có thể rơi về **hai** phía của ngưỡng 0,78, và nó đã rơi cả hai
phía ngay trong cùng một chương.

Còn 4 segment nữa (ch7 ×2, ch9, ch10) chưa tới lượt — con số cuối phải chờ chạy xong.

Ghi lại cả cách suy luận: tôi viết mục trên khi n=1, và ca ấy dựng lên một câu chuyện gọn
gàng ("ASR tốt hơn làm mất chương"). Với n=5 thì câu chuyện ấy đúng về *cơ chế* nhưng sai về
*quy mô*. Một ca đủ để tìm ra cơ chế, không bao giờ đủ để định giá nó.

#### Máy đã cố hết mức, và đó chính là bằng chứng

Tôi đoán bản thu của `c00006_s0000001` vẫn ổn còn câu gào thì khó nghe. Sổ candidate của
alpha.43 ủng hộ điều đó chứ không chỉ là suy diễn ngữ âm:

    r0 a0 dual_failed  2,08s   beam=ASR_MISMATCH; greedy=ASR_MISMATCH
    r1 a0 dual_failed  1,92s   beam=ASR_MISMATCH; greedy=ASR_MISMATCH
    r2 a0 dual_failed  1,84s   beam=ASR_MISMATCH; greedy=ASR_MISMATCH
    r3 a0 dual_failed  2,16s   beam=ASR_MISMATCH; greedy=ASR_MISMATCH
    r4 a0 dual_failed  2,00s   beam=ASR_MISMATCH; greedy=ASR_MISMATCH

**Năm vòng sửa, năm bản thu seed khác nhau, mười lần giải mã, tất cả đều lệch.** Ngân sách
`asr.repair_rounds = 5` của high_quality đã dùng hết và dùng đúng.

Năm bản thu độc lập cùng hỏng theo một kiểu thì khó tin là "năm bản thu tồi" hơn là "câu này
không nghe ra được". Nghĩa là **thêm nỗ lực của máy không cứu được nó** — đúng chỗ cần
`accept`, và cũng đúng lý do `accept` tồn tại.

#### Bảng cuối (7/9 đã xử lý), và lớp ấy thật ra là gì

| segment | sim 32 → 43 | kết cục ở alpha.43 |
|---|---|---|
| ch2 `s0000067` (`S`) | 0,00 → 0,00 | vẫn `TIMELINE_IMPOSSIBLE`, vẫn được tha |
| ch2 `s0000071` (`SSS`) | 0,00 → 0,00 | vẫn `TIMELINE_IMPOSSIBLE`, vẫn được tha |
| ch4 `s0000099` (`—RẦM!!`) | 0,00 → 0,00 | `UNVERIFIABLE_SHORT_TEXT`, được tha |
| ch7 `s0000035` (`"Argh!"`) | 0,00 → 0,00 | **verified**, không còn cảnh báo nào |
| ch6 `s0000066` | 0,00 → 0,50 | qua cổng |
| ch7 `s0000051` | 0,00 → **1,00** | qua cổng — bản ghi **hoàn hảo** ở chỗ engine cũ ảo giác |
| ch6 `s0000001` | 0,00 → 0,59 | **chặn** |

**6/7 không chặn, 1/7 chặn.** Còn 2 segment (ch9, ch10).

**Lớp này là gì:** nhìn văn bản thì rõ — `S`, `SSS`, `—RẦM!!`, `"Argh!"`, `"Mẹ kiếp! A a a!"`.
Đây là **chữ cái đơn, tiếng động, tiếng gào** — những chỗ gần như không có nội dung lời nói
để mà nghe. Whisper lấp chỗ trống bằng thứ nó được huấn luyện (`"Các bạn hãy đăng ký kênh
để ủng hộ kênh của mình nhé."` là ví dụ hoàn hảo). Phán quyết ASR ở đây vốn dĩ vô nghĩa, và
đó chính là điều hai mã miễn trừ đang nói.

**Một lỗi của tôi trong lúc đếm, đáng ghi lại:** bảng đầu tôi kiểm
`"TIMELINE_IMPOSSIBLE" in codes` với `codes` là một **set** — mà thành viên của set phải
khớp *nguyên vẹn*, còn mã thật là `ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE`. Nên nó không bao giờ
khớp, và tôi báo "0 segment còn ảo giác" trong khi có 2. Tổng số chặn/không chặn thì vẫn
đúng vì tính bằng đường khác. Kiểm chuỗi con thì đừng dùng `in` trên set.

## Nhường máy cho người dùng: 0,38 segment/phút, và nghịch lý nhẹ-hơn-nặng

Đo trên 4,4 giờ đầu của alpha.46, gán mỗi segment hoàn tất cho chế độ tài nguyên đang có
hiệu lực đúng lúc đó:

| chế độ | segment | phút | nhịp |
|---|---|---|---|
| `maximum` | 452 | 80,6 | **5,60 /phút** |
| `yield_heavy` | 69 | 30,4 | **2,27 /phút** |
| `yield_light` | 57 | 150,2 | **0,38 /phút** |

`yield_light` khai báo `gpu_batch_scale = 0.70` — giảm 30% — nhưng thực tế chạy chậm hơn
**14,7 lần**, và **chậm hơn cả `yield_heavy`**, chế độ đáng lẽ nhường nhiều hơn.

### Nguyên nhân

`YIELD_LIGHT` đặt `allow_cpu_heavy_work=False` **vô điều kiện**. `YIELD_HEAVY` thì đặt cờ ấy
**có điều kiện**, chỉ chặn khi thật sự có `foreground_cpu_pressure`, `disk_io_pressure`,
`memory_pressure` hoặc `disk_space_pressure`.

Mà nhánh `YIELD_LIGHT` **chỉ chạy tới được khi cả bốn sức ép ấy đều vắng mặt** — nếu có bất
kỳ cái nào thì nhánh `YIELD_HEAVY` phía trên đã return rồi. Nói cách khác: chế độ nhẹ chặn
CPU chính vì lý do khiến nó là chế độ nhẹ.

Hậu quả không nhỏ, vì `pipeline._wait_for_resources` xử lý cờ ấy bằng cách ngủ:

```python
cpu_ok = (not require_cpu_io) or decision.allow_cpu_heavy_work
if gpu_ok and cpu_ok:
    return decision
time.sleep(2.0)
```

Nên mọi checkpoint cần CPU I/O **đứng im chừng nào người dùng còn động vào máy**. Điều kiện
kích hoạt chỉ là `user_active and cpu_percent >= 55` — tức chỉ cần đang dùng máy. Tối
05/09/2026 nó ở trạng thái đó liên tục **21:44 → 23:36, 112 phút**, sinh được 57 segment.
Với nhịp của `yield_heavy` thì quãng ấy chỉ mất 25 phút.

### Đã sửa

`allow_cpu_heavy_work=True` ở `YIELD_LIGHT`. Việc nhường mà chế độ này định làm là
`gpu_batch_scale=0.70`, và thế là đủ; sức ép CPU thật vẫn rơi xuống `YIELD_HEAVY` và vẫn bị
chặn như cũ.

Test khoá lại **tính chất** chứ không phải giá trị: chế độ nhẹ không bao giờ được phép khắt
khe hơn chế độ nặng, ở cả cờ CPU lẫn `gpu_batch_scale`.

### Một phép đo sai, ghi lại để đừng lặp

Trước khi tìm ra nguyên nhân thật, tôi đo "thời gian nạp UTMOSv2" bằng cách ghép dòng
`Loading pretrained weights` với dòng `Processing audio` kế tiếp, và ra **47 phút / 18% lần
chạy**. Sai. Nhìn thẳng vào log thì các dòng nạp cách nhau **0,6 giây**; hàm ghép cặp của tôi
đã bắt sang sự kiện của thành phần khác. Một phép đo phải được nhìn tận mắt ở một mẫu cụ thể
trước khi tin vào con số tổng.

## Sức ép RAM của pool: một lỗi thật, nhưng đừng bán nó như tiết kiệm thời gian

Pool chấm cảm thụ tự định cỡ mà không biết pool TTS sắp khởi động, và hằng số RAM mỗi worker
thấp hơn thực tế — hai cái cộng lại đẩy alpha.47 xuống 1,5–2,3 GB trống và ném run vào
`yield_heavy`. Chi tiết bản sửa: commit `01384a7` và `ad9fd0c`.

Nhưng **đo mới biết nó tốn bao nhiêu**, và câu trả lời khiêm tốn. Trên 166 phút đầu của
alpha.47:

| chế độ | thời gian | tỉ lệ |
|---|---|---|
| `maximum` | 156,1 phút | **94,0%** |
| `yield_heavy` | 5,2 phút | 3,1% |
| `yield_light` | 2,9 phút | 1,7% |
| `pause_new_work` | 1,8 phút | 1,1% |

Tổng cộng **~6 phút trên 166**, tức 3,7%. Worker chấm cảm thụ sống ngắn, nên mỗi lần siết
chỉ kéo dài dưới một phút rồi nhả.

**Giá trị của bản sửa là không tự bắn vào chân, không phải throughput.** Một pool tự đưa mình
vào trạng thái cấm chính công việc nó đang làm là sai bất kể tốn mấy phút, và trên một máy ít
RAM hơn thì cùng lỗi ấy sẽ không còn nhẹ như vậy. Nhưng đừng trích nó như một mục tối ưu.

### Đối chiếu để giữ đúng tỉ lệ

Cùng họ vấn đề — "cơ chế nhường máy tự chặn công việc" — nhưng hai bậc độ lớn khác nhau:

| lỗi | tốn |
|---|---|
| `yield_light` chặn CPU vô điều kiện (alpha.46) | **112 phút liên tục**, 0,38 segment/phút |
| pool vượt ngân sách RAM (alpha.47) | ~6 phút rải rác |

Cái thứ nhất là mất một buổi tối; cái thứ hai là một vết xước. Cả hai đều đáng sửa, chỉ đừng
báo cáo chúng như nhau.

### alpha.48 xác nhận bản sửa, trên cùng một mẻ việc

Phép đối chiếu sạch vì cùng chương, cùng số đoạn: **chương 3, 111 đoạn.**

| | alpha.47 | alpha.48 |
|---|---|---|
| worker chấm cảm thụ | 8 | **3** |
| RAM trống lúc căng nhất | 1,5–2,3 GB | **3,4 GB** |

Ngân sách 2,65 GB/worker cộng phần dành sẵn cho pool TTS đã tự cắt pool từ 8 xuống 3. RAM
dừng ngay dưới sàn 3,5 thay vì thủng sâu — lệch khoảng 0,1 GB, nằm trong sai số của phép ước
lượng, nên không đáng siết thêm.

**Chưa đo được là cái giá.** 3 worker thì chấm chậm hơn 8, và việc chấm vốn được giấu sau
ASR nên có thể không mất gì — nhưng "có thể" không phải là một phép đo. Đừng ghi bản sửa này
là thắng thuần cho tới khi có thời gian hoàn thành chương của hai bản để so.
