# Nhật ký phiên bản

Mỗi phiên bản là một tag Git kèm một lần chạy thật trên chapter thuộc `Text_Tmp`. Mục đích của file này là
để người tiếp theo biết **tại sao** một thay đổi được thực hiện và **bằng chứng nào** dẫn tới nó, chứ không
chỉ là danh sách commit.

## Quy ước

- Tag: `v<major>.<minor>.<patch>-alpha.<n>`, khớp với `version` trong `_internal/pyproject.toml`
  (pyproject luôn mang số của phiên bản **đang phát triển**, tag mang số của phiên bản **đã phát hành**).
- Output của từng phiên bản nằm ngoài repo, tại `D:\Novels\Audiobooks\_versions\<tag>\`.
  Audio và SQLite **không bao giờ được commit** — chúng chỉ để nghe lại và đối chiếu.
- Một phiên bản **không cần chạy hết**. Đọc log và chấm audio ngay khi có segment đầu tiên;
  thấy lỗi hệ thống thì dừng, sửa, tạo project sạch và chạy lại.
- Mọi thay đổi hành vi phải cập nhật `AGENTS.md` (invariant) và/hoặc `README.md` (hành vi người dùng thấy)
  trong cùng commit.

## Cách chạy một phiên bản

```bash
cd _internal
./runtime/.venv/Scripts/python.exe -m ebook_reader.cli create \
  --output-root "D:/Novels/Audiobooks/_versions/<tag>" \
  --source-dir "D:/Novels/Ebook Reader/Text_Tmp" \
  --range "000..001" --width 3 --title "<tag>" --profile high_quality --json
./runtime/.venv/Scripts/python.exe scripts/run_book_job.py "<project-root>"
```

Chấm giữa chừng, không cần đợi xong:

```bash
./runtime/.venv/Scripts/python.exe scripts/audit_audiobook.py "<project-root>"
```

---

## v0.2.0-alpha.9 — chịu được lỗi mạng Ollama, có công cụ chấm audio

**Bằng chứng dẫn tới thay đổi.** Lần chạy đầu tiên trên `Text_Tmp/000..007` chết ở
`stage=unrecoverable_error` với `last_error="Response ended prematurely"` sau khi mới phân tích được
2/805 segment. Đây là `ChunkedEncodingError` của urllib3: kết nối tới Ollama rớt giữa stream. Một sự cố
mạng thoáng qua đã giết cả job không người trông — đúng thứ mà một studio audiobook không được phép có.

**Thay đổi.**

- `analysis.py` chia lỗi Ollama thành hai lớp. Kết nối chết **trước khi nhận được ký tự response nào**
  là replay an toàn và được gửi lại tối đa `OLLAMA_TRANSPORT_RECONNECT_ATTEMPTS` lần. Stream đã sinh
  output thì không bao giờ replay.
- Transport fault vượt qua lớp replay trong một attempt critic đã reserve giờ tiêu đúng attempt đó
  (giống hệt crash sau reserve), ghi `ANALYSIS_CRITIC_TRANSPORT_FAULT`, rồi để vòng lặp durable đi tiếp.
  Ngân sách attempt vẫn chặn vòng lặp vô hạn và hết ngân sách vẫn rơi vào nhánh terminal/split cũ.
- `scripts/run_book_job.py` được đưa ra khỏi `runtime/` (thư mục bị gitignore) và reconfigure stdout sang
  UTF-8. Trước đó thread drain message chết ngay ở dòng log tiếng Việt đầu tiên vì stdout mặc định cp1252.
- Thêm `scripts/audit_audiobook.py`: chấm khách quan phần mà gate per-segment không nhìn thấy — độ tản
  tốc độ đọc trong chương, khoảng lặng **thực tế nghe được** ở mỗi mối nối, độ đồng đều loudness giữa
  narration và dialogue, và tính nhất quán voice/pitch theo nhân vật.

**Đã biết, chưa xử lý.** `AnalysisOutputBudgetError`, `AnalysisWallTimeoutError` và
`OllamaStreamIncompleteError` phát sinh **trong** lượt critic bền vẫn raise xuyên pipeline. Ngữ nghĩa
durable của chúng giống hệt transport fault (attempt đã bị tiêu), nên nhiều khả năng chúng cũng nên đi
tiếp thay vì kết thúc book. Chưa sửa vì chưa quan sát được trường hợp thật; đừng sửa mù, hãy đợi bằng chứng
từ một lần chạy.

### Số liệu đo được trong lần chạy alpha.9

Trên 29 batch đầu của chapter 000–001:

- **72% batch phải retry ít nhất một lần** (8 batch qua ngay, 14 batch cần 2 lượt, 7 batch cần cả 3 lượt).
- 46/53 lần từ chối đến từ `semantic delivery validation` — model đề xuất `emotion=neutral` cho câu có
  cue cảm xúc trực tiếp; 4 lần từ host affect adjudication, 3 lần từ director critic.
- Nghĩa là phân tích đang tốn khoảng **2,1× số lời gọi model** so với trường hợp lý tưởng.

**Đây là chi phí có chủ đích, đừng "tối ưu" nó đi.** Cách rẻ nhất để giảm retry là gửi sẵn cue mà host đã
phát hiện được vào prompt lần đầu. Nhưng làm vậy thì semantic gate không còn là một phép kiểm độc lập —
nó biến thành "model có làm theo gợi ý của host không". Giá trị của gate nằm ở chỗ model tự quyết rồi host
đối chiếu. `AGENTS.md` đã quy định: khi throughput xung đột với toàn vẹn output thì chọn toàn vẹn output.
Advisory `allowed_emotions` vì thế chỉ được gửi **sau** khi một candidate `neutral` bị từ chối.

Con số cần nhớ khi ước lượng thời gian: ở profile `high_quality`, phân tích chạy khoảng **4 segment/phút**
trên RTX 5060 Laptop với `qwen3:8b` (~24 token/s, GPU ~47%, VRAM 6,5/8 GB).

### Phát hiện chất lượng: peak cap đang vô hiệu hóa toàn bộ ý đồ loudness

Đo 107 segment đã commit của chapter 000–001:

| | |
|---|---|
| Segment chạm trần peak `-2 dBFS` | **82/107 = 77%** |
| Lệch trung bình so với target LUFS | **-1,22 dB** |
| Lệch xấu nhất | **-4,09 dB** |
| Crest factor (peak − LUFS) | median 17,6 dB · p95 19,7 dB · max 20,6 dB |

`normalize_segment_level` tính `gain = min(desired_gain, peak_safe_gain)`. Target segment hiện tại
(`normal -19,0`, `loud -17,8`, narrator `+0,5`) nằm quá sát trần peak `-2 dBFS`, trong khi crest factor
tự nhiên của giọng nói là 17–20 dB. Hệ quả: **peak cap thắng, và mức cuối của mỗi segment do crest factor
quyết định chứ không do quyết định của đạo diễn.**

Hậu quả nghe được, không chỉ là sai số:

- Hai segment `volume=loud` (target `-17,30`) ra `-19,41` và `-20,21` — **nhỏ hơn** narration `volume=normal`
  ở `-19,14`. Quyết định "đọc to hơn" tạo ra audio nhỏ hơn.
- Anchor `segment_narrator_offset_db = 0,5` bị xoá sạch.
- Loudness giữa các segment tản `3,04 LU` vì lý do không liên quan gì tới nội dung.

Vì chương được master lại về `-18 LUFS` ở cuối, **chỉ tương quan giữa các segment mới quan trọng**. Nên cách
sửa đúng là hạ đều toàn bộ anchor cho tới khi peak cap không còn chạm: mô phỏng cho thấy `-4 dB` đưa
99,1% segment về đúng target, `-5 dB` đưa 100%.

**Đã kiểm chứng trước khi chọn cách sửa:** UTMOSv2 gần như bất biến với mức âm lượng tuyệt đối. Hạ
`-2/-4/-6 dB` trên 8 segment cho lệch MOS trung bình `-0,008/-0,009/-0,006`, xấu nhất `-0,032` — so với
ngưỡng review `-0,8`. Nghĩa là hạ anchor **không** phải trả giá bằng điểm tự nhiên, nên không cần đụng tới
limiter hay nén động (vốn sẽ làm méo waveform).

**Cần đo tiếp trước khi sửa:** cùng ràng buộc vật lý đó có thể tái xuất hiện ở tầng master chương —
`-18 LUFS` với true peak `-2 dBTP` đòi crest factor ≤ 16 dB, thấp hơn crest thực tế của giọng nói.
Phải đo MP3 chương thật rồi mới chốt.

**Output:** `D:\Novels\Audiobooks\texttmp_iter1_cbde22ef6b` (chapter 000–001).
