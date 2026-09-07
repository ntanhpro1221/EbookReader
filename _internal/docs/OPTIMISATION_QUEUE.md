# Hàng đợi tối ưu đã đo, xếp theo giá trị

Mỗi mục dưới đây có một con số đo được đứng sau. Trạng thái ship ghi ở **từng mục** —
câu "mỗi mục đều chưa ship" ở bản đầu đã cũ từ lúc mục 3 lên tàu; đừng tin phần mở đầu,
đọc mục. Tài liệu này tồn tại vì các
mục ấy **ảnh hưởng lẫn nhau**: làm mục 1 xong thì mục 2 phải giữ nguyên phạm vi hẹp, và làm
mục 2 sai phạm vi thì mục 1 mất phần lớn giá trị.

Nền để so: alpha.32 tốn ~15.600 giây công việc đo được sau pha phân tích, cộng ~3.850 giây
pha phân tích.

**Nền ấy đã dịch.** faster-whisper (đã ship, alpha.43 đang chạy) lấy đi khoảng 3.400s của hai
pha ASR, nên phần việc sau phân tích còn khoảng **12.200s**. Điều đó không làm mục nào rẻ đi
- nó làm mục 1 **đắt hơn về tỉ trọng**: 4.707s trên 12.200s là **39% phần việc còn lại**
(dù phần *lấy lại được* của nó chỉ ~905s, xem mục 1).
Xem `docs/WHERE_A_RUN_SPENDS_ITS_TIME.md` cho phép đo và biến kiểm của nó.


## Trạng thái sau phiên 2026-09-04 (chuẩn bị alpha.44)

Chủ sách chọn: **giữ chú thích tiếng Anh**, **lùi dải nhịp về `normal` kèm cảnh báo**,
**đợi alpha.44 rồi nghe một lần**. Đã ship:

| | thay đổi | commit |
|---|---|---|
| ✅ | Tách sentinel khỏi `max_retries` (dùng `generation_strategy`) | `303e5c9` |
| ✅ | `tts.max_retries` 4 → 10 | `6278c2e` |
| ✅ | `NAME_PRONUNCIATION_BATCH_SIZE` 20 → 12 → `num_ctx` 7.168 | `6278c2e` |
| ✅ | Lùi dải nhịp về `normal` + `TTS_PACE_BAND_RELAXED` | `aef4f20` |
| ✅ | `asr.engine` mặc định `faster`, khai báo dependency, cấm tải giữa chừng | `5fcb06e` |
| 🔧 | **Mục 1 (pool vòng candidate)** — đã code + test xong trên `dev/alpha13`, **chưa merge** | `ab5d025` |

**Vì sao hoãn mục 1.** Năm thay đổi trên đều đổi fingerprint, nên alpha.44 phải xác minh cả
năm cùng lúc. Thêm mục rủi ro nhất — sửa đúng vòng đã sinh ra bốn lần sập cùng một họ — thì
nếu alpha.44 có gì lạ sẽ **không quy trách nhiệm được**. Đây cũng chính là thứ tự tài liệu
này tự đề ra ở mục "Làm cái nào trước": làm hằng số trước, đo lại, rồi mới tới thay đổi cấu
trúc. Làm mục 1 sau alpha.44, với một nền sạch để đo. **Đã viết xong và test xong** trong lúc
alpha.44 chạy (nhánh dev, production không đụng tới), nên chỉ còn việc merge và chạy alpha.45
khi alpha.44 cho xong con số của nó.

Test của nó được kiểm bằng **đột biến**: cố tình đưa lại lỗi "một prefix cho cả lô" thì 4
test đỏ, hoàn nguyên thì cả 15 xanh. Bản test đầu tiên của tôi so
`_segment_candidate_seed_salt` với chính nó - chứng minh hàm tất định, và không nói gì về
việc hai phía có khớp nhau không. Một test trông như phủ đúng cái bẫy mà nó không phủ.

Mục 2 (Whisper thường trú) giá trị đã tụt còn ~230s sau khi đổi engine — để sau mục 1.
Mục 5 (ngưỡng perceptual theo sigma) vẫn chờ phép đo phân giải nhiễu-hay-thật.

---

---

## MỐC MỚI, đo trên alpha.53 — lượt chạy sạch, không cảm thụ (2026-09-07)

Đo bằng `scripts/phase_timings.py`. **Dùng bảng này, đừng dùng các phần trăm cũ bên dưới.**

| khoản | giây | tỷ trọng công việc đo được |
|---|---|---|
| phân tích | 3.828 | 45% |
| TTS | 2.267 | 27% |
| ngoài TTS (Whisper + MP3) | 784 | 9% |
| **vòng sửa candidate** | **1.538** | **18%** |
| — sinh candidate | 1.168 | |
| — kiểm candidate | 370 | |
| tổng | 8.417 | (đồng hồ thật 161 phút) |

**Điều tắt cảm thụ thật sự lấy đi**, so với số liệu alpha.51:

| | alpha.51 | alpha.53 |
|---|---|---|
| cảm thụ mức chương | 332,5s | **0** |
| cảm thụ trong vòng candidate | 519,5s | **0** |
| UTMOS candidate | 322,3s | **0** |
| sinh candidate | 1.937,3s | 1.168,2s |
| kiểm candidate | 832,2s | 369,5s |

> **So sánh này KHÔNG sạch, đừng trích riêng con số hiệu.** alpha.51 là một lượt **resume**:
> `phase_timings` in `phân tích 0.0s` cho nó, tức nó không thu lại toàn bộ, và các con số vòng
> sửa của nó đo theo từng việc nên có thể gộp nhiều lần thử. Ba khoản đầu thì chắc chắn (bằng
> 0 là bằng 0). Hai khoản sau chỉ nói được "nhỏ đi", không nói được "nhỏ đi bao nhiêu vì cảm
> thụ" — muốn biết thì phải có một lượt chạy **sạch và có cảm thụ** để so, mà hiện không có.

**Hệ quả cho hàng đợi:** phân tích giờ là khoản lớn nhất (45%), không phải vòng sửa. Cả hai mục
chưa ship (pool candidate, Whisper thường trú) đều nằm trong hai khoản cộng lại chỉ còn 27% —
nên giá trị của chúng đã **nhỏ đi đáng kể** so với lúc được xếp hạng. Muốn rút ngắn một lượt
chạy bây giờ thì chỗ đáng nhìn là **pha phân tích**.

## Cảnh báo: mọi phần trăm dưới đây đo khi CÒN cảm thụ (2026-09-07)

Mọi con số "% một lần chạy" trong tài liệu này đo trên **lượt chạy có phép kiểm cảm thụ**.
Từ alpha.52 phép kiểm ấy **tắt** (`PERCEPTUAL_QA_COST.md`), và nó là khoản tốn lớn nhất
ngoài TTS. Nên:

- **Mẫu số nhỏ đi**, tức mọi mục còn lại tự động chiếm **phần trăm lớn hơn** trước. "1,6%
  một lần chạy" của mục 2 sẽ không còn là 1,6%.
- **Tử số cũng đổi.** Cả mục 1 lẫn mục 2 đều nằm trong vòng sửa candidate, mà vòng ấy trước
  đây chạy cho *cả* lỗi ASR lẫn lỗi cảm thụ. Bỏ nhánh cảm thụ thì vòng sửa chạy ít hơn hẳn,
  nên khoản tiết kiệm tuyệt đối (905s và 230s) **cũng nhỏ đi**, không chỉ đổi tỷ lệ.

Hai thứ đổi ngược chiều nhau, nên **không suy ra được** kết quả bằng phép nhân — đúng cái sai
mà mục 2 đã tự thú ở trên ("tôi lấy 2,33 GB/worker nhân ba, chứ không đo").

**Việc phải làm:** đo lại cơ cấu thời gian trên alpha.52 rồi mới xếp lại hàng đợi. Đừng dùng
các phần trăm dưới đây để quyết định gì cho tới lúc đó. `WHERE_A_RUN_SPENDS_ITS_TIME.md` cũng
cần đo lại cùng lúc, vì nó chia thời gian theo pha trên cùng loại lượt chạy cũ.

## Làm cái nào trước

Xếp theo giá trị thì mục 1 đứng đầu, nhưng xếp theo **giá trị chia cho rủi ro** thì mục 3
mới nên làm trước:

| mục | lấy lại | file phải sửa | trạng thái |
|---|---|---|---|
| 3. hạ `num_ctx` | ~639s pha phân tích | `config.py` | **đã ship** — thực tế 638s |
| 4. `tts.max_retries` → 10 | chất lượng: cứu 2 segment | `config.py` | **đã ship** — profile `high_quality`, config.py:289 |
| 6. khai báo `faster-whisper` | lỗ tái lập | `pyproject.toml` | **đã ship** — `faster-whisper==1.2.1` |
| 1. pool vòng candidate | ~905s | `pipeline.py` | chưa ship — thêm một đường prefetch |
| 2. Whisper thường trú | ~230s | `pipeline.py`, `asr.py` | chưa ship — đổi vòng đời model |

Kiểm lại trạng thái ship bằng chính code, đừng tin bảng này (2026-09-06):

```bash
grep -n "NAME_PRONUNCIATION_BATCH_SIZE = " _internal/ebook_reader/analysis.py   # mục 3: 12
grep -n '"tts": {"max_retries"' _internal/ebook_reader/config.py                # mục 4: 10
grep -n "faster-whisper==" _internal/pyproject.toml                             # mục 6
```

`config.py` mặc định vẫn ghi `max_retries: 3`; số 10 đến từ **override của profile
`high_quality`** ở `config.py:289`, nên đọc mỗi dòng mặc định sẽ tưởng mục 4 chưa làm.
Cách chắc chắn là đọc `book_settings.json` của project đang chạy.

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

### Hình dạng của thay đổi, và cái bẫy im lặng trong nó

Đường tổng hợp chính **không** song song hoá vòng ghi sổ của nó; nó dùng **prefetch**:
`pool.synthesize_many(jobs)` tổng hợp cả lô song song, rồi vòng tuần tự gọi
`_claim_prefetched_segment` để nhận từng kết quả sau khi kiểm stable_id, seed, file có thật,
và checksum. Cái gì bị từ chối thì tổng hợp lại tại chỗ. Nghĩa là **ghi DB vẫn tuần tự** -
không có chuyện tranh chấp SQLite - và pool chỉ làm phần TTS thuần tuý. Vòng candidate cần
đúng hình dạng ấy.

Ba ràng buộc đã kiểm trên dữ liệu thật, không phải đoán:

1. **Chỉ attempt 0 được prefetch** (`pipeline.py:3687`: một attempt sau tồn tại vì có gì đó
   đã sai, nên không được đoán trước). Trên alpha.32, **786/883 = 89%** candidate ở
   attempt 0, nên ràng buộc này chỉ bỏ lỡ 11%.
2. **Salt phải theo từng job, không theo cả lô.** `_prefetch_segment_batch` gắn cứng
   `"seed_salt": f"{seed_salt_prefix}_0"` cho mọi job. Candidate thì lấy salt từ
   `segment_candidate_split_seed_salt(repair_round, variant)`, và **cả hai variant đều tồn
   tại trong cùng một quyển sách** (`locked_spoken_v1` 526, `source_spelling_v1` 357), với
   round khác nhau giữa các segment. Một lô candidate vì thế **không đồng nhất**.
3. **Biến thể phát âm đi qua được pool.** `tts.synthesize_atomic` có nhận
   `pronunciation_delivery_variant`, và `_worker_job` truyền thẳng `**payload["kwargs"]`,
   nên không cần đụng gì tới `tts_pool.py`. (`_supports_pronunciation_delivery_variant`
   là phép kiểm cho *provider* trong tiến trình chính, không phải cho worker.)
4. **Cache phát âm của worker: an toàn, nhưng vì một lý do cụ thể.** Docstring của
   `SynthesisPool` cảnh báo worker cache phát âm lần đầu tổng hợp và parent phải
   `restart()` khi học được cách đọc mới. Trong pipeline **không có lời gọi `restart()`
   nào** - thay vào đó pool bị `_close_synthesis_pool()` ở cuối pha tổng hợp mỗi chương
   (dòng 2416, để nhả VRAM trước khi nạp Whisper) rồi dựng lại lười biếng. Vòng sửa chạy
   *sau* đó, nên pool của nó là pool mới với phát âm hiện hành. Đừng phá tính chất ấy: nếu
   giữ pool sống xuyên qua ranh giới ấy thì phải gọi `restart()` cho đúng hợp đồng.
5. **Phải đóng pool trước pha kiểm candidate**, y như dòng 2416 làm cho đường chính - pool
   giữ một bản VieNeu mỗi worker, và pha kiểm cần VRAM cho Whisper.
6. **Sai salt thì hỏng *im lặng*.** `_claim_prefetched_segment` kiểm
   `seed == generation_seed(row, seed_salt)`; lệch một chút là **mọi** kết quả bị từ chối,
   rơi hết về tổng hợp tuần tự. Kết quả: trả tiền VRAM cho pool và không nhanh hơn tí nào -
   trông y hệt "pool không giúp gì" chứ không phải một lỗi. **Test phải khẳng định số kết
   quả được *nhận*, không phải chỉ khẳng định chạy xong.**

Chi tiết và cảnh báo về cách quy thời gian: `docs/THROUGHPUT.md`.

## 2. Giữ Whisper thường trú **trong vòng sửa** — ~230s (đã hạ từ ~1.400s)

> **Chưa ship, và mục 1 vừa làm nó khó hơn** (2026-09-06). `verifier.unload()` vẫn được gọi
> ở cả bốn chỗ trong vòng sửa (`pipeline.py` 2073, 2121, 5207, 5284) — chúng nhả VRAM để TTS
> chạy, nên "giữ thường trú" nghĩa là để Whisper nằm cạnh pool TTS.
>
> Con số VRAM trong mục này (**đỉnh 2.719/8.151 MiB**) được đo khi vòng candidate còn chạy
> **tuần tự**, nên nó không còn dùng để quyết định được nữa.
>
> **Đo lại trên alpha.50** (158 mẫu, 13,2 phút, run ở `maximum`, pool clarity đang chạy):
>
> | | |
> |---|---|
> | VRAM p50 | 3.846 MiB |
> | VRAM p90 | 4.414 MiB |
> | **VRAM đỉnh** | **4.703 MiB — 58% card** |
> | còn trống lúc đỉnh | **3.448 MiB** |
>
> Lọc riêng 67 mẫu lúc GPU ≥ 50% (tức đang thật sự làm việc): p50 4.387, đỉnh vẫn 4.703.
>
> **Sửa một con số tôi tự bịa ra bằng phép nhân.** Bản trước của mục này ghi "ba worker là
> ~7 GB trên card 8 GB" — tôi lấy 2,33 GB/worker nhân ba, chứ không đo. Đỉnh thật là 4,7 GB.
> faster-whisper large-v3-turbo cỡ 1,5–2 GB, tức **vẫn còn 1,4–1,9 GB dư** nếu giữ thường
> trú. Phản đối về VRAM của tôi yếu hơn hẳn những gì tôi đã viết.
>
> Vẫn **chưa làm**, nhưng vì lý do khác: phần thưởng là 230 giây — **1,6% một lần chạy** —
> còn thời điểm rủi ro nhất (pool đủ cỡ *và* Whisper cùng nằm trong VRAM) là thứ hôm nay
> chưa bao giờ xảy ra, nên chưa ai đo được nó. Muốn làm thì đo đúng khoảnh khắc ấy trước,
> đừng suy ra như tôi đã làm. alpha.26 chết ở 357/948 vì hết bộ nhớ, và một lần chạy hỏng
> đắt gấp năm mươi lần khoản tiết kiệm.
>
> Cách đo lại: `scratchpad/vram_in_candidate_phase.py` cộng một sampler `nvidia-smi` mỗi 5
> giây; **lọc bỏ mẫu lúc run bị siết**, nếu không sẽ đo một cái pool đã bị bóp còn 0,25 GPU.

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

## 3. Hạ `num_ctx` về 7.168 bằng cách hạ batch tên — ~639s, ~16% pha phân tích

> **ĐÃ SHIP.** `NAME_PRONUNCIATION_BATCH_SIZE = 12` (analysis.py:268), và alpha.46 trở đi
> chạy ở 7.168. Đo lại pha phân tích trên chính log các bản:
>
> | bản | num_ctx | pha phân tích |
> |---|---|---|
> | alpha.43 | 9.216 | 74m39s (4.479s) |
> | alpha.46 | 7.168 | 67m14s (4.034s) |
> | alpha.47 | 7.168 | 64m13s (3.853s) |
> | alpha.48 | 7.168 | **64m01s (3.841s)** |
> | alpha.49 | 7.168 | 64m05s (3.845s) |
>
> Dự đoán tiết kiệm **639s**; thực tế **638s** (4.479 → 3.841). Hiếm khi một dự đoán trúng
> sát thế, nên ghi lại cả hai con số.
>
> Ba lần chạy cuối ở cùng cấu hình cho 3.841 / 3.845 / 3.853 giây — **chênh 12 giây trên
> 64 phút, tức 0,3%**. Pha phân tích vì thế là một mốc so sánh dùng được: lần sau lệch quá
> vài chục giây thì đó là thay đổi thật, không phải nhiễu.
>
> **Nhưng 0,3% ấy đo trên máy rảnh.** alpha.51 ra 3.926s (+85s, +2,2% so với alpha.48) trong
> khi bị siết **51,8%** thời gian. Nên biên nhiễu là hàm của việc máy có đang được dùng hay
> không, và phải kiểm `resource_share.py` trước khi gọi một chênh lệch là "thay đổi thật".
>
> Điều đáng chú ý theo hướng ngược lại: máy bị dùng hơn nửa thời gian mà pha phân tích chỉ
> chậm 2,2%. Pha ấy do **Ollama** — một tiến trình riêng — chạy, nên `gpu_scale` của bộ quản
> lý tài nguyên gần như không chạm tới nó. Siết chủ yếu ăn vào pha TTS và ASR.
>
> alpha.46 chậm hơn ~190s ở đúng cấu hình ấy, nên nó là tải máy chứ không phải num_ctx.
>
> Cách đo lại: mốc đầu và mốc cuối của dòng `Đang phân tích batch` trong
> `logs/ebook_reader.log`.

alpha.32 ở 7.168 chạy pha phân tích trong 3.851s; alpha.43 ở 9.216 mất 4.490s. Số lượt gọi
và số token gần như không đổi (+1,4% và +2,6%); **tốc độ sinh tụt 56,4 → 50,1 tok/s**, riêng
nó giải thích 542s trong 639s chênh lệch.

Đổi lại được đúng một lần guard cắt prompt. Cái làm ngữ cảnh nhỏ an toàn là **guard**, không
phải ngữ cảnh lớn — guard biến một lần hỏng âm thầm thành một lần chia batch nhìn thấy được.

**Nhưng đừng đè lên phép suy ra — hãy sửa cái làm nó lớn.** 9.216 đến từ batch chuẩn hoá tên:
20 tên xin `min(512 + 20*192, 6144)` = 4.352 token đầu ra, và phép suy ra đòi ít nhất gấp
đôi số ấy để tránh bị `num_ctx // 2` cắt lén. Sàn thật của quyển sách này là batch *segment*
(5 đoạn, 6.200 ký tự) chỉ cần 6.940 → **7.168**.

    NAME_PRONUNCIATION_BATCH_SIZE   num_ctx suy ra   số batch cho 112 tên
                               20             9216                      6
                               16             8192                      7
                             **12**         **7168**                 **10**
                                8             7168                     14

**Hạ `NAME_PRONUNCIATION_BATCH_SIZE` 20 → 12** đưa num_ctx về đúng 7.168 mà **không đè gì
cả**: phép suy ra vẫn bảo đảm gấp đôi đầu ra, không có cái cắt lén nào. Giá là 112 tên đi từ
6 batch thành 10 - **4 lời gọi thêm trên 424**, và mỗi cái còn nhỏ hơn trước.

Chưa đo: batch tên nhỏ hơn ảnh hưởng thế nào tới *chất lượng* cách đọc. Log alpha.43 có
"Chuẩn hóa tên batch 1 còn 18 tên lỗi sau lần 3", nên batch nhỏ hơn có thể còn đỡ hơn - đó
là phỏng đoán, phải nhìn số tên lỗi ở lần chạy sau.

### Cảnh báo: đây **không phải** một núm thuần tốc độ

Đổi `num_ctx` làm **đổi cả đầu ra của phân tích**, và alpha.43 cho thấy mức độ:

| | dải `fast` được gán |
|---|---|
| alpha.32 (ctx 7.168) | 3 segment (0,3%) |
| alpha.43 (ctx 9.216) | **14 segment (1,5%)** |

Cùng quyển sách, cùng prompt. Ngữ cảnh rộng hơn đổi cách chia batch (10 lần chia so với 3)
và đổi cả số học của suy luận, nên director chọn khác. Điều đó **đổi chỉ dẫn diễn xuất → đổi
âm thanh → đổi kết cục**: chính cơ chế đã lấy mất audio của `c00007_s0000074` (xem mục 7).

Nên hạ num_ctx **sẽ lại làm đổi kết quả một lần nữa**. Có thể đổi theo hướng tốt - alpha.32
ở 7.168 gán `fast` ít hơn nhiều và không mất segment nào vì dải - nhưng phải coi đây là
**thay đổi chạm chất lượng**, xác minh bằng `scripts/compare_runs.py`, chứ không phải một
con số vô hại. Đó cũng đúng là lý do `pyproject.toml`/`config.py` nằm trong
`QUALITY_IMPLEMENTATION_FILES` ngay từ đầu.

Chi tiết: `docs/VRAM_AND_CONTEXT.md`.

## 4. Nâng `tts.max_retries` 4 → 10 — cứu 2 trong 3 segment không có audio

Không phải tối ưu tốc độ, mà là chất lượng. Hai segment trượt cổng nhịp vì **hết lượt**,
không phải vì giọng không đọc nổi: một cái trượt 0,03 ký tự/s. Ở ngân sách 10 chúng qua với
xác suất 88% và 73%. Giá: cả sách chỉ 3 segment chạm ngân sách, nên ~18 lượt tổng hợp thêm.

Segment thứ ba (`C » B » A » S » SS » SSS`) ngoài tầm với ở mọi ngân sách và **không được
nới cận dưới vì nó** — 807 segment đã nhận, không cái nào dưới 12.5. Chi tiết:
`docs/PACE_METRIC.md`.

### Cái bẫy: `max_retries` không chỉ là số lần thử, nó còn là một **sentinel**

Đổi một hằng số nghe như việc an toàn nhất hàng đợi. Nó không hẳn thế. `max_retries` được
đọc ở **ba** chỗ, và một chỗ dùng nó làm **giá trị đánh dấu**:

    pipeline.py:3086   tts_attempt = max_retries if force_clause_split else 0
    pipeline.py:3362   if current_attempt > retries: raise ...
    pipeline.py:3366   for attempt in range(current_attempt, retries)

Candidate thường có `tts_attempt = 0` → `range(0, 4)` → 4 lần thử. Candidate **clause-split
ép buộc** được ghi với `tts_attempt = max_retries` → `range(4, 4)` → **cố ý không có lần thử
nào**. Nói cách khác, "không thử lại" được mã hoá *bằng chính con số* `max_retries`.

Nâng 4 → 10 thì những hàng đã ghi với `tts_attempt = 4` tính ra `range(4, 10)` = **6 lần
thử trên một candidate lẽ ra không có lần nào**. Trong alpha.32 có **85 hàng như vậy**
(phân bố `tts_attempt`: 0→786, 1→10, 2→2, **4→85**).

**Phạm vi của nguy cơ:** chỉ cắn khi **resume một project đã có** sau khi đổi hằng số.
Project mới thì không sao - sentinel mới là 10 và `range(10, 10)` vẫn rỗng. Nhưng đổi
`config.py` chính là thứ vô hiệu hoá bằng chứng QA và buộc xác minh lại *có resume*, nên
đây không phải tình huống hiếm.

**Cách làm đúng:** hoặc chỉ áp cho project mới (mỗi phiên bản alpha vốn đã là một project
riêng), hoặc tách sentinel ra khỏi hằng số trước — nó không nên là `max_retries` ngay từ
đầu. Cái sau mới là sửa thật, và nó chạm `pipeline.py`, nên **mục 4 không còn là "đổi một
hằng số" nữa** khi có project cần resume.

## 5. Ngưỡng perceptual theo sigma thay vì theo số tuyệt đối — bớt một nửa việc nghe

Không phải tốc độ, mà là **thời gian của chủ sách**. Cổng dùng một ngưỡng tuyệt đối
(`review_delta = -0.8`) cho mọi độ dài, nhưng độ tán của thước đo tăng 63% khi đoạn ngắn
lại, trong khi **trung vị phẳng**. Kết quả: đoạn <2s bị gắn cờ 14,9%, đoạn ≥8s chỉ 1,8% —
"tệ nhất" mang hai nghĩa trong cùng một cổng.

Áp cùng **2,06 sigma** (đúng cái mà −0,8 nghĩa là với đoạn dài) cho từng nhóm độ dài:
**80 → 39 lần gắn cờ**. Nó *siết* đoạn dài (1,8% → 2,8%) và nới đoạn ngắn, nên là **cân
bằng lại, không phải nới lỏng**.

**Nhưng nó không mở khoá thêm chương nào — đã kiểm.** Trong 6 segment perceptual đang chặn
của alpha.32, ngưỡng mới gỡ được 3 (gồm cả hai đoạn ngắn 2,48s và 1,84s đúng kiểu thiên vị
độ dài). Chạy lại cổng xuất bản với 3 cái đã gỡ: **0/7 chương được mở**, vì chương nào cũng
còn ít nhất một chỗ chặn khác. Giá trị của mục này là **thời gian nghe của chủ sách**, không
phải số chương xuất bản. Đừng bán nó như cái thứ hai.

**Câu hỏi mở đã trả lời (06/09/2026) — và không cần GPU.** Câu hỏi là: phần tán thêm ở
đoạn ngắn là nhiễu thước đo hay chất lượng thật sự dao động hơn. Không cần tổng hợp lại gì
cả: vòng sửa chữa đã thu lại cùng một câu với seed khác nhau hàng trăm lần và
`segment_candidates` lưu đủ `generation_seed` + `wav_duration` + `perceptual_result_json`.

Gộp alpha.32/43/44/46, khử trùng lặp theo văn bản, chỉ lấy câu có từ hai seed khác nhau:
**đoạn <4s dao động 0,178 (trung vị), đoạn ≥4s dao động 0,047 — gấp 3,8 lần.** Cá biệt câu
`"Thương hại? Ta sao?"` (1,60s) dịch **0,703** chỉ vì đổi seed, tức **88% của cả ngưỡng
−0,8**, trên đúng cùng một câu chữ.

Phép đo này **không** tách được "thước đo nhiễu" khỏi "bản thu ngắn thật sự dao động hơn" —
seed khác thì audio thật sự khác. Nhưng cả hai đều dẫn tới cùng kết luận: **ngưỡng tuyệt đối
là sai với đoạn ngắn**, nên câu hỏi ấy không còn chặn mục này.

Cỡ mẫu nhỏ (8 câu ngắn, 3 câu dài) và thiên về câu vốn có vấn đề. Chi tiết và giới hạn:
`docs/PERCEPTUAL_QA_COST.md`, `scripts/perceptual_duration_bias.py`.

## 6. `faster-whisper` chưa được khai báo là dependency — lỗ tái lập, **không phải** lỗi chạy

alpha.43 đang chạy `asr.engine = faster`, dùng `faster-whisper 1.2.1` + `ctranslate2 4.8.2`
cài trong runtime venv. **Cả hai đều không có trong `pyproject.toml` lẫn `uv.lock`.** Dựng
lại môi trường từ manifest thì không ra được môi trường đang chạy.

Mức độ: **có giới hạn, và đã kiểm chứ không đoán.** Mặc định `asr.engine` vẫn là `openai`
(cố ý - đổi engine là một "version event"), nên cấu hình mặc định dựng lại được. Còn nếu ai
đặt `faster` trên môi trường thiếu gói, `asr.required = True` và `failure_policy = "fail"`
làm nó **ném lỗi to** lúc nạp model, chứ không âm thầm chạy cả sách mà không có ASR.

Đáng chú ý: `load()` khi engine `faster` hỏng thì **không lùi về `openai`** - nó tắt ASR.
Đúng ở đây chỉ vì `required=True` biến việc tắt ấy thành ném lỗi.

**Không sửa được lúc này, và lý do đáng ghi lại:** `../pyproject.toml` và `../uv.lock` nằm
*trong* `QUALITY_IMPLEMENTATION_FILES`. Sửa chúng giữa lúc alpha.43 chạy sẽ đổi fingerprint
chất lượng và **xoá sạch bằng chứng QA audio của cả quyển sách**, bắt ASR + perceptual chạy
lại từ đầu. Một dòng thêm vào manifest, đúng lúc, tốn 30-40 phút chạy lại.

## 7. Lùi về dải `normal` khi một chỉ dẫn nhịp không đọc tới được — cứu segment khỏi mất sạch audio

`tts.pace_chars_per_second` có ba dải và `analysis` chọn dải cho từng segment. Dải `fast`
nâng **cận dưới** lên 14,0, nên chỉ dẫn "đọc nhanh lên" biến thành "bản thu này quá chậm".

alpha.43 mất `c00007_s0000074` đúng kiểu ấy: bốn lần thử 12,70 / 12,26 / 12,26 / 12,70, và
**bản thu 12,70 y hệt đã qua được ở alpha.32** khi dải là `normal` (cận 12,5). Chỉ có chỉ
dẫn đổi — `neutral/0` thành `afraid/2` — chứ giọng đọc không đổi gì.

**Lớp này nhỏ nhưng đang phình ra, và rủi ro cao:**

| | `fast` | `slow` | `normal` |
|---|---|---|---|
| alpha.32 | 3 (0,3%) | 3 | 942 |
| alpha.43 | **14 (1,5%)** | 3 | 931 |

alpha.43 gán `fast` **nhiều gấp 4,7 lần**, và **1 trong 14** đã mất sạch audio — tỉ lệ ~7%
trong dải ấy so với nền 0,2% của cả sách. (Việc gán nhiều hơn đi *cùng* với thay đổi
`num_ctx`, thứ làm đổi cách chia batch nên đổi đầu ra của director. Đó là tương quan với một
thay đổi đã biết, chưa phải nhân quả đã chứng minh.)

**Cách sửa hẹp:** đường cứu hiện tại khi hết 4 lượt là **chia nhỏ câu**, và với câu ngắn nó
báo "too short to split safely" rồi bỏ cuộc. Thêm một bước trước khi bỏ: nếu segment không ở
dải `normal`, **thử lại ở dải `normal`**. Bằng chứng ủng hộ trực tiếp — chính bản thu ấy đạt
ở `normal`. Mất một sắc thái diễn xuất còn hơn mất cả câu.

Chi tiết và bảng đầy đủ: `docs/PACE_METRIC.md`.

---

## Cần gì để xuất bản trọn quyển sách (alpha.32)

Đây mới là câu trả lời mà mọi thứ ở trên phục vụ. `scripts/what_blocks_publication.py` giờ
in thẳng ra:

    Đang xuất bản được: 3/10
      chỉ cần tai người nghe : +4 chương [2, 3, 7, 8]  => 7/10
      cần bản thu mới trước  : +3 chương [5, 9, 10]  => 10/10

**Bốn chương chỉ đợi tai người.** 10 chỗ có bản thu để nghe, mỗi chỗ một lệnh `accept` in
sẵn - hoặc mở `review.html` mà `scripts/build_review_page.py` dựng ra, có sẵn trình phát.

**Ba chương còn lại không nghe được.** Segment chặn chúng **không có audio nào**: cổng nhịp
từ chối cả 4 lần thử, nên không có gì để nghe và `accept` sẽ báo lỗi vì không có checksum để
đối chiếu. Chúng cần **mục 4** (`tts.max_retries` 4 → 10), thứ đã đo là cứu được 2 trong 3
với xác suất 88% và 73%.

Nói gọn: **một tối cặm cụi nghe cộng một hằng số đổi từ 4 lên 10 là ra cả quyển sách.**

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

## Đã loại: chồng lấn pha phân tích với TTS (đo 2026-09-06, alpha.49)

Ý tưởng nghe rất hợp lý: pha phân tích chạy 948/948 segment rồi mới tới chương đầu tiên,
mất khoảng **64 phút** trong đó chưa dựng một giây audio nào. Chương 1 đã phân tích xong từ
phút thứ nhất, nên về lý thì có thể dựng audio chương 1 song song với phân tích chương 10.

**Đo trong lúc alpha.49 đang phân tích, 12 mẫu:**

| tài nguyên | mức |
|---|---|
| GPU | **96%** (min 96, max 97) |
| VRAM | 6.450 / 8.151 MiB — **79%** |
| CPU | 5% |
| RAM | còn trống 21,2 GB |

**GPU đã kín.** Ollama chiếm 96% suốt pha ấy, nên TTS chạy chồng lên không lấy thêm được gì
— nó chỉ tranh đúng cái tài nguyên đang là nút cổ chai, và còn phải chen vào 1,7 GB VRAM
trống trong khi VieNeu cần nhiều hơn thế. Chồng lấn ở đây không phải "được thêm", mà là
"chia lại cùng một miếng, cộng thêm rủi ro hết VRAM".

CPU nhàn 5% và 21 GB RAM trống **không phải năng lực bỏ phí** theo nghĩa dùng được: việc
CPU-nặng duy nhất trong pipeline là chấm cảm thụ, mà nó cần audio — thứ chưa tồn tại trong
pha phân tích.

Kết luận: pha phân tích đã vắt kiệt đúng tài nguyên quyết định. Muốn nó nhanh hơn thì phải
làm **ít việc GPU hơn** (mục 3 — hạ `num_ctx`), không phải xếp thêm việc GPU vào cạnh nó.
Cách đo lại: `nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader`
lặp vài chục lần trong lúc pha phân tích chạy.

## Pha phân tích: 93% là sinh token, nên gộp lô không giúp gì

Đo trên alpha.54, 417 lần gọi Ollama, tổng 63,5 phút:

| khoản | giây | tỷ trọng |
|---|---|---|
| **sinh token** | **3.541** | **93%** |
| nạp prompt | 201 | 5% |
| nạp model | 5 | 0% |
| overhead còn lại | 62 | 2% |

Trung bình mỗi lần: prompt 2.416 token, sinh 468 token, tốc độ 55,5 tok/s.

**Hệ quả thứ nhất: gộp lô to hơn gần như vô ích.** Overhead mỗi lần gọi chỉ 2%. Tăng
`batch_segments` từ 5 lên 10 thì số lần gọi giảm một nửa nhưng token sinh mỗi lần tăng gấp
đôi — tổng token gần như không đổi, mà 93% chi phí nằm ở đó. Đây là loại tối ưu nghe hợp lý
nhưng không có gì để lấy.

**Hệ quả thứ hai: schema đã gọn rồi.** 10 trường mỗi đoạn, và `notes` — trường dài nhất trong
bản ghi lưu trữ — **không** nằm trong schema gửi model; nó được tính lại bằng
`canonical_analysis_note()` sau khi model trả lời. Tối ưu ấy đã làm từ trước.

**Đòn bẩy còn lại, và nó nhỏ:** mỗi đoạn model phải nhắc lại `id` dạng
`c00001_s0000000_7d9b3fda46a9` — 28 ký tự, khoảng 12 token, chỉ để định danh dòng. Năm đoạn là
~60 token, tức **~13% đầu ra**. Thay bằng chỉ số 0–4 trong lô sẽ lấy lại chừng đó.

Ước tính: 13% × 93% × 45% ≈ **5% một lượt chạy**, tức ~7 giờ trên 130 giờ.

**Chưa làm, và không nên làm vội.** `id` là thứ dóng kết quả về đúng dòng. Đổi nó là đổi giao
thức, và loại lỗi ở đó **im lặng** — đúng như `expected_status` bị hard-code `"pending"` đã
cho thấy: UPDATE khớp không dòng nào và câu trả lời bị vứt mà không ai báo. Đổi 7 giờ lấy rủi
ro ấy chỉ đáng khi có test ghim được chuyện dóng sai.

## Đừng cắt ngân sách thu lại: vòng 2–4 đẻ ra bản thu thắng cuộc trong 1/6 số ca

Mỗi segment hỏng được thu lại tối đa 5 vòng. Nhìn qua thì đó là chỗ cắt ngon nhất còn lại: một
segment đã trượt hai vòng thì trượt luôn, cắt còn 2 vòng là tiết kiệm được GPU thật.

**Tôi đã suýt đề xuất đúng như thế, dựa trên một phép đếm sai.** Phép đếm ấy là: gộp 6 phiên
bản, đếm số *lượt thu* ở vòng 2–4 và số lượt "cứu được" → 563 lượt thu, cứu 4, tức 0,7%. Nghe
là bỏ ngay.

Sai ở mẫu số. Một segment cứng đầu chạy hết 5 vòng sẽ được đếm **một lần cho mỗi vòng**, nên
nó nhồi mẫu số bằng chính những ca vô vọng, rồi kết luận "vòng sau vô dụng" — một lập luận
vòng tròn. Phép đo đúng là hỏi theo **segment**, không theo lượt thu: *bản thu cuối cùng được
chọn nằm ở vòng nào?*

| bản | segment có thu lại | chọn ở v0 | v1 | v2 | v3 | v4 | không bao giờ |
|---|---|---|---|---|---|---|---|
| alpha.50 | 131 | 34 | 29 | 6 | 13 | 6 | 43 |
| alpha.51 | 148 | 47 | 31 | 6 | 13 | 3 | 48 |
| alpha.52 | 104 | 26 | 32 | 4 | 9 | 5 | 28 |
| alpha.53 | 97 | 26 | 30 | 4 | 10 | 4 | 23 |
| alpha.54 | 97 | 26 | 30 | 4 | 10 | 4 | 23 |
| alpha.55 | 64 | 21 | 12 | 0 | 4 | 1 | 26 |
| **gộp** | **641** | **180** | **164** | **24** | **59** | **23** | **191** |

**106 trên 641 segment (16,5%) lấy bản thu thắng cuộc từ vòng 2 trở đi.** Cắt ngân sách xuống
2 vòng là vứt đúng 106 segment ấy — mỗi cái là một chương không xuất được.

Chú ý cột `v3` cao hơn `v2` ở cả sáu bản. Tôi đoán đầu tiên là "vòng 3 đổi chiến lược sinh" —
**sai**: `generation_strategy` là `direct_v1` suốt vòng 0–3, `split_v1` mãi vòng 4 mới xuất hiện.

Thứ thật sự luân phiên là `pronunciation_delivery_variant`, tức **văn bản đưa cho TTS**:

| vòng | `locked_spoken_v1` | `source_spelling_v1` |
|---|---|---|
| 0 | 641 | – |
| 1 | 123 | **338** |
| 2 | 291 | – |
| 3 | 84 | **183** |
| 4 | 104 | 104 |

Vòng **chẵn** thu lại bằng đúng cách đọc đã khoá, chỉ khác seed. Vòng **lẻ** đưa cho TTS
*chính tả gốc* thay cho dạng phiên âm. Đó là lý do v1 và v3 ăn đứt v0 và v2 — đổi đầu vào thì
thoát được, gieo lại thì hiếm.

Và bản thân tỉ lệ thắng của hai biến thể cũng đáng ghi:

| biến thể | được chọn |
|---|---|
| `locked_spoken_v1` | 251/848 = **29,6%** |
| `source_spelling_v1` | 199/558 = **35,7%** |

`source_spelling_v1` chỉ được thử trên những segment **đã trượt** với `locked_spoken_v1`, tức
một tập khó hơn hẳn — vậy mà vẫn thắng cao hơn 6 điểm. Nói cách khác: với một phần đáng kể tên
riêng, **đưa chính tả gốc cho TTS đọc lại đúng hơn là đưa phiên âm ta soạn**. Chưa đủ để đảo
thứ tự (phiên âm vẫn phải đi trước, vì nó là thứ chủ sách duyệt), nhưng đủ để không ai nên bỏ
vòng lẻ đi.

Ai muốn cắt thì cắt vòng 2 — vòng gieo-lại-thuần — đừng cắt vòng lẻ.

**Bài học rộng hơn, đáng nhớ hơn con số:** khi đếm để quyết định bỏ một cơ chế, kiểm xem mẫu số
có bị chính những ca thất bại nhồi lên không. Đếm theo *lượt* thì cơ chế nào cũng trông vô dụng,
vì cái vô vọng bao giờ cũng chiếm nhiều lượt nhất.
