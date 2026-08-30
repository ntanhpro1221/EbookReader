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

### `pace` không tới được audio — nhưng đo xong thì thấy chưa đáng sửa

`vieneu_sampling_for_segment` ánh xạ `pace` thành đúng hai thứ: lệch temperature `±0,03/0,04` và
`silence_p` (`slow 0,20 / normal 0,15 / fast 0,08`). Không có tham số tốc độ đọc nào cả — thư viện Python
của VieNeu không có (xem `DEPENDENCIES.md`). Đo trên 104 segment có audio:

| pace | n | articulation (âm tiết/s) | tỉ lệ lặng |
|---|---|---|---|
| fast | 4 | 5,41 | 20% |
| normal | 98 | 5,29 | 19% |
| slow | 2 | **5,60** | 23% |

`slow` đọc **nhanh hơn** `normal`. Quyết định `pace` của đạo diễn bị vứt đi.

**Nhưng chưa sửa, vì phân bố nói khác.** Trên toàn bộ 199 segment đã phân tích: `pace` là
**193 normal / 4 fast / 2 slow — 97% normal**. Hiện thực hóa `pace` bằng hậu xử lý tempo sẽ chạm tới
**3% segment**, trong khi lỗi loudness ở trên chạm tới **77%**. Xây hạ tầng tempo bất biến (candidate riêng,
provenance, dual-decode, test) cho một ca 3% là đặt sai chỗ công sức.

Ghi lại để người sau cân nhắc: khác với `emotion`, **`pace` và `volume` không có host gate tất định**.
Prompt có dặn "không mặc định mọi câu là normal", nhưng không có gì kiểm chứng. `emotion=neutral` bị từ chối
46 lần trong lần chạy này; `pace=normal` thì chưa bao giờ bị chất vấn. 97% có thể đúng với văn xuôi kể chuyện —
người đọc audiobook thật cũng không đổi nhịp liên tục — nên đừng ép nó đa dạng khi chưa có bằng chứng là nó sai.
Muốn kết luận thì phải nghe đối chiếu, không phải nhìn phân bố.

Phân bố các quyết định delivery khác trong cùng lần chạy, để tham chiếu:
`volume` 177 normal / 20 loud / 2 soft; `emotion` 143 neutral / 19 angry / 16 afraid / 9 sad / 6 surprised /
4 tired / 2 happy; `intensity` 106 số 0 / 42 số 1 / 39 số 2 / 12 số 3.

### Kết quả cuối lần chạy alpha.9: 15/199 segment fail, 0/2 chapter publish

| | |
|---|---|
| Segment đạt | 184 / 199 |
| Segment fail | 15 — **tất cả** đều `ASR_LOCKED_NAME_ANCHOR_MISMATCH` |
| Chapter publish | **0 / 2** |

#### Anchor tên riêng đang từ chối chính cách đọc đúng

Đọc evidence của cả 15 segment (bản `locked_spoken_v1` cuối cùng), 23 anchor trượt:

| surface | đọc là | Whisper nghe | đánh giá |
|---|---|---|---|
| Joel | Giô-en | `joanne` ×5 | TTS đúng, Whisper viết bằng chữ Latinh |
| Lucien | Lu-si-en | `lucienne`, `lucianne` | TTS đúng |
| Iven | Ai-vân | `ivan` ×3 | TTS đúng |
| Alisa | A-li-sa | `alyssa` ×2 | TTS đúng |
| John | Giôn | `dôn`, `dốn` | TTS đúng — `gi` và `d` **đồng âm** /z/ trong tiếng Việt |
| Wayne | Uên | `nè`, `warner` | lỗi thật |
| Lucien | Lu-si-en | `rusien` | lỗi thật |
| Alisa | A-li-sa | `xá` | lỗi thật |

Khoảng **13/23 là từ chối nhầm**. Nguyên nhân gốc là **sai lệch dụng cụ đo**: gate so *chính tả*
mà Whisper chọn cho một cái tên ngoại quốc đọc theo âm Việt, trong khi Whisper là model đa ngữ có
thiên lệch tiếng Anh nên viết lại thành tên tiếng Anh. Chính tả của Whisper **không phải bằng chứng
về cách phát âm**.

Hệ quả với sản phẩm: 7,5% segment fail, và chỉ cần một segment fail là cả chapter bị giữ lại. Với
915 chapter thì **không chapter nào từng được publish**. Đây là blocker số 1, trên cả lỗi loudness.

Bằng chứng cho thấy `Aalto`, `Alisa` khớp ổn định ở `locked_spoken_v1`; chuyển sang variant
`source_spelling_v1` thì chính chúng lại trượt (`An-tô` bị đòi phải nghe ra `aalto`). Nghĩa là nhánh
repair đổi variant đang làm tình hình xấu đi chứ không cứu được.

#### Lỗi rõ ràng, không cần bàn: cùng một tên có hai cách đọc đã khóa

| surface | spoken_form |
|---|---|
| `Lucien` | `Lu-si-en` |
| `Evans` | `E-vân` |
| `Lucien Evans` | `Lư-xi-ên Ê-van` |

Entry nhiều từ tạo ra cách đọc khác hẳn cho chính hai tên đó (`u`→`ư`, `si`→`xi`, `en`→`ên`).
Đã xác nhận nó thực sự được áp dụng vào `spoken_text`. Người nghe sẽ nghe cùng một nhân vật được gọi
là "Lu-si-en" ở chương này và "Lư-xi-ên" ở chương khác. Vi phạm thẳng invariant *"cùng một tên không
đổi cách đọc theo giọng, chapter, confidence threshold hoặc lần resume"*.

#### Bài học quy trình

**Không di chuyển thư mục project.** SQLite lưu đường dẫn WAV tuyệt đối; chuyển đi là mọi công cụ
audit mất dấu file. Từ alpha.10, tạo project thẳng trong `_versions/<tag>/` bằng `--output-root`.

**Output:** `D:\Novels\Audiobooks\texttmp_iter1_cbde22ef6b` (chapter 000–001).
