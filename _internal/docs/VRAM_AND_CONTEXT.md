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
