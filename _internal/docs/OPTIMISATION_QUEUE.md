# Hàng đợi tối ưu đã đo, xếp theo giá trị

Mỗi mục dưới đây có một con số đo được đứng sau, và mỗi mục đều **chưa ship** vì
`QUALITY_IMPLEMENTATION_FILES` bị khoá trong lúc alpha.43 chạy. Tài liệu này tồn tại vì các
mục ấy **ảnh hưởng lẫn nhau**: làm mục 1 xong thì mục 2 phải giữ nguyên phạm vi hẹp, và làm
mục 2 sai phạm vi thì mục 1 mất phần lớn giá trị.

Nền để so: alpha.32 tốn ~15.600 giây công việc đo được sau pha phân tích, cộng ~3.850 giây
pha phân tích.

**Nền ấy đã dịch.** faster-whisper (đã ship, alpha.43 đang chạy) lấy đi khoảng 3.400s của hai
pha ASR, nên phần việc sau phân tích còn khoảng **12.200s**. Điều đó không làm mục nào rẻ đi
- nó làm mục 1 **đắt hơn về tỉ trọng**: 4.707s trên 12.200s là **39% phần việc còn lại**
(dù phần *lấy lại được* của nó chỉ ~905s, xem mục 1).
Xem `docs/WHERE_A_RUN_SPENDS_ITS_TIME.md` cho phép đo và biến kiểm của nó.

---

## Làm cái nào trước

Xếp theo giá trị thì mục 1 đứng đầu, nhưng xếp theo **giá trị chia cho rủi ro** thì mục 3
mới nên làm trước:

| mục | lấy lại | file phải sửa | hình dạng thay đổi |
|---|---|---|---|
| 3. hạ `num_ctx` | ~639s pha phân tích | `config.py` | **một hằng số** |
| 4. `tts.max_retries` 4→10 | chất lượng: cứu 2 segment | `config.py` | **một hằng số** |
| 1. pool vòng candidate | ~905s | `pipeline.py` | thêm một đường prefetch |
| 2. Whisper thường trú | ~230s | `pipeline.py`, `asr.py` | đổi vòng đời model |

Mục 3 và 4 là đổi số, xác minh lại bằng chính lần chạy kế tiếp. Mục 1 đáng làm nhất về con
số nhưng động vào vòng sửa - nơi đã sinh ra bốn lần sập cùng một họ (xem `WORK_LOG.md`).
Làm 3 và 4 trước, đo lại, rồi mới tới 1.

---

## 1. Cho vòng sinh candidate dùng pool — ~905s, tức ~7,4% một lần chạy

`pipeline.py` sinh candidate clarity bằng vòng lặp thẳng, trong khi đường tổng hợp chính
dùng `_synthesis_pool`. Đó là **pha tốn nhất cả lần chạy**: 4.707s, 826 việc, 5,45s mỗi
việc. Lấy mẫu GPU giữa lúc ấy: **23,7% trung bình, VRAM đỉnh 2.719/8.151 MiB.**

**Ước lượng đầu của tôi ở đây sai 3,5 lần và đã sửa.** Tôi lấy "3 tiến trình" làm mức tăng
tốc, tức 4.707s → ~1.570s. Nhưng chính dự án đã đo pool rồi, và con số nằm ngay trong
docstring của `TTS_POOL_MIN_BATCH`: **2 đoạn 1,00×, 3 đoạn 1,12×, 4 đoạn 1,22×, 9 đoạn
1,29×**. Tổng hợp TTS không giãn tuyến tính theo số worker vì 3 worker đã đẩy GPU lên 90%.

Ghép đường cong ấy với kích thước vòng thật (129 vòng, trung vị **5** candidate):

    tuần tự : 4.707s
    có pool : ~3.802s      tiết kiệm ~905s = 19,2% của pha, **7,4% một lần chạy**

Vẫn là mục lớn nhất hàng đợi, nhưng bằng một nửa con số tôi viết lần đầu. Bài học: phép đo
đã có sẵn trong kho, trong một docstring, và tôi công bố ước lượng trước khi đọc nó.

`TTS_POOL_MIN_BATCH = 3` nên 36/129 vòng (7,4% candidate) vẫn chạy tuần tự - đã tính vào
con số trên.

Chi tiết và cảnh báo về cách quy thời gian: `docs/THROUGHPUT.md`.

## 2. Giữ Whisper thường trú **trong vòng sửa** — ~230s (đã hạ từ ~1.400s)

**Đo lại sau khi đổi engine thì mục này nhỏ đi sáu lần.** Whisper vẫn được nạp **189
lần** mỗi lần chạy, nhưng openai-whisper mất 7,15s mỗi lần (1.502s = 9,6% công việc) còn
faster-whisper chỉ mất **1,31s** (~248s = 1,6%). alpha.43 đang chạy engine mới, nên nền để
tính là 1,6% chứ không phải 9,6%.
129 lần rơi vào lúc vào pha kiểm candidate: vòng sửa xen kẽ TTS và ASR, hai model đá nhau
ra khỏi VRAM mỗi vòng — 7 giây nạp cho 5 giây việc.

**Phạm vi vẫn là thứ làm mục này đúng, và giờ nó còn phải rẻ nữa.** Trong vòng sửa, VRAM
đỉnh chỉ 2.719 MiB nên 1,5 GB của Whisper là miễn phí. Ngoài vòng sửa thì không: 1,5 GB ấy lấy mất một tiến trình pool ở pha
tổng hợp chính (2.658s ở 3 tiến trình → ~3.987s ở 2), gần đúng bằng phần tiết kiệm. **Và
nếu mục 1 đã làm xong thì đánh đổi ấy còn tệ hơn** — pool càng quan trọng thì càng không
được lấy VRAM của nó.

## 3. Hạ `num_ctx` về ~7.168 — ~16% pha phân tích

alpha.32 ở 7.168 chạy pha phân tích trong 3.851s; alpha.43 ở 9.216 mất 4.490s. Số lượt gọi
và số token gần như không đổi (+1,4% và +2,6%); **tốc độ sinh tụt 56,4 → 50,1 tok/s**, riêng
nó giải thích 542s trong 639s chênh lệch.

Đổi lại được đúng một lần guard cắt prompt. Cái làm ngữ cảnh nhỏ an toàn là **guard**, không
phải ngữ cảnh lớn — guard biến một lần hỏng âm thầm thành một lần chia batch nhìn thấy được.
**Giữ guard, hạ num_ctx.** Chi tiết: `docs/VRAM_AND_CONTEXT.md`.

## 4. Nâng `tts.max_retries` 4 → 10 — cứu 2 trong 3 segment không có audio

Không phải tối ưu tốc độ, mà là chất lượng. Hai segment trượt cổng nhịp vì **hết lượt**,
không phải vì giọng không đọc nổi: một cái trượt 0,03 ký tự/s. Ở ngân sách 10 chúng qua với
xác suất 88% và 73%. Giá: cả sách chỉ 3 segment chạm ngân sách, nên ~18 lượt tổng hợp thêm.

Segment thứ ba (`C » B » A » S » SS » SSS`) ngoài tầm với ở mọi ngân sách và **không được
nới cận dưới vì nó** — 807 segment đã nhận, không cái nào dưới 12.5. Chi tiết:
`docs/PACE_METRIC.md`.

---

## Đã có script, chưa chạy (cần máy rảnh, không có lần chạy nào đang bay)

- `scripts/measure_ollama_parallel.py` — pha phân tích gửi 424 request tuần tự; sinh token
  bị chặn bởi băng thông bộ nhớ nên gộp request có thể tăng thông lượng gộp. Đo trước, và
  đo cả VRAM: mỗi chỗ song song cần một KV cache riêng.
- `scripts/measure_concurrent_asr.py` — giữ một lời gọi mỗi segment (không trộn ranh giới
  bản ghi) nhưng chạy nhiều lời gọi cùng lúc. Cột "bản ghi khác" phải bằng 0.

## Đã đo và **bác bỏ** — đừng làm lại

- **Gộp lô ASR**: 1,11× chứ không phải 3-5×. Lý do đã biết: `BatchedInferencePipeline` gộp
  các cửa sổ *trong một file*, không gộp giữa các file.
- **Gói nhiều segment vào một cửa sổ 30 giây**: đúng về mặt số học (encoder tính tiền theo
  cửa sổ, 84% mỗi cửa sổ là đệm, ~16% ASR) nhưng nó trộn ranh giới bản ghi mà neo tên khoá,
  kiểm dòng thời gian ảo giác và similarity từng segment đều dựa vào. Không phải một tối ưu.
- **Tối ưu việc nạp audio**: 0,7% chi phí giải mã. Bỏ qua.
- **Bỏ chú thích tiếng Anh trong ngoặc**, và **"chú thích dài mới hỏng"**: cả hai đều bị số
  liệu bác. `docs/` và `scripts/english_gloss_risk.py`.
