# VRAM, num_ctx, và chỗ chậm nhất của pha phân tích

## Máy đang hết VRAM (đo 2026-09-03, trong lúc alpha.26 chạy)

```
NVIDIA GeForce RTX 5060 Laptop GPU | 8151 MiB tổng | 7503 MiB đã dùng | 308 MiB trống
ollama ps: qwen3:8b | 7.8 GB | 22%/78% CPU/GPU | ctx 16384
```

**Model không lọt hết vào VRAM nên 22% số lớp phải chạy trên CPU.** Với một model 8B, các
lớp bị đẩy sang CPU chi phối thời gian sinh token, vì sinh token là bài toán giới hạn bởi
băng thông bộ nhớ chứ không phải bởi tính toán. Đây là chỗ chậm nhất của pha phân tích, mà
pha phân tích là pha dài nhất của một lần chạy mới: alpha.26 đi 5 segment mỗi ~31 giây,
tức 948 segment ≈ 98 phút.

Tranh VRAM với Ollama tại thời điểm đo: **ba tiến trình Unity Editor**, Unity Hub, JetBrains
Rider, Fork, hai tiến trình Edge, Telegram, Claude. Đây là công việc khác của người dùng,
không phải thứ tôi được tự tắt.

## num_ctx 16384 giữ chỗ bao nhiêu?

KV cache của qwen3:8b (36 lớp, 8 đầu KV, 128 chiều, fp16):

| num_ctx | KV cache |
|---|---|
| 4.096 | ~0,60 GB |
| 8.192 | ~1,21 GB |
| **16.384** | **~2,42 GB** |

Chỗ này được giữ dù prompt có dùng tới hay không.

## Prompt thật dùng bao nhiêu? (chưa đủ để kết luận)

Đo bằng chính tokenizer của Ollama (`num_predict: 1`, đọc `prompt_eval_count`) trên
SYSTEM_PROMPT thật cộng 5 segment thật:

```
system 4.405 ký tự | 5 segment 390 ký tự
prompt = 1.351 token / 16.384 ctx = 8,2%
```

**Đây là cận dưới, không phải con số thật.** Nó thiếu schema JSON của batch (có enum theo
từng ID nên khá lớn), ngữ cảnh chương, và các segment thật thì dài hơn 5 segment đầu chương.

Ngân sách đầu ra thì đã biết chính xác:
`_analysis_output_token_limit(5, num_ctx)` = **1.472 token ở cả 4096, 8192 lẫn 16384** —
`min(512 + 5*192, num_ctx // 2, 6144)`, và vế `num_ctx // 2` không hề chặn. Nghĩa là
**num_ctx 16384 không phục vụ đầu ra chút nào**; nó chỉ nới trần cho prompt.

Tổng tối thiểu đã biết: 1.351 + 1.472 = **2.823 token**. Kể cả nếu prompt thật gấp ba cận
dưới thì vẫn khoảng 5.500 — lọt num_ctx 8192, và tiết kiệm 1,21 GB VRAM, nhiều hơn mức cần
để kéo model từ 78% GPU lên 100% GPU.

## Tại sao chưa đổi

Prompt vượt `num_ctx` thì Ollama **cắt bớt trong im lặng**, và một batch phân tích bị cắt
mất phần đuôi vẫn trả về JSON hợp lệ. Đổi num_ctx dựa trên một cận dưới là đánh cược tính
đúng đắn của phân tích để lấy tốc độ. Cần con số lớn nhất thật, không phải con số ước lượng.

Commit `18295d5` giữ lại các bộ đếm mà Ollama vẫn luôn gửi kèm chunk cuối
(`prompt_eval_count`, `eval_count`, thời lượng mỗi vế) và ghi chúng ra log. Lần chạy mới
đầu tiên sau commit đó sẽ cho biết prompt lớn nhất thật là bao nhiêu, và lúc ấy quyết định
num_ctx là một phép so sánh chứ không phải một suy đoán.

Lấy ra khỏi log:

```bash
grep -o "prompt [0-9,]* tok" logs/ebook_reader.log | tr -d ', ' | grep -o '[0-9]*' | sort -n | tail -1
```

## Đã sửa, và đã đo lại (2026-09-03)

`num_ctx` không còn là một hằng số cho mọi profile. Nó được suy ra từ chính batch của
profile đó (`config.analysis_context_window`): high_quality **7.168**, balanced 13.312,
fast 14.336. Con số 16384 cũ không tuỳ tiện - nó đúng cho profile gốc, 28 segment mỗi batch
với ngân sách đầu ra 5.888 token - nhưng high_quality ghi đè batch xuống 5 mà vẫn thừa
hưởng nguyên cái ngữ cảnh ấy.

Đo trên hai lần chạy cùng sách, cùng máy, chỉ khác num_ctx:

| | alpha.27 (16.384) | alpha.28 (7.168) |
|---|---|---|
| `ollama ps` kích thước | 7,8 GB | **6,0 GB** |
| bộ xử lý | 22% CPU / 78% GPU | **100% GPU** |
| sinh token | 25,8 tok/s | **53,6 tok/s** |
| một batch 5 segment | 20,8s | **11,3s** |

**Nhanh gấp 2,08 lần ở nửa chậm.** Sinh token chiếm 94% thời gian Ollama (đo trên 40 yêu
cầu của alpha.27), nên pha phân tích - pha dài nhất của một lần chạy mới, khoảng 95 phút -
rút còn khoảng một nửa.

Lý do nó hiệu quả đến vậy: sinh token bị giới hạn bởi băng thông bộ nhớ, không phải bởi
tính toán. Mọi lớp nằm trên CPU đều phải đi qua PCIe cho từng token một. Đưa được model
lọt hết vào VRAM không phải là tối ưu vi mô, nó xoá hẳn một nút cổ chai.

### Hai bậc phải vượt, không phải một

Ngân sách đầu ra là `min(512 + segment*192, num_ctx // 2, 6144)`. Một ngữ cảnh chỉ *lớn hơn*
đầu ra yêu cầu thì vế `// 2` vẫn lặng lẽ cắt đôi nó, và một batch phân tích bị cụt giữa
chừng JSON làm hỏng cả chương. Nên khung phải **ít nhất gấp đôi yêu cầu**, và ít nhất bằng
prompt cộng đầu ra. Công cụ `scripts/ollama_usage.py` lúc đầu đề xuất 4096 vì chỉ nhìn
prompt đã quan sát được; 4096 sẽ cắt đôi đầu ra. Đã sửa.

### Bẫy im lặng giờ đã kêu

Ollama không từ chối và không cảnh báo khi prompt vượt ngữ cảnh: nó bỏ phần đầu rồi trả
lời về phần còn lại, và một batch mất mấy segment đầu vẫn ra JSON hợp lệ đúng schema. Không
chỗ nào trong hệ thống biết model chưa từng nhìn thấy phần đó.

`_check_prompt_fits` giờ ném `AnalysisPromptTruncatedError` khi số token prompt báo về đúng
bằng chỗ còn lại - dấu hiệu nó đã bị cắt cho vừa. **Đây là thứ khiến việc thu nhỏ ngữ cảnh
là an toàn**; thu nhỏ mà không có nó là đổi một sự lãng phí đã biết lấy một sự hỏng hóc
không biết.

### Xác nhận bằng đồng hồ tường (70 yêu cầu của alpha.28)

Bảng trên đo tốc độ sinh token. Đây là thời gian thật của cả pha, cùng sách, cùng máy,
đếm từ dòng log "batch N/194":

| | giây mỗi batch |
|---|---|
| alpha.27 (num_ctx 16.384) | 40,8 |
| alpha.28 (num_ctx 7.168) | **19,6** |

**2,08×** - trùng khít với mức tăng tốc sinh token, tức sinh token đúng là nút cổ chai chứ
không phải một trong nhiều chi phí. Chiếu ra 194 batch: **132 phút → 63 phút**.

Thời gian mỗi batch (19,6s) lớn hơn thời gian Ollama mỗi yêu cầu (9,6s) vì high_quality bật
`director_critic_enabled`, tức hai yêu cầu mỗi batch, cộng phần việc của host.

Nạp prompt cũng nhanh lên, 3.441 → 5.065 tok/s (1,47×), dù đó không phải nửa chiếm thời
gian. Prompt lớn nhất qua 70 yêu cầu là 3.744 token, tức 52% khung 7.168 - còn dư rộng.

## Gốc rễ: dự án chưa bao giờ đo được VRAM

`ResourceSnapshot` mang nhiệt độ GPU và % GPU của tiến trình foreground, nhưng **không có
dung lượng VRAM**. Đó là lý do sâu xa khiến mọi hằng số phụ thuộc VRAM đều phải hiệu chỉnh
bằng tay trên đúng một cái card 8151 MiB rồi ghi thẳng vào defaults: một con số không đo
được thì bắt buộc phải đoán, và một con số đoán thì đúng ở đây và sai ở mọi nơi khác.

Đã thêm `gpu_free_mb` và `gpu_total_mb` vào snapshot, hỏi qua `nvidia-smi` giống hệt cách
nhiệt độ vẫn được hỏi. Đo cho cả thiết bị chứ không riêng tiến trình này: câu hỏi mà những
chỗ gọi nó đặt ra là "card còn bao nhiêu chỗ", mà chương trình foreground đang giữ phần
còn lại thì không báo cáo cho ta.

### Người dùng đầu tiên: pool tổng hợp TTS

`docs/THROUGHPUT.md` ghi hai điểm đo: 3 worker giữ 5.484 MiB, 5 worker giữ 7.318 MiB. Nối
thành đường thẳng: **917 MiB mỗi worker trên nền dùng chung 2.733 MiB**. Chính con số ấy
giờ được áp cho card đang có, thay vì bị nướng thành hằng số.

- `tts.parallel_workers` trở thành **trần**, không phải yêu cầu - đúng hợp đồng mà pool
  cảm thụ đã dùng từ trước. Đo đạc chỉ có thể hạ nó xuống.
- Card 8151 MiB vẫn ra đúng 3 worker như đã đo.
- Card 4 GiB ra 0 và chuyển sang tuần tự, thay vì đòi bộ nhớ không có rồi hỏng.
- Card 24 GiB ra nhiều worker hơn mà không ai phải sửa hằng số.
- Máy không đọc được VRAM (không có nvidia-smi, không phải card NVIDIA) giữ nguyên con số
  cấu hình - đúng như mọi lần chạy trước đây.

`TTS_POOL_FOREGROUND_RESERVE_MB = 800` là phần cố ý chừa lại. 5 worker nhanh hơn 3 đúng
1,3% trong khi giữ 7.318 trên 8.151 MiB, tức không còn chỗ cho foreground lẫn cho việc giữ
Whisper thường trú. 1,3% không đáng để chiếm cả card.

### Còn lại chưa suy ra từ máy

`perceptual_qa.parallel_workers` và `worker_threads` (đã co theo RAM và số lõi, nhưng trần
8 và 2 luồng vẫn là hằng số hiệu chỉnh), `beam_size`, và `min_free_ram_gb` /
`critical_free_ram_gb` vốn là **GB tuyệt đối** chứ không phải tỉ lệ RAM máy.

## Ngưỡng RAM tuyệt đối: đã xét, và giữ nguyên có lý do

Tồn đọng ghi `min_free_ram_gb` (3,5) và `critical_free_ram_gb` (1,5) "vẫn là GB tuyệt đối
chứ không theo máy", như thể đó là khiếm khuyết. Xét lại thì **không phải**.

Hai ngưỡng ấy canh những khoản cấp phát **có kích thước cố định trên mọi máy**:

| | |
|---|---|
| qwen3:8b ở num_ctx 7168 | 6,0 GB VRAM |
| ba worker tổng hợp | 5.484 MiB VRAM |
| một worker chấm cảm thụ | 1,75 GB RAM |
| Whisper turbo | ~2,5 GB VRAM |

Một *phần trăm của máy* là đơn vị sai để đo một model có kích thước cố định. Máy 128 GB mà
chỉ còn 1,5 GB trống thì đang gặp rắc rối thật, y như máy 8 GB.

Điều máy nhỏ xứng đáng được nhận **không phải là một ngưỡng lỏng hơn** - nới ra chỉ khiến
nó chạy vào đúng vùng thrashing - mà là **một câu trả lời thẳng ngay từ đầu**. Trước đây
`doctor` kiểm tra mọi module import được, mọi tài sản tồn tại, và **không nói một chữ nào
về bộ nhớ**. Máy quá nhỏ vẫn qua sạch mọi kiểm tra rồi mới biết sự thật một cách chậm chạp:
nhường tài nguyên ở mọi cổng, đẩy model phân tích sang CPU, hoặc dừng giữa sách vì
"available RAM 1.1 GB" - đúng cách alpha.26 kết thúc ở 357/948.

`doctor` giờ có `headroom:ram` và `headroom:vram`. Mọi con số đều lấy từ chính hằng số mà
lần chạy sẽ dùng, không phải viết cứng - viết cứng thì nó vẫn "đạt" sau khi thứ nó mô tả đã
phình ra, đúng kiểu pool chấm điểm từng hứa 5 worker trên bộ nhớ chỉ chứa nổi 2.

Trên máy này: RAM 31,3 GB / cần 7,0 GB; VRAM 8.151 MiB / cần 5.367 MiB.

## Bẫy cắt prompt đã kêu trong lần chạy thật (alpha.32, 2026-09-03)

```
Prompt phân tích ... không vừa ngữ cảnh: num_ctx 7.168 trừ đầu ra dành sẵn 3.584
chỉ còn 3.584. Ollama đã cắt bớt phần đầu prompt mà không báo.
```

Đây là **giá trị của cái bẫy, chứng minh bằng chính lần chạy**: không có nó thì batch ấy
trả về JSON hợp lệ cho những cái tên còn sót lại sau khi bị cắt, không ai biết gì, và một
số tên sẽ có cách đọc do model bịa từ ngữ cảnh cụt. Có nó thì batch chia nhỏ, thử lại, và
về đích đủ **112/112 tên**.

Nhưng nó kêu vì suy luận `num_ctx` của tôi **chỉ biết một trong hai hình dạng yêu cầu**.
Pha phân tích gọi Ollama theo hai kiểu khác hẳn nhau:

| | số mục | văn bản prompt | đầu ra yêu cầu |
|---|---:|---:|---:|
| batch segment (high_quality) | 5 | tới 6.200 ký tự | 1.472 |
| batch chuẩn hoá tên | **20** | vài chục ký tự mỗi tên | **4.352** |

Tên thì ngắn mà câu trả lời dài; segment thì ngược lại. Cửa sổ 7.168 suy từ batch segment
để `num_ctx // 2 = 3.584` — **nhỏ hơn 4.352 mà batch tên xin** — nên vế `// 2` cắt đôi phần
đầu ra, chừa nửa còn lại cho prompt, và prompt không vừa.

`analysis_context_window` giờ lấy **max trên mọi hình dạng yêu cầu**, mỗi hình dạng tính
theo đúng đặc điểm của nó. high_quality: **7.168 → 9.216**. Vẫn tiết kiệm ~1,06 GB VRAM so
với hằng số 16.384 cũ, chỉ là trả lại một phần để đổi lấy tính đúng đắn mà một lần chạy
thật đã đòi.

## Mức chừa VRAM từng đếm trùng (sửa trong lúc alpha.32 chạy)

Log của alpha.32:

```
Pool TTS thu còn 2/3 worker cho 6029 MiB VRAM trống.
```

Ba worker chiếm 5.484 MiB, **vừa khít trong 6.029 MiB trống**, mà pool vẫn chỉ lấy hai.

Nguyên nhân là lỗi trong chính công thức tôi viết: `free_vram_mb` **đã** trừ phần desktop
đang giữ rồi, mà tôi còn trừ tiếp 800 MiB "chừa cho foreground". Tức là để không 800 MiB
*ngoài* phần người khác đã dùng - đếm trùng.

Nặng hơn: cấu hình đã đo là **ba worker giữ 5.484 trên 8.151 MiB**, tức chừa lại 2.667 MiB
cho mọi thứ khác. Một quy tắc từ chối chính cấu hình ấy mỗi khi desktop dùng quá ~1,9 GB
là **nghiêm khắc hơn cả phép đo sinh ra nó**.

Sửa: mức chừa tính trên **tổng dung lượng card**, còn phần trống là trần cứng.

| VRAM trống (card 8.151 MiB) | trước | sau |
|---:|---:|---:|
| 8.151 | 3 | 3 |
| 6.029 | **2** | **3** |
| 5.000 | 2 | 2 |
| 4.000 | 0 | 0 |

Máy không đọc được VRAM thì không có gì để chừa, nên dùng thẳng con số cấu hình - y như
trước khi phép đo này tồn tại.

## num_ctx 9.216 đắt hơn 7.168 16% một pha phân tích, và mua về đúng một lần guard (đo 2026-09-04)

Hai lần chạy cùng quyển sách, cùng model, khác mỗi `num_ctx`:

| | alpha.32 (ctx 7.168) | alpha.43 (ctx 9.216) |
|---|---|---|
| số lượt gọi | 418 | 424 (+1,4%) |
| token sinh ra | 197.263 | 202.411 (+2,6%) |
| **tốc độ sinh** | **56,4 tok/s** | **50,1 tok/s (−11%)** |
| nạp prompt | 5.045 tok/s | 4.827 tok/s |
| **pha phân tích** | **3.851s** | **4.490s (+16%)** |
| guard cắt prompt | 1 lần | 0 lần |

Số lượt gọi và số token gần như không đổi. Pha chậm đi vì **chính việc sinh token chậm đi
11%** - riêng nó giải thích 542s trong 639s chênh lệch. Ngữ cảnh rộng thêm 29% lấy đi 16%
của pha phân tích.

### Đổi lại được gì

Đúng một lần: ở 7.168, guard bắt được một prompt không vừa và **chia đôi batch** để chạy
lại. Đó là chuyện tốn khoảng mươi giây. **630 giây để tránh một lần chia batch là một cái
giá tồi** - tôi đã sửa quá tay.

Điều làm ngữ cảnh nhỏ trở nên an toàn không phải là ngữ cảnh lớn, mà là **cái guard**. Không
có nó, 7.168 hỏng âm thầm: Ollama cắt đầu prompt, trả JSON hợp lệ, checkpoint ghi nhận, và
không chỗ nào nói rằng model chưa từng nhìn thấy mấy segment đầu. Có nó, 7.168 hỏng thành
một lần chia batch nhìn thấy được. Cách suy luận đúng là **giữ guard và hạ num_ctx**, không
phải nâng num_ctx cho vừa trường hợp xấu nhất lý thuyết mà quyển sách này không bao giờ
chạm tới: prompt lớn nhất cả hai lần chạy đều là ~4.357 token.

### Cơ chế: **không phải giả thuyết** - dự án đã đo nó rồi

KV cache của qwen3:8b ≈ 36 lớp × 2 × 8 đầu × 128 chiều × 2 byte = 147.456 byte mỗi token,
tức 1,06 GB ở 7.168 và 1,36 GB ở 9.216 - hơn nhau **300 MB**. Trên card 8,15 GB đã chứa
model, 300 MB ấy đủ để đẩy một lớp xuống CPU, và một lớp qua PCIe mỗi token thì đúng là
kiểu chậm 11% mà không đổi số token. Và đây là chỗ tôi ghi sai lần đầu: tôi để mục này là "giả thuyết chưa kiểm" trong khi chính
docstring của `analysis_context_window` đã ghi cơ chế ấy, đo ở 16.384: *"model tràn xuống
CPU và phần sinh... chạy 25,6 token mỗi giây"*. Ghép lại thành ba điểm trên cùng một đường:

    num_ctx 16.384 ->  25,6 tok/s   (đo trước, trong docstring)
    num_ctx  9.216 ->  50,1 tok/s   (alpha.43)
    num_ctx  7.168 ->  56,4 tok/s   (alpha.32)

Cơ chế đã được xác lập từ trước; phép đo của tôi chỉ nối dài đường cong. **Lần thứ hai trong
một phiên tôi công bố một kết luận trước khi đọc phép đo đã nằm sẵn trong kho.**

### Suýt ghi ngược lại

Lần grep đầu tôi tìm chuỗi "cắt ngắn" trong khi guard in ra "cắt **bớt** phần đầu prompt",
nên nó báo alpha.32 có **0** lần cắt. Từ đó suy ra "9.216 chẳng mua được gì" - đúng kết
luận cuối cùng, nhưng bằng một lý do sai, và lý do sai ấy sẽ dẫn tới việc bỏ luôn cả guard.
Kiểm một con số 0 bằng cách đọc đúng chuỗi mà code thật sự in ra.

### Việc cần làm (chưa làm - `config.py` bị khoá lúc alpha.43 chạy)

Hạ `ANALYSIS_CONTEXT_*` để mức suy ra bám theo prompt quan sát được thay vì trần lý thuyết
của batch tên. Đây cũng chính là câu hỏi chủ sách đã đặt - *"project tưởng nó đang tự căn
chỉnh theo mức độ tài nguyên hiện có của máy mà?"* - áp vào ngữ cảnh: con số nên bám theo
việc thật, và guard là thứ khiến việc bám sát ấy an toàn.

## alpha.44 xác nhận: 7.168 **không kèm** cắt prompt (đo 2026-09-04)

Hạ `NAME_PRONUNCIATION_BATCH_SIZE` 20 → 12 để num_ctx suy ra về 7.168. Pha phân tích:

| | num_ctx | pha phân tích | lượt gọi | tốc độ sinh | guard cắt prompt |
|---|---|---|---|---|---|
| alpha.32 | 7.168 | 3.846s | 418 | 56,4 tok/s | **1 lần** |
| alpha.43 | 9.216 | 4.475s | 424 | 50,1 tok/s | 0 |
| **alpha.44** | **7.168** | **3.733s** | 418 | **57,6 tok/s** | **0** |

**Đúng thứ mà thay đổi này nhắm tới:** lấy tốc độ của 7.168 mà không lấy chỗ hỏng của nó.
alpha.32 ở cùng ngữ cảnh đã cắt prompt một lần; alpha.44 không lần nào, vì batch tên nhỏ hơn
xin ít token đầu ra hơn nên prompt vừa. Tiết kiệm **742s** so với alpha.43 - hơn mức 639s đã
dự đoán.

### Câu hỏi để mở đã có đáp án: batch tên nhỏ hơn **không** làm hỏng cách đọc

Docstring của hằng số ghi rõ là chưa đo: batch tên nhỏ hơn ảnh hưởng thế nào tới *chất lượng*
cách đọc. Số liệu batch 1:

| | cỡ batch 1 | thất bại → CMU | tỉ lệ |
|---|---|---|---|
| alpha.43 | 20 | 18 | 90% |
| alpha.44 | 12 | 12 | **100%** |

Tỉ lệ ấy **cao hơn**, và nó đã làm tôi lo nhầm. Khi pha chạy xong, tổng mới là con số đáng
tin:

| | cỡ batch | tên rơi về CMU | khoá được |
|---|---|---|---|
| alpha.43 | 20 | **18** | 112/112 |
| alpha.44 | 12 | **17** | 112/112 |

**Trung tính, nhỉnh hơn một chút.** Cả hai đều khoá đủ 112 tên. Tỉ lệ batch 1 là ảo ảnh:
batch 1 chứa đúng những tên khó ở cả hai lần chạy (`Apex`, `Arthur Kaizer Theosbane`, `Card`,
`Debuff`...), nên batch nhỏ hơn chỉ dồn chúng đặc hơn chứ không tạo thêm chỗ hỏng. Tỉ lệ
theo từng batch không nói lên điều gì khi thành phần batch tự nó đã lệch.

Vậy thay đổi này **được 742s mà không trả giá gì**: không cắt prompt, không mất chất lượng
cách đọc.

(Và một lần suýt báo sai nữa: tôi đọc "không có dòng `còn N tên lỗi sau lần 3`" thành "không
tên nào lỗi", trong khi pha ấy **đang chạy dở** và batch 1 đã có 12 tên rơi về CMU. Đừng đọc
sự vắng mặt của một dòng log như một kết quả khi việc chưa xong.)

## Nền nhiễu của phân tích: 3,1% — và num_ctx nhân nó lên bốn lần (đo 2026-09-04)

alpha.44 cho thứ mà hai lần chạy trước không cho được: **một biến kiểm**. alpha.32 và
alpha.44 chạy cùng `num_ctx = 7.168`; alpha.43 chạy 9.216. So chỉ dẫn diễn xuất
(`pace`/`emotion`/`intensity`/`kind`) trên cả 948 segment:

| so sánh | khác nhau |
|---|---|
| alpha.32 ↔ alpha.44 (**cùng 7.168**) | **3,1%** ← nền nhiễu |
| alpha.32 ↔ alpha.43 (7.168 vs 9.216) | **11,5%** |
| alpha.43 ↔ alpha.44 (9.216 vs 7.168) | 10,7% |

**Phân tích không tất định.** Hai lần chạy cùng cấu hình vẫn lệch 3,1% - suy luận LLM không
tái lập theo từng bit, và việc chia batch cũng lệch chút ít. Đó là **sàn** của mọi phép so
sánh giữa hai lần chạy trong dự án này.

> **Sàn ấy đã cũ, đo lại 2026-09-07: nó là 0%.** So `speaker` của cả 948 đoạn giữa alpha.48
> và alpha.51 — hai lần chạy **liền mạch**, cách nhau nhiều giờ và **ba bản sửa code** — cho
> **0 đoạn lệch**, và cùng 23 nhân vật, cùng casting không lệch một đoạn.
>
> Nên phân tích **có** tất định, và mọi phép so giữa hai lần chạy trong dự án này nhạy hơn
> con số 3,1% ở trên rất nhiều: một đoạn lệch là một tín hiệu, không phải nhiễu.
>
> Không rõ vì sao số cũ là 3,1% — có thể một trong các lần chạy ấy đã bị ngắt (xem
> `VERSIONS.md`: một lần `stop`/`resume` giữa pha phân tích làm lệch 18 đoạn và mất 4 nhân
> vật), hoặc phân tích hồi đó chưa được gieo seed theo nội dung. **Đừng suy; nếu cần con số,
> đo lại bằng hai lần chạy liền mạch.**

**Đổi num_ctx làm lệch 11,5%**, và với sàn thật là 0% thì **cả 11,5% ấy là do num_ctx**,
không phải 11,5% trừ đi một nền nhiễu 3,1%. Kết luận cũ ("nhân sàn lên bốn lần") đọc sai
theo hướng làm nhẹ đi: hiệu ứng lớn hơn những gì nó nói.

11,5% ấy khớp gần khít với 11,3% segment có *âm thanh khác* đã đo giữa alpha.32 và alpha.43
(107/944). Chuỗi nhân quả vì thế khép lại: **ngữ cảnh → chỉ dẫn diễn xuất → âm thanh →
kết cục.** Sàn 0% làm chuỗi này *chặt hơn*, vì không còn phần dư nào để đổ cho nhiễu.

### Thấy được ở hai segment cụ thể

| segment | alpha.32 | alpha.43 (9.216) | alpha.44 |
|---|---|---|---|
| `c00007_s0000074` Juliana | normal/neutral/0 | **fast/afraid/2** → mất audio | **normal/neutral/0** |
| `c00006_s0000001` tiếng gào | fast/angry/3 | **normal/neutral/0** → chặn ch6 | **fast/angry/3** |

Cả hai segment từng làm hỏng một chương ở alpha.43 đều **quay về đúng cách đọc của
alpha.32** khi ngữ cảnh trở lại 7.168.

### Hệ quả cho cách đọc mọi phép so sánh trước đó

Bất kỳ khác biệt nào dưới ~3% giữa hai lần chạy **không phải bằng chứng của gì cả**. Điều
này không lật kết luận nào đã ghi - 1,6% bản ghi khác nhau trên *cùng một file âm thanh* vẫn
đứng, vì phép đo ấy so cùng một audio nên không dính nhiễu phân tích - nhưng nó đặt lại
thước cho những so sánh ở mức chương và mức cảnh báo, nơi con số nhỏ dễ bị đọc thành xu
hướng.

### Trục trôi dạt thứ hai: đúc vai - và chương 6 của alpha.44 là nhiễu, không phải công của thay đổi nào

alpha.44 lấy lại chương 6 mà alpha.43 đánh mất, và lấy lại đẹp: segment tiếng gào ra
`verified`, similarity **1,00**, không mã cảnh báo - trong khi alpha.32 xuất bản chính chương
ấy nhờ một bản ghi **ảo giác được miễn trừ**. Rất dễ ghi công cho `max_retries` hoặc engine.
Cả hai đều không phải.

Truy ra thì lý do nằm ở chỗ khác:

    alpha.32: voice=14  speaker="…người bị bắt"      pitch=-4  sha=cea8dd10
    alpha.44: voice=16  speaker="…người bị bắt nạt"  pitch=0   sha=a1492959

Phân tích **nhận diện nhân vật khác đi** - "người bị bắt" so với "người bị bắt nạt" - nên
đúc giọng khác, pitch khác, seed khác, âm thanh khác, và bản mới tình cờ được Whisper nghe
đúng hoàn toàn. Cả hai đều là bản `primary`, không candidate nào, nên vòng sửa không dính
dáng gì.

Đo trục ấy trên cả sách:

| | speaker khác | giọng khác |
|---|---|---|
| alpha.32 ↔ alpha.44 (**cùng 7.168**) | **1,8%** | **2,4%** |
| alpha.32 ↔ alpha.43 (7.168 vs 9.216) | 9,0% | 6,1% |

Cùng hình dạng với trôi dạt chỉ dẫn (3,1% cùng ctx, 11,5% khác ctx). **Nền nhiễu của phân
tích không chỉ là chỉ dẫn diễn xuất - nó gồm cả việc đúc vai**, và chương 6 rơi đúng vào
2,4% ấy.

**Hệ quả cho cách đọc kết quả alpha.44:** chênh lệch một hai chương giữa các lần chạy nằm
trong nhiễu. Muốn quy cho một thay đổi cụ thể thì phải truy tới từng segment và chỉ ra cơ
chế - như đã làm cho `c00005_s0000013` (cứu thật, do `max_retries`) và cho chương 6 này (may,
do đúc vai). Đếm chương không đủ.

### Đo lại nền nhiễu với cặp thứ ba: 3,1% là cặp may, không phải sàn (06/09/2026)

alpha.46 chạy `num_ctx = 7.168`, cùng model, cùng `batch_segments`/`batch_chars`/
`temperature`/`max_retries`/`retry_policy_version` với alpha.32 và alpha.44 — đã đối chiếu
từng trường trong `settings_json` của cả ba project. Nên giờ có **ba** cặp cùng cấu hình chứ
không phải một.

Đo lại đúng bốn trường `pace`/`emotion`/`intensity`/`kind` như phép đo gốc. Ba con số cũ tái
lập chính xác, nên phương pháp là một:

| cặp | khác nhau | |
|---|---|---|
| alpha.32 ↔ alpha.44 | **3,1%** | cùng cấu hình |
| alpha.44 ↔ alpha.46 | **6,2%** | cùng cấu hình |
| alpha.32 ↔ alpha.46 | **7,4%** | cùng cấu hình |
| alpha.43 ↔ alpha.46 | 9,1% | 9.216 vs 7.168 |
| alpha.43 ↔ alpha.44 | 10,7% | 9.216 vs 7.168 |
| alpha.32 ↔ alpha.43 | 11,5% | 7.168 vs 9.216 |

**Hai kết luận cũ phải sửa.**

1. **Nền nhiễu không phải 3,1%.** Ba cặp cùng cấu hình trải từ 3,1% đến 7,4%. Con số 3,1%
   là cặp thấp nhất, và mục ở trên gọi nó là "sàn của mọi phép so sánh". Dùng 3,1% làm ngưỡng
   thì một khác biệt 6% giữa hai lần chạy cùng cấu hình sẽ bị đọc nhầm thành hiệu ứng thật.
   Ngưỡng an toàn là **~7,4%**, tức cặp cao nhất đã quan sát được.

2. **`num_ctx` không nhân nhiễu lên bốn lần.** Ba cặp khác ctx trải 9,1–11,5% (trung bình
   10,4%); ba cặp cùng ctx trải 3,1–7,4% (trung bình 5,6%). Tỉ số là **~1,9 lần**, không phải
   4. Con số "bốn lần" ra đời từ việc so 11,5% với đúng cặp cùng-cấu-hình thấp nhất.

`num_ctx` **vẫn** làm lệch nhiều hơn cùng cấu hình — kết luận định tính không đổi, chỉ độ lớn
bị thổi lên. Nhưng khoảng của hai nhóm nay **chồng lấn** (7,4% so với 9,1%), nên một cặp lẻ
không còn phân biệt được hai nguyên nhân nữa.

> Bài học chung: một hằng số rút ra từ **một** cặp quan sát là một mẫu, không phải một sàn.
> Có ba cặp thì nó tăng gấp đôi.
