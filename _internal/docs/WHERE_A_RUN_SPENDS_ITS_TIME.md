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
