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

---

## Máy tự sinh ra thuốc chữa rồi vứt đi — `"Tiếp theo."`, chương 003 alpha.60

**Chưa sửa.** Đây là thứ chặn chương 003 vĩnh viễn sau khi
[cơ chế tự cho qua](SHIPPING_WITHOUT_A_LISTENER.md) đã gỡ ba chương khác, nên nó là ứng viên
tiếp theo rõ ràng nhất. Ghi kèm toàn bộ số liệu vì lập luận ở đây rất dễ trượt thành thứ tôi
đã cố ý **từ chối** làm.

### Số liệu

Đoạn `c00003_s0000129`, chữ `"Tiếp theo."` (10 ký tự). Bản đương nhiệm và năm ứng viên:

| | thời lượng | chạm trần | ASR beam nghe ra | sim |
|---|---|---|---|---|
| **đương nhiệm** | 1,92s | **có** | `"Tiếp theo. À xong."` | — |
| vòng 0 | 0,96s | **có** | `"tiếp theo"` | 1,00 |
| vòng 1 | 0,56s | không | `"Cảm ơn các bạn đã theo dõi."` | 0,00 |
| vòng 2 | 0,96s | **có** | `"Cảm ơn các bạn đã theo dõi và hẹn gặp lại."` | 0,00 |
| vòng 3 | 0,96s | **có** | `"Cảm ơn các bạn đã theo dõi và hẹn gặp lại."` | 0,00 |
| **vòng 4** | **0,64s** | **không** | `"Tiếp theo. Tiếp theo. Tiếp theo."` | **1,00** |

Ba bản 0,96s giống hệt nhau đến hai chữ số — đó là **trần khung**, không phải trùng hợp. Và
1,92 = 2 × 0,96.

"Không chạm trần" ở đây là kết luận chắc, không phải suy đoán từ giá trị vắng:
`tts.py:1101` chỉ ghi `metrics["generation_ceiling_hit"] = 1.0` **khi thật sự chạm trần**, nên
khoá vắng mặt nghĩa là bộ sinh tự kết thúc. Vòng 1 và vòng 4 vắng cả ba khoá
`generation_*`; vòng 0, 2, 3 có đủ.

### Vì sao đây **không** phải "thăng bản ít tệ nhất"

Tôi đã cố ý từ chối luật ấy — xem [SHIPPING_WITHOUT_A_LISTENER.md](SHIPPING_WITHOUT_A_LISTENER.md)
và `test_candidate_exhaustion_keeps_incumbent_and_uses_incumbent_evidence`. Lý lẽ: so hai con
số mà **cả hai** đều dưới ngưỡng thì không nói lên gì.

Ở đây không phải thế. Vòng 4 hơn bản đương nhiệm ở **đúng tín hiệu mà chính sách coi là bằng
chứng về bản thu**:

- bản đương nhiệm mang `generation_ceiling_hit` — bộ sinh tự khai nó chạy hết khung mà chưa
  dừng, và ASR nghe ra thừa hẳn `"À xong"`, tức trong file **có tiếng thật sự thừa**;
- vòng 4 không chạm trần, dài 0,64s — đúng dải 0,64–0,80s mà `scripts/probe_frame_cap.py` đo
  được cho chính câu này ở năm trần khác nhau;
- vòng 4 trượt vì `ASR_REPEATED_SHORT_PASS`: Whisper lặp lại chữ trên clip dưới một giây. Đó
  là tật đã biết của Whisper trên clip ngắn, và `sim=1,00` nói nó nghe ra **đúng chữ**.

Nói cách khác: bản bị vứt trượt vì một phép kiểm nói về **Whisper**, bản được giữ hỏng theo
một phép kiểm nói về **bản thu**. Chính sách đã tự xếp `ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE` vào
nhóm "không mang thông tin" (`HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS`) vì đúng lý do ấy.

### Rộng bao nhiêu: 2 ca trên 38.520 đoạn, và cùng một chữ ký

`scripts/discarded_cures.py` quét **mọi** project đã lưu tìm đúng mẫu ấy — đương nhiệm chạm
trần, có ứng viên không chạm trần chỉ trượt bằng mã mà chính sách tự xếp là vô thông tin:

```
v0.2.0-alpha.25   ch005  '"Arghh..."'      đương nhiệm 1,92s;  cứu ở 0,48s và 0,64s
v0.2.0-alpha.60   ch021  '"Tiếp theo."'    đương nhiệm 1,92s;  cứu ở 0,56s và 0,64s
TỔNG: 2 ca / 38.520 đoạn  =  0,005%
```

Hiếm — nhưng chữ ký thì **trùng khít**, và điều đó quan trọng hơn tỉ lệ:

- cả hai đương nhiệm dài **đúng 1,92 giây**;
- cả hai là câu rất ngắn (một tiếng thốt, một câu hai từ);
- cả hai có ứng viên **tự kết thúc** ở 0,48–0,64 giây;
- cả hai ứng viên ấy trượt bằng `ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE` — mã mà
  `HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS` **đã tự khai là không mang thông tin**.

Cách đọc đúng con số này: hiếm tính theo **đoạn**, không hiếm tính theo **chương**, vì mỗi ca
chặn nguyên một chương. Ngoại suy thô sang 478 chương (~72.000 đoạn) ra **khoảng bốn chương**
bị chặn vĩnh viễn vì mẫu này. Bốn chương không phải là gấp, nhưng cũng không phải không đáng —
và nó sửa lại câu tôi viết ở
[SHIPPING_WITHOUT_A_LISTENER.md](SHIPPING_WITHOUT_A_LISTENER.md): chương 003 của alpha.60 không
phải một ca lẻ, nó là ca thứ hai trong một họ.

(Ngoại suy này là ngoại suy, và tôi đã sai ba lần vì đúng loại phép tính ấy. Nó chỉ dùng để
xếp ưu tiên, không dùng để khẳng định.)

**Cùng một sự thật, ba lần sửa** — để lại cả ba vì mỗi lần đều dựa trên bằng chứng tốt hơn lần
trước, và lần cuối mới là một đồng nhất thức.

*Lần một* tôi viết "1,92 giây = 2 × trần khung 0,96 giây", nghe rất khớp và không có gì chống đỡ.

*Lần hai* tôi truy `generation_frame_cap` và thấy đoạn 1,92 giây có `cap=12` còn đoạn 0,96 giây
**không đặt cap**, nên kết luận "hai con số đến từ hai đường khác nhau chứ không phải bội số của
nhau". Đúng về chỗ **ghi**, sai về kết luận.

*Lần ba* (2026-09-10) đo trên **mọi** project đã lưu:

```
segments   cap=12  dur=1,92s   7 lần   ->  0,1600 giây/khung, chính xác
candidates         dur=0,96s  36 lần   (bảng candidate không ghi cap)
candidates         dur=1,92s  52 lần
candidates         dur=1,84s   2 lần
```

Một khung là **đúng 160 ms**, và hai hằng số trong `tts.py` là:

```
MICRO_UTTERANCE_REPAIR_MAX_FRAMES  =  6   ->  0,96 s
SHORT_UTTERANCE_REPAIR_MAX_FRAMES  = 12   ->  1,92 s
```

Nên 0,96 và 1,92 **là** 6:12 trên cùng một lưới — trực giác lần một đúng số nhưng sai lý do, và
"hai đường khác nhau" của lần hai sai: cùng một lưới, hai hằng số trần, và bảng candidate chỉ
không ghi lại cap. Chữ ký 1,92 giây không còn là "mức hay gặp" mà là **giá trị duy nhất** mà một
đoạn ngắn chạm trần có thể dừng ở.

### Hình dạng bản vá — và tôi đã mô tả sai nó một lần

Lần đầu tôi viết ở đây rằng bản vá "hẹp đến mức không đụng vào luật giữ-bản-đương-nhiệm". Đọc
code thì **không phải**, và cái sai ấy đáng để lại vì nó đổi cả độ khó.

Thứ chặn không nằm ở điểm cạn ngân sách mà nằm sâu hơn hai tầng:
`ProjectDB.promote_segment_candidate` chỉ nhận ứng viên ở trạng thái `dual_passed`, và ném
`RuntimeError("segment candidate cannot be promoted before both ASR decodes pass")` với mọi
trạng thái khác. Một ứng viên `dual_failed` **không thể** được thăng, ở tầng database, có chủ ý.

Test tôi tưởng đang ghim quyết định này —
`test_candidate_exhaustion_keeps_incumbent_and_uses_incumbent_evidence` — hoá ra nói về ứng
viên **không sinh nổi audio** (`candidate_attempts` toàn `tts_failed`), tức một ca khác hẳn.
Ràng buộc thật là câu `raise` ở trên.

**Cách phát biểu đúng vấn đề:** không có chỗ nào trong hệ thống so *bản đương nhiệm đã được
chứng minh là hỏng* với *ứng viên chưa chứng minh được là tốt*. Cổng thăng hạng hỏi "ứng viên
có tốt không" và trả lời **không** — hoàn toàn đúng, vì không chứng minh được tốt thì không
được thay. Nhưng không ai hỏi "bản đương nhiệm có hỏng không", mà với `"Tiếp theo."` thì nó
**có**: `generation_ceiling_hit`.

Nên bản vá không phải một phép so ở điểm cạn ngân sách. Nó phải là một đường riêng, và đường
ấy cần được thiết kế chứ không phải chèn vào.

### Lô 2 trả lời, và câu trả lời đổi cả cách phát biểu vấn đề (2026-09-10)

Lô 2 mất chương 053 vì đoạn `'"Bất bại?"'`, và ca này khác hai ca trước ở chỗ **quan trọng
nhất**: `patch_ceiling_repairable` **đã chạy**. Đoạn ấy có đủ năm ứng viên, vòng 0 tới 4 — lần
đầu bản vá trần khung được thực thi ngoài unit test. Nên nó không phải "một lỗ hổng chưa vá".

```
đương nhiệm  1,92s  chạm trần            <- bị CẮT giữa câu, bộ sinh tự khai
vòng 0       0,96s  chạm trần            ASR_MISMATCH / ASR_MISMATCH
vòng 1       0,80s  KHÔNG chạm trần      ASR_REPEATED_SHORT_PASS / ASR_MISMATCH
vòng 2       0,96s  chạm trần
vòng 3       0,72s  KHÔNG chạm trần      ASR_MISMATCH / ASR_MISMATCH
vòng 4       0,96s  chạm trần
```

**`'"Bất bại?"'` có sáu ký tự chữ-số, trên ngưỡng `ASR_MIN_VERIFIABLE_CHARS = 10.**` Dự án đã
**đo** rằng dưới ngưỡng ấy ASR không phán xử được: tương đồng trung vị 0,27 so với 0,94, trượt
75% số lần so với 0,2%. Vậy "cả năm ứng viên trượt ASR" **không phải bằng chứng** rằng chúng
tệ — nó là kết quả của việc hỏi một phép kiểm câu hỏi mà chính dự án biết nó không trả lời được.

Và `_segment_has_non_asr_failure_evidence` từ chối cái cớ văn-bản-ngắn cho **đương nhiệm** một
cách đúng đắn, với lý do ghi ngay trong docstring: *"Short text excuses only the transcriber. If
the generator itself reported that it ran out of frames … a short reference is no defence."*
Nhưng vòng 1 và vòng 3 **không** chạm trần — bộ sinh không khai gì về chúng — nên cái cớ ấy vẫn
còn nguyên hiệu lực cho chúng.

**Phát biểu đúng, gọn hơn bản cũ nhiều:** không phải *"so đương nhiệm hỏng với ứng viên chưa
chứng minh được"*. Mà là:

> Khi ASR không thể làm trọng tài, hãy giữ bản thu mà bộ sinh **nói xong**, đừng giữ bản mà bộ
> sinh **cắt giữa câu**.

Đó không phải nhận một ứng viên chưa chứng minh — đó là dùng nhân chứng **duy nhất có ý kiến**,
đúng cái nguyên tắc mà `MACHINE_ACCEPTABLE` đứng trên. Ở đây có một phép kiểm nói đương nhiệm
hỏng, và không phép kiểm nào nói ứng viên hỏng.

### Cách chữa nhỏ hơn, và phép đo bác bỏ nó

Trước khi dựng một đường thăng hạng mới, tôi thử tìm đường rẻ hơn: cái cớ văn-bản-quá-ngắn
**đã tồn tại** ở tầng segment (`asr_verdict_is_unverifiable` → verdict `PASS` +
`ASR_UNVERIFIABLE_SHORT_TEXT`), còn tầng ứng viên thì không áp nó. `database` quyết
`dual_passed` thuần từ hai verdict ASR cộng cờ sóng âm. Nếu áp cùng cái cớ ấy cho ứng viên thì
ứng viên thành `dual_passed`, `promote_segment_candidate` chạy nguyên như cũ, **không cần bảng
mới, không cần nới bất biến nào**.

Rất gọn, và **sai**. Đếm trên mọi project đã lưu:

```
2.884  văn bản DÀI,  có ứng viên
  469  văn bản NGẮN, có ứng viên, đương nhiệm KHÔNG chạm trần
   14  văn bản NGẮN, có ứng viên, đương nhiệm CHẠM TRẦN
```

Tôi đã suy luận rằng ứng viên chỉ sinh ra cho đoạn văn-bản-ngắn khi có bằng chứng ngoài-ASR,
nên nới cái cớ ấy là vô hại. **469 dòng nói ngược**, và phần lớn chúng kết thúc `verified` —
tức đương nhiệm vốn không sao. Nới cái cớ ở tầng ứng viên là trao quyền thay thế cho bốn trăm
chỗ chẳng cần thay, dựa trên không bằng chứng nào ngoài sóng âm.

Nên kết luận cũ của mục này đứng vững, và giờ có bằng chứng cho *vì sao*: nó phải là **một đường
riêng**, với điều kiện tiên quyết là **đương nhiệm đã bị chứng minh hỏng**, chứ không phải một
lần nới ở chỗ phán xử ứng viên. Con số 14 cũng nói đường ấy hẹp đến mức nào: nhiều nhất mười bốn
lần trên năm mươi nghìn đoạn.

### Tần suất thật, sau khi nới bộ dò

Bộ dò đầu tiên đòi mã của ứng viên nằm trong danh sách "vô thông tin", nên nó **bỏ sót** ca lô 2
(mã là `ASR_MISMATCH`). Nới thêm một đường: *mọi* mã ASR đều vô thông tin khi văn bản ngắn hơn
ngưỡng. Quét lại toàn bộ:

```
3 ca / 50.196 đoạn  =  0,006%
  alpha.25  ch005  '"Arghh..."'      đương nhiệm 1,92s
  alpha.60  ch021  '"Tiếp theo."'    đương nhiệm 1,92s
  lo02      ch053  '"Bất bại?"'      đương nhiệm 1,92s
```

Hiếm theo **đoạn**, không hiếm theo **chương**: lô 1 gặp 0/30, lô 2 gặp 1/30. Ngoại suy thô sang
478 chương ra khoảng **tám chương** bị chặn vĩnh viễn, tức chừng ba giờ audio. Ngoại suy vẫn là
ngoại suy, và tôi đã sai ba lần vì đúng loại phép tính ấy — nó chỉ dùng để xếp ưu tiên.

### Bước đã làm trước đó: cho mẫu tự lộ ra, thay vì vá vội trước lô 2

**Chưa vá cơ chế.** Cân nhắc ngày 2026-09-09: mẫu này là 2 ca trên 38.520 đoạn, ngoại suy
khoảng bốn chương trên 478 — nên lô 2 (30 chương) nhiều khả năng gặp **không lần nào**. Thêm
một cơ chế mới chưa từng chạy thật ngay trước một lô 30 chương là tự chuốc rủi ro để đổi lấy
một kỳ vọng dưới một ca. Cơ chế xuất-bản-không-người-nghe được thêm vào trước lô 1 và chạy tốt,
nhưng nó **cộng thêm** (chỉ gỡ chặn); đường này **thay thế** một bản thu, và sai thì hỏng audio
chứ không chỉ hỏng lịch.

Việc làm được ngay mà không có rủi ro: `plan_repair_batch.py` giờ quét mẫu này trong những
chương hỏng và **cảnh báo trước khi người ta chạy lại**. Vì chạy lại không chữa được nó — luật
vứt ứng viên vẫn nguyên, nên thoát được chỉ là trúng một lần gieo khác.

Kiểm cả hai chiều: im lặng trên bốn chương hỏng của lô 1 (loudness, hai join, một nhịp — không
cái nào thuộc mẫu), và kêu đúng ca đã biết của alpha.60:

```
ch021  c00003_s0000129  '"Tiếp theo."'
   đương nhiệm chạm trần khung ở 1.92s; 2 ứng viên bị vứt (0.56s, 0.64s)
```

Lô 2 sẽ cho thêm dữ liệu về tần suất, và thiết kế đường riêng nên đợi dữ liệu ấy.

### Không có tai người, nhưng có sóng âm

Tôi đã viết ở đây rằng lập luận này "dựa trên đọc con số" và cần tai người mới xác nhận được.
Không hẳn: câu hỏi thật hẹp hơn nhiều — *bản thu này có chứa tiếng lẽ ra không được có ở đó
không?* — và sóng âm trả lời được. `scripts/burst_profile.py` chia bản thu thành ô 20ms và
tách "cụm tiếng" bằng khoảng im từ 0,15 giây:

```
đương nhiệm  1,92s  2 cụm   ..#####.##########.............................####################...
                            tiếng 0,04-0,36s   |   im 0,58s   |   tiếng 0,94-1,68s
ứng viên v0  0,96s  1 cụm   tiếng 0,04-0,42s
ứng viên v1  0,56s  1 cụm   tiếng 0,00-0,38s
ứng viên v3  0,96s  1 cụm   tiếng 0,00-0,34s
ứng viên v4  0,64s  1 cụm   tiếng 0,04-0,44s
```

Hai từ không nằm ở hai cụm cách nhau nửa giây. Và chi tiết đắt nhất: **mọi ứng viên đều dứt
tiếng trước 0,44 giây**, đúng bằng cụm *đầu* của bản đương nhiệm. Câu `"Tiếp theo"` dài chừng
0,35 giây; cụm thứ hai của bản đương nhiệm dài 0,74 giây — **gấp đôi cả câu**. Đó là tiếng
thừa, đúng cái Whisper nghe ra thành "À xong".

Cùng phép đo trên `"Gì cơ?"` chương 026: **ba cụm** cho một câu hai từ.

### Và một kết quả âm, đáng bằng kết quả dương

Cám dỗ tiếp theo là hiển nhiên: lấy **số cụm** làm phép kiểm mới, chặn mọi đoạn ngắn có ≥2 cụm.
Đo trước khi làm, trên 205 đoạn ngắn `verified` của alpha.60:

```
verified:  1 cụm ×178    2 cụm ×26    3 cụm ×1
failed  :  1 cụm ×3      2 cụm ×2     3 cụm ×1
```

**27 đoạn `verified` cũng có ≥2 cụm**, và nhìn nội dung thì chúng hoàn toàn bình thường:
`"Sai bét. Tiếp theo!"`, `"Tốt! Tuyệt vời!"` có dấu câu bên trong; `"Tại sao ư?"` chỉ là một
quãng ngập ngừng. Hai phân bố chồng nhau — **lần thứ hai** một đặc trưng âm học nghe rất hợp lý
lại không tách được gì, sau nhịp đọc.

Kết luận đứng vững: `burst_profile.py` là **kính lúp để nhìn một ca**, không phải cổng để chặn
hàng loạt. Thứ duy nhất tách sạch được vẫn là lời tự khai của bộ sinh, `generation_ceiling_hit`
— và cơ chế hiện tại đã dùng đúng nó.

Cái thuyết phục ở ca này không phải một tín hiệu mà là **ba tín hiệu cùng chỉ một hướng**: bộ
sinh khai chạm trần, sóng âm có cụm thừa dài gấp đôi câu thật, và ASR nghe ra chữ không có
trong văn bản — trong khi bốn ứng viên bị vứt không có tín hiệu nào trong ba.

---

## Bộ test ngủ thật, và điều đó làm tôi chẩn đoán sai hai lần

**Chưa sửa.** Chi phí là thời gian của người phát triển, không phải chất lượng sách — nhưng
2026-09-08 nó đã ăn của tôi hai lượt chạy và khoảng ba mươi phút.

`pipeline._process_segment_candidate` lùi dần giữa các lần thử lại bằng
`time.sleep(min(8, 2**attempt))` (pipeline.py:3817). Đúng cho lượt chạy thật — máy TTS cần
thời gian để hồi. Trong bộ test thì mọi giây ngủ ấy là giây thật.

Đo được: `test_final_locked_name_round_uses_audited_clause_split_and_promotes` vượt **90 giây**
mà chưa xong, và faulthandler dump ra đúng dòng `time.sleep`. Chạy trên cây đã vá và trên
worktree HEAD sạch cho **kết quả y hệt**, nên đây là chi phí sẵn có chứ không phải hồi quy.

### Vì sao đáng ghi chứ không chỉ đáng chịu

Triệu chứng của "đang ngủ" và của "đã treo" giống hệt nhau nếu chỉ nhìn từ ngoài: không có
dòng nào ra, và **CPU gần như không nhích** — tôi đo được 1 giây CPU trong 5 phút và kết luận
là deadlock. Giết. Chạy lại. Giết lần nữa. Cả hai lượt ấy có thể đã xanh.

Bài học rẻ hơn cho người sau: `time.sleep` không tốn CPU, nên **CPU phẳng không phải bằng chứng
của treo**. Bằng chứng là `-o faulthandler_timeout=N`, nó in ra ngăn xếp của cái đang chạy chậm
và trả lời trong một phút.

### Hình dạng bản sửa — **đã thử và bị chính phép đo bác bỏ** (2026-09-09)

Đề xuất cũ, giữ nguyên văn để thấy nó hợp lý đến mức nào: *"Một fixture `autouse` trong
`tests/conftest.py` monkeypatch `time.sleep` thành no-op cho những test không đo thời gian
thật. Rủi ro thấp: không test nào ở đây khẳng định điều gì về độ dài của lần lùi, chúng khẳng
định về số lần thử và trạng thái ứng viên."*

Tôi viết đúng fixture ấy rồi đo. Nó **làm bộ test chậm đi**:

```
test_successful_confirmation_decode_clears_initial_asr_false_negative
   ngủ thật     5,09 giây
   ngủ giả     89,65 giây          <- chậm gấp 17 lần
   một module: 49.598.670 lần gọi time.sleep
```

Vì `pipeline._wait_for_resources` không ngủ để **nhường lượt**, nó ngủ để **đợi đồng hồ**: ngủ
2 giây rồi hỏi lại bộ điều tiết, và bộ điều tiết chỉ nhả khi `stable_for` vượt
`idle_seconds_before_ramp` (20 giây, đo bằng `time.monotonic()`). Bỏ ngủ không rút ngắn 20 giây
ấy — nó biến vòng **chờ** thành vòng **quay tít**, đốt trọn một lõi để tới cùng một mốc.

Nhưng kết luận không phải "đừng đụng vào": phép đo cho thấy **hai loại ngủ trộn lẫn**, và chúng
nhìn từ ngoài giống hệt nhau.

```
_process_segment_candidate  time.sleep(min(8, 2**attempt))   ngủ để NHƯỜNG  -> bỏ được
_wait_for_resources         time.sleep(2.0) rồi hỏi lại      ngủ để ĐỢI ĐỒNG HỒ -> không bỏ được
```

Cùng một test cho thấy cả hai chiều: `test_final_locked_name_round_uses_audited_clause_split_
and_promotes` bỏ qua **220 giây** trong 36 lần ngủ và chạy trong 11,6 giây, tức nó thuộc loại
thứ nhất và bỏ ngủ giúp rất nhiều. Thời lượng không tách được hai loại — cả hai đều gọi
`sleep(2.0)` — nên muốn tách phải nhìn **hàm gọi**.

**Chưa làm phần tách ấy**, và cố ý: lợi ích là thời gian của người phát triển, còn phép đo đòi
chạy cả bộ test nhiều lần trong khi một lô đang tổng hợp — tức cướp CPU của chính thứ đang làm
ra sản phẩm. Để dành cho lúc không có lô nào bay.

### Cái đã làm: `tests/conftest.py` **đếm** chứ không bỏ

Nó bọc `time.sleep`, cộng dồn, rồi ngủ thật — không đổi hành vi một chút nào — và in ở cuối:

```
[conftest] ngồi chờ 246 giây trong 102 lần time.sleep.
2521 test xanh trong 519 giây      ->  47% thời gian bộ test là ngồi chờ
```

**Con số 826 giây / 11.724 lần mà tôi trích ở trên là của chế độ BỎ ngủ**, và chênh lệch trăm
lần về *số lượt gọi* chính là bằng chứng cho kết luận: khi `sleep` là no-op, vòng chờ quay tít
và gọi hàng nghìn lần để tới đúng cái mốc đồng hồ mà một lần ngủ 2 giây đã tới. Hai con số ấy
không so sánh trực tiếp được với nhau, và tôi đã suýt trích nhầm cái sau như thể nó mô tả lượt
chạy bình thường.

Nên phần **thật sự** cắt được, nếu tách được ngủ-nhường khỏi ngủ-đợi-đồng-hồ, nhiều nhất là
khoảng 4 phút mỗi lượt chạy — không phải 14.

Cái nó mua là **khả năng nhìn**, đúng thứ đã thiếu hôm 2026-09-08 khi tôi giết hai lượt chạy vì
tưởng treo. `EBOOK_TESTS_REAL_SLEEP_OFF=1` bật lại chế độ bỏ ngủ, để đo lại kết luận trên chứ
không phải để chạy nhanh hơn.

Chưa làm vì chưa đo tổng: cần biết bộ test mất bao nhiêu giây trong `time.sleep` trước khi nói
sửa nó đáng bao nhiêu. Cách đo rẻ: `-o faulthandler_timeout=30` một lượt rồi đếm số dump rơi
vào dòng 3817.

---

## `TTS_PACE_BAND_RELAXED` chặn chương, và cái tên gợi ý điều ngược lại

**Đã giải quyết** — `patch_pace_relaxed_is_a_decision`, commit `4d2d39a`. Mục này giữ lại vì
kết luận đầu tiên của tôi ở đây **sai**, và cái sai ấy là một bài học về đo đạc chứ không phải
về nhịp đọc. Chương 007 của lô 1 hỏng vì:

```
High-quality policy requires repair or review for segment warnings:
c00008_s0000058_b47b5843ed04=TTS_PACE_BAND_RELAXED
```

(Bản đầu của mục này chép thiếu đuôi `_RELAXED`. Không phải chi tiết nhỏ: đọc `TTS_PACE_BAND`
thì bản vá — vốn chỉ nhận `TTS_PACE_BAND_RELAXED` — trông như không khớp với chính chương nó
sinh ra để cứu. `last_error` của chương 007 trong lô 1 ghi đủ đuôi.)

Đoạn ấy: `"C-Cái con ả này! Cô ta đang hả hê trước nỗi đau của tôi đấy à?!"` — phân tích gán
nhịp **`fast`**.

**Bản đầu của mục này viết 11,22 ký tự/giây. Con số ấy sai.** Tôi tính lại từ `signal_json` của
chính đoạn ấy và ra:

```
chars_per_second 13,06   pace_outlier 0   pace_band_relaxed 1
```

Sai vì tôi coi `pause = 0` khi trường ấy **vắng mặt**, trong khi vắng mặt nghĩa là "không đo",
không phải "bằng không" — và thời gian nghỉ nằm ở mẫu số. Chênh lệch nhỏ, nhưng nó **đảo ngược
kết luận**: 11,22 nằm ngoài băng `normal`, còn 13,06 nằm trong ([12,5 – 24,5]). Đoạn ấy chỉ
trượt **sàn của băng `fast`** (14,0).

### Chỗ chưa hiểu

Mã hiện tại trên đoạn là `TTS_PACE_BAND_RELAXED`, và `PACE_BAND_RELAX_ATTEMPTS = 4` — đường ống
thử lại bốn lần **chấm theo sàn `normal` thay vì theo băng đã yêu cầu**. Tức nó đã tự nhượng bộ
một lần rồi mới gắn nhãn ấy.

Nhưng nhãn ấy **không** nằm trong `HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS`, nên nó chặn chương.
Hai cách đọc, và chưa biết cách nào đúng:

- *"đã đạt theo băng nới lỏng"* → chặn là **mâu thuẫn**: đường ống nhượng bộ rồi cổng phủ nhận
  nhượng bộ ấy.
- *"đã nới lỏng mà vẫn không đạt, đành giữ bản đang có"* → chặn là **nhất quán**.

Với con số đúng, **cách đọc thứ nhất thắng**: 13,06 ≥ 12,5, `pace_outlier = 0`,
`pace_band_relaxed = 1` — đường ống đã thu lại bốn lần, không lần nào chạm 14,0, rồi tự nhượng
bộ và chấp nhận bản trong băng `normal`. Cổng chương sau đó phủ nhận đúng cái nhượng bộ ấy.
Cái tên gợi ý đúng ngay từ đầu; chỉ có phép đo của tôi là sai.

Cách vá: đưa `TTS_PACE_BAND_RELAXED` vào `MACHINE_ACCEPTABLE_SEGMENT_WARNINGS` — **không** vào
`HIGH_QUALITY_ALLOWED_SEGMENT_WARNINGS`. Bản vá đầu của tôi làm đúng cái sau và bộ test bắt
được: ALLOWED làm mã ấy **im lặng**, vứt mất tín hiệu "nên có người nghe"; MACHINE_ACCEPTABLE
cho qua nhưng **ghi sổ**. Xem [SHIPPING_WITHOUT_A_LISTENER.md](SHIPPING_WITHOUT_A_LISTENER.md).

Một dải nhịp bị làm phẳng là một **đánh đổi**, không phải một khuyết tật — đó là ranh giới giữa
hai bảng. Một `pace_outlier` thì ngược lại: phép kiểm nói bản thu hỏng, và máy không được tự
cho qua.

### Lô vá chạy lại chương 007, và bản vá **không** được chứng minh

Cùng đoạn ấy, cùng dây gieo, chạy lại ngày 2026-09-09:

```
lô 1     chars_per_second 13,06   pace_band_relaxed 1   -> TTS_PACE_BAND_RELAXED, chặn chương
lô vá    chars_per_second 14,07   (không có cờ nới)     -> verified, không cảnh báo nào
```

Sàn của băng `fast` là **14,0**. Hai lần thu cùng một câu rơi hai bên vạch: lần đầu hụt 0,94,
lần sau vượt **0,07**. Nên chương 007 qua được lần này, và `patch_pace_relaxed_is_a_decision`
**chưa hề chạy** — đường nới lỏng không được kích hoạt lần nào.

Phải nói rõ như thế. Một chương xanh không phải bằng chứng cho bản vá nếu bản vá không chạy;
nhầm hai thứ ấy là cách người ta tin vào một cơ chế chưa từng được thử.

Hai điều phép đo này **có** nói:

- Nó là ví dụ sạch cho [AUDIO_IS_NOT_ALWAYS_REPRODUCIBLE.md](AUDIO_IS_NOT_ALWAYS_REPRODUCIBLE.md):
  cùng văn bản, cùng giọng, hai lần thu chênh nhau 7,7% nhịp đọc.
- Với đoạn này, vạch 14,0 nằm **giữa** phân bố các lần thu của chính nó, nên mỗi lượt chạy là
  một lần tung đồng xu. Đó vừa là lý do bản vá đáng tồn tại, vừa là lý do không nên chờ nó
  chứng minh mình trong một lô — nó chỉ hiện ra ở khoảng một nửa số lượt.

### Chi tiết "chưa khớp" — đã kiểm, không phải lỗ hổng

`segment_candidates` của đoạn này **rỗng** dù `PACE_BAND_RELAX_ATTEMPTS = 4`, và tôi ghi nó là
"cùng hình dạng với lỗ hổng trần khung". **Sai.** Đọc code:

```
_retry_in_normal_pace_band  →  allocate_segment_candidate : KHÔNG
                               mark_generating            : có
                               synthesize_atomic          : có
                               mark_signal_passed         : có
```

Nó ghi thẳng vào segment, không đi qua bảng candidate. Nên bốn lần thu lại **có xảy ra thật**;
chúng chỉ không để lại dấu ở nơi tôi đi tìm. Khác hẳn lỗ hổng trần khung, nơi đoạn ấy **không
được thu lại lần nào**.

Còn lại một khoảng mù nhỏ và thật: `segment_candidate_attempt_summary` không thấy bốn lần ấy,
nên nhìn vào lịch sử ứng viên thì một đoạn đã qua bốn vòng nới lỏng trông y hệt một đoạn chưa
thử gì. Đó là chuyện quan sát được, không phải chuyện chất lượng — nhưng nó vừa làm tôi mất một
lượt truy sai hướng.

## Bộ cấp phát giọng không biết ai cùng chương

**Chưa vá.** Lô 1 có ba cặp nhân vật có tên dùng chung đúng một `voice_key`, và một cặp trong
số đó nói **trong cùng chương 023** — chỗ duy nhất người nghe thật sự lẫn.

Tôi mở mục này với tiêu đề *"kho giọng nam đầy 14/14"* và nó **sai**. Phép trừ đúng (14 nhân vật
nam có tên, 14 chỗ cấp được) nhưng câu hỏi sai: người nghe nghe từng chương một. Tô màu đồ thị
đồng hiện của lô 1 cần **7 giọng nam**, và 7 cũng là cận dưới (chương 023 có 7 người nam cùng
nói). **Kho gấp đôi cái cần dùng; cả ba va chạm đều tránh được.**

**Hai trong ba chỗ đã vá** (2026-09-09). Còn lại chỗ thứ ba, và nó **hạ ưu tiên**: sau khi
`reserve()` đánh dấu đúng bậc, kho nam còn 6 chỗ trống lúc lô 2 bắt đầu, mà lô 1 (30 chương)
chỉ sinh thêm **một** nhân vật nam có tên. Nên việc buộc phải cho hai người dùng chung giọng
chưa xảy ra lại trong khoảng sáu lô nữa. Cái đáng canh vẫn là **chương đông nhất**, không phải
tổng cast.

Truy tiếp thì hỏng ở **ba chỗ chồng lên nhau**, và chỗ giữa là bug thật:

1. Thang biến thể formant là vòng modulo — `variants[variant_usage[name] % len(variants)]` —
   nên người thứ 8 trên preset 7 bậc quay về bậc 1 mà không kiểm tra bậc ấy đã có chủ chưa.
   Thái Sơn nhận 9 người, quay 2 lần. Chín trên bảy thì phải dùng lại; phần này không phải lỗi.
2. **`reserve()` chỉ nhận tên preset**, nên một giọng đã ghim làm bộ đếm nhích một bậc *bất kỳ*
   thay vì đánh dấu bậc nó đang giữ. Thanh Bình có 7 người, 7 bậc, mà chỉ ra 6 giọng: bậc
   `0,898` bỏ phí trong khi `f104` phát cho hai người. `_reserve_pinned_voices` cầm cả
   `formant_ratio` lẫn `voice_key` rồi vứt đi. Va chạm này **tránh được hoàn toàn**.
3. Sau khi vá 1 và 2, 16 người đòi 14 chỗ vẫn còn hai lần phải dùng chung — và lúc ấy mới tới
   câu hỏi *ai* dùng chung với ai, thứ cần đồ thị đồng hiện. **Chưa vá**, và chưa cần: đo lúc
   lô 2 khởi động, kho nam còn 6 chỗ.

Chỗ 1 (`reserve()` đánh dấu đúng bậc) đã vào cây ở commit `bda3283`. Ngoài ra `port_casting.py`
đổi luật khi buộc phải chia lại: giữ người được nghe nhiều hơn thay vì bỏ pin của cả hai — ba
nhân vật bị đúc lại thay vì sáu ở ranh giới lô 1 → lô 2.

Ba hướng nới kho — pitch, biên formant, trả giọng miền Trung cho NPC — đều đã bị đo bác bỏ, và
[TWO_CHARACTERS_ONE_VOICE.md](TWO_CHARACTERS_ONE_VOICE.md) ghi từng cái kèm phép đo, vì cả ba
đều nhắm vào một vấn đề không tồn tại.

Cái đáng canh không phải tổng cast mà là **chương đông nhất**: hôm nay 7 trên 14.
Đo bằng `python scripts/voice_pool_pressure.py <project>`.

## Một nhân vật bị tách đôi vì Ollama rơi dấu (2026-09-10)

**Đã vá một nửa; nửa còn lại chờ ranh giới lô 3 → 4.** Lô 3 va chạm giọng gấp đôi lô 2, và truy
ra thì kho giọng không phải thủ phạm chính:

```
            THỦ LÃNH   THU LÃNH        NGƯỜI TRẢ LỜI   NGUOI TRA LOI
lô 2          111         14                185              37
lô 3           32         66  <- trội        46             160  <- trội
```

Nguồn văn bản của 62 chương **không chứa** chuỗi nào trong số ấy: đó là nhãn Ollama tự đặt cho
vai, và nó rơi dấu ngẫu nhiên. `_known_summary` đưa bản nhiều lần hơn vào prompt lô sau, nên cái
sai tự củng cố và đến lô 3 thì bản sai thành bản trội. Hậu quả: một người hai giọng (THỦ LÃNH ghim
f100_p-07 từ lô 1, THU LÃNH ghim f090_p-04 mới), và mỗi bản tách chiếm một chỗ trong kho 14 giọng
nam — lô 3 hết kho sớm hơn dự đoán một phần vì thế.

Luật gộp là **tập con dấu**, không phải "bỏ dấu ra giống nhau": MÁ và MÀ vẫn là hai từ. Người
thắng là bản **nhiều dấu nhất**, không phải bản nhiều lần nhất — vì số lần đã bị vòng phản hồi
làm nhiễm.

- `scripts/name_marks.py` + `port_casting` gộp **ngay khi gieo** (đã vào cây; lô 4 gieo từ lô 3
  sẽ mang 36 giọng ghim và THỦ LÃNH giữ f100_p-07 — giọng 321 câu qua ba lô, không phải f090).
- `patch_dropped_marks_are_the_same_name` gộp **trong registry** (hàng chờ, áp trước lô 4), để
  chính lô 4 không tách lại.
- `tests/test_name_marks_agree.py` ghim hai bản không lệch nhau.

Còn một họ khác lộ ra cùng lúc: tên ngắn / tên đầy đủ. Đếm ngay thay vì đợi lô 4:

```
lô 1   0 cặp
lô 2   1 cặp   ALICE (3 câu)  <  ALICE DRACEN (2)
lô 3   3 cặp   ALICE (25)     <  ALICE DRACEN (0)
                ALICE (25)     <  ALICE VIC. DRAKEN (1)
                SELNE (32)     <  SELNE VALKRYN (3)
```

Đang lớn, và `ALICE` có **ba** cách viết với hai họ khác nhau — model không chỉ thêm họ, nó bịa
họ. Hướng gộp **ngược** với lớp rơi dấu: bản ngắn giữ gần hết câu, bản dài là nhãn lạc 0–3 câu.
Rủi ro thật là JAKE / JAKE SMITH cha con, nên luật phải thận trọng: bản dài ≤ 3 câu **và** bản
ngắn ≥ 10 lần bản dài — bốn cặp trên đều lọt, một cặp cha con thật thì không (hai người thật đều
có câu). *Không* có điều kiện cùng giới: tầng chuẩn hoá tên chạy trước tầng phân giải giới, nên
hai ngưỡng số câu là toàn bộ chốt chặn. `patch_stray_surname_is_the_same_name` (hàng chờ, thứ 3).
Bản dài `ALICE VIC. DRAKEN` đã kịp va chạm giọng với THALIA ở lô 3.

Một bài học nhỏ khi xếp nó vào hàng: bản vá này chèn một pass ngay trước dòng `aliases_by_target`,
và neo của bản rơi dấu kéo từ khối chọn đại diện xuống đúng dòng ấy — áp họ-bịa trước là bản rơi
dấu trượt neo (`khong khop pass chuan hoa`), dừng sạch, không ghi gì. Thu hẹp neo bên rơi dấu
lại, đo lại cả hai thứ tự trên hai bản sao: cùng một `character_registry.py` byte-một, 52 bài
registry xanh cả hai. Ghi lại vì docstring ban đầu tuyên bố "áp thứ tự nào cũng được" mà chưa
thử — tuyên bố độc lập không phải phép đo.

## Nấc quay vòng của bộ cấp phát giọng mù-theo-chương — không còn hoãn được (2026-09-10)

Mục *"Bộ cấp phát giọng không biết ai cùng chương"* ở trên hạ ưu tiên chỗ này vì "kho còn 6 chỗ,
lô 1 chỉ thêm 1 nam". Lô 3 thêm **~7** nam mới; 18 người đòi 14 chỗ, nấc quay vòng chạy thật, và
3 trong 7 va chạm nằm cùng chương — `KANG + SAMAEL` (066, 071), `IGOR + THU LÃNH` (062, đã vào
audio: 3 + 23 câu). Ước lượng "6 lô nữa" sai vì nó ngoại suy từ một lô. Bản vá phần 3 viết trong
`patch_wrap_prefers_a_stranger` (hàng chờ).


## Ranh giới không người — ba thứ phải đúng trước khi nó tự chạy (2026-09-10, tối)

Cả hai lần chủ sách hỏi "sao lại dừng?" đều rơi vào khoảng giữa hai lô. Lô 3 xong lúc nào không
ai biết trước (nhịp đo 18:29→18:53 là 745 segment/giờ, trung bình cả lô là 208), và một ranh giới
là năm lệnh nối tiếp — không lệnh nào cần người; cái cần người là **đọc** kết quả, và việc ấy làm
sau cũng được. `scripts/boundary.sh` làm cả năm. Nhưng để nó chạy được không người, ba chỗ đang
dựa vào tay phải đổi:

1. **`apply_all --apply` tự rút hàng chờ.** Cửa số 3 của `before_a_batch` đọc chính `ORDER`;
   hàng chờ còn tên là lô sau không bao giờ bắt đầu. Ở ranh giới lô 2 tôi rút tay *sau* khi vân
   tay lượt xanh đã ghi, nên gate chạy lại cả bộ test trên một cây chỉ khác đúng chỗ hàng chờ.
   Giờ rút **trước** bộ test: cây được kiểm là cây được commit. Bài kiểm chạy trên chính bố cục
   file thật (bản sao) chứ không chỉ bản mẫu, và nó bắt ngay một lỗi: chuỗi `ORDER: ... = ()`
   xuất hiện lần nữa *trong mã của chính hàm rút*, nên thay theo chuỗi là hỏng hàm — phải neo
   cột 0.

2. **Project đúc lại giọng phải nối đuôi, và lô sau gieo từ cái cuối.** `launch_repair.sh` gieo
   mọi chương từ project lô — đúng khi mọi giọng đều ghim, sai ngay khi có người bị bỏ ghim vì
   trùng giọng: mỗi chương cấp lại độc lập, KANG có thể ba giọng ở ba chỗ, và không cổng nào
   bắt vì từng project tự nó nhất quán. Một luật cho cả ba script (`seed_chain.py`), cộng hai
   thứ đi kèm: sổ cộng dồn được `port_casting` chép sang project đích (đo thật lô 2 → project
   nháp: 36 tên = 36 tên), và `backfill_exposure` đếm mỗi chương **một lần** theo tiêu đề,
   project sau thắng — năm chương đúc lại không còn là năm chương đếm đôi.

3. **`ls -dt` nói dối.** Thư mục `lo02_4d783ac744` "trẻ" hơn cả ba project vá của nó, vì SQLite
   tạo/xoá `-wal`/`-shm` mỗi lần ai đó mở DB và mtime thư mục đi theo. `book.created_at` thì
   không đổi. Bài kiểm đặt mtime thư mục lô lên năm 2286 và đòi câu trả lời không đổi.

Cái `boundary.sh` KHÔNG làm là đọc kết quả thay tôi: nó ghi số va chạm cùng chương của từng
project đúc lại vào `runtime/boundary_03.log` — 0 ở 066/071 là bằng chứng của
`patch_wrap_prefers_a_stranger` (062/084/086 hết va chạm nhờ gộp tên, không chứng minh gì) —
và đi tiếp cả hai trường hợp, vì va chạm là lỗi chất lượng sửa được bằng một lô đúc lại nữa,
không đáng để GPU ngồi không tới lúc có người nhìn.

Một phép đo tiện thể, đáng ghi vì nó ngược với điều tôi tin: ba lượt bộ test đầy đủ (18:31,
18:33, 18:50) trong khi lô 3 đang bay **không** làm bộ điều tiết đổi chế độ — không một dòng
`Resource mode:` nào sau 17:48:33. Trước đó tôi giả định "chạy test là cướp CPU của lô" (và
`before_a_batch` bỏ qua test vì thế). Vậy 65,6 phút `yield_heavy` của lô 3 ("foreground CPU
81%", 17 segment) là của ai — và `foreground` đo cái gì mà không thấy pytest? Chưa trả lời;
`resource_manager.py` là file khoá nên đọc thì được, đổi thì đợi ranh giới.

## Chương 075: thước nhịp lệch lần thứ hai, và bản vá thứ tư vào hàng chờ (2026-09-10, 19:55)

Chương hỏng đầu tiên của lô 3 là một câu dẫn 38 ký tự mất 10/10 lần ở 10,6–11,8 chars/s (sàn
12,5), không chia được (< 100), dải đã `normal` — mọi đường cứu đóng. Không phải seed: câu toàn
từ ngắn (2,25 chữ/từ, kho 3,33), và theo âm tiết nó đọc 4,48/giây, gần trung vị kho 4,67. Cùng
họ với lỗi chữ số. `patch_pace_counts_syllables_too`: một bản thu chỉ chậm khi chậm theo **cả**
chữ lẫn âm tiết; sàn âm tiết 3,75 là p2 của 8.301 bản thu đã qua. Chi tiết và số liệu ở
[PACE_COUNTS_THE_WRONG_STRING.md](PACE_COUNTS_THE_WRONG_STRING.md) (chương hai).

Xếp thứ tư — file khác (`audio_io.py`) nên không chạm neo ba bản registry. Ranh giới tự chạy
sẽ áp nó trước lô vá của lô 3, và chương 075 chạy lại là phép thử: câu ấy phải qua **lần đầu**.

Tổng diễn tập ranh giới trên bản sao đủ bố cục (`Ebook Reader.vbs`, `.lnk`): `apply_all
--apply --force` áp ba bản, tự rút hàng chờ, bộ test đầy đủ xanh, mã thoát 0. Bốn bản áp chồng
trên bản sao khác: test audio + registry xanh.

## Hoãn: khi mọi lần thử chỉ hỏng vì "chậm", giữ bản thu gần dải nhất thay vì mất chương

Ghi để không quên, không làm tối nay. Đường đi của chương 075 cho thấy một ngõ cụt cấu trúc:
`pace_outlier` ở high_quality là **ném lỗi để thử lại** (`pipeline.py`, "high-quality TTS retry
required"), mười lần rồi chia nhỏ, và câu dưới 100 ký tự thì không chia được. Mười bản thu ấy
không được giữ làm ứng viên (`segment_candidates` của segment ấy: 0 dòng) — chúng bị ghi đè
từng lần, nên lúc cạn không còn gì để đề cử.

Nhưng "chậm" không phải "hỏng": `TTS_PACE_OUTLIER` đã nằm trong danh sách cảnh báo được phép
của high_quality, và học thuyết của hai bảng chấp nhận là *chỉ những phép kiểm không nói bản
thu hỏng*. Nếu mười lần đều chỉ hỏng vì chậm (không ASR, không lặp, không trần), bản gần dải
nhất là một bản thu nghe được kèm một cảnh báo — tốt hơn hẳn một chương không xuất bản. Cùng
hình dạng với `patch_finished_take_beats_a_cut_off_one`: đường ống chỉ đề nghị, tầng database
kiểm bốn điều kiện từ chính dữ liệu, ghi vào bảng riêng.

Bản vá âm tiết đã đóng phần lớn lớp này (câu toàn từ ngắn) mà không cần tới đây. Cái này chỉ
đáng làm nếu lô 4 vẫn mất chương vì "chậm" sau bản vá ấy — đếm trước, rồi mới viết.

## 170 cờ neo tên mỗi lô, và chỉ một trong số đó là lỗi thật (2026-09-10, 21:30)

`ASR_LOCKED_NAME_ANCHOR_REVIEW` (147 đoạn ở lô 3) và `_MISMATCH` (23) đều không chặn chương, nên
170 đoạn mỗi lô đi qua mà không ai nhìn. Đo cả 3.923 phép kiểm neo bằng
`scripts/name_is_read_the_same_way.py` và tách hai câu hỏi vốn bị trộn: *"có thoả cổng không"*
khác *"có được đọc giống nhau mỗi lần không"*. Chi tiết ở
[A_NAME_READ_MANY_WAYS.md](A_NAME_READ_MANY_WAYS.md); ba con số quyết định:

- `Awakened` đọc **giống nhau 66/66 lần** mà trượt cổng 68 lần (Whisper viết `awaken`, cổng chờ
  `awakened`). Cổng sai, audio đúng — không có gì để sửa ở giọng.
- `Willem → Guy-lem`: `'lem'` chiếm 297/512, tức bộ ghép gán **một** token cho neo hai âm tiết
  rồi so `guy-lem` với `lem`. Lỗi cửa sổ ghép, không phải lỗi đọc.
- `Jake → Giếch`: **1.827 neo qua cả ba lô, 0% khớp ở cả ba, và `đỉnh%` tụt 33 → 15 → 13.** Cùng
  một câu ra `Giật` rồi `Dịch` — hai âm khác nhau. Đây là lỗi thật, và nó là **cái duy nhất**
  trong danh sách mà cổng đang nói đúng.

Việc phải làm, và nó là **một dòng dữ liệu chứ không phải một dòng mã**: đổi `spoken_form` của
`Jake` (bảng `pronunciations`, id 132, `Giếch`). Tôi đã viết sai một lần ở đây — rằng bảy cái
tên có "hai dòng trong sổ" và chỉ cần bỏ dòng tệ hơn. Sổ có **một** dòng mỗi tên; cái thứ hai
tôi đếm là `pronunciation_delivery_variant`, hai biến thể giao mà đường ống sinh cho mỗi đoạn —
đọc theo dạng ghim (`locked_spoken_v1`) và đọc thẳng chữ viết gốc (`source_spelling_v1`), cả
hai đều bị ASR chấm. Kiểm bằng `SELECT * FROM pronunciations WHERE surface='Jake'` trước khi
viết mục này thì đã không sai; tôi kiểm sau.

Tách theo biến thể thì số nói rõ hơn hẳn: `Jake` đọc theo dạng ghim `Giếch` cho `đỉnh` **13%**,
còn đọc **thẳng chữ viết** `Jake` cho **44%** — dạng ghim làm giọng kém ổn định hơn cả khi không
có nó. Ngược lại `Samael → Xa-men` khớp 69% so với 2% khi đọc thẳng chữ, tức dạng ghim ở đó làm
đúng việc. Vậy ứng viên đầu tiên cho `Jake` không cần đoán: chính chữ viết gốc, đã đo trên cuốn
sách này. Giá của việc sửa hẳn: **đọc lại 182 đoạn trên 18 chương** trong số 92 chương đã có.

Thứ tự quan trọng: **đừng nới cổng trước khi sửa dạng đọc.** Nới trước là làm mất đúng cái cảnh
báo đang nói thật về `Jake` — và nó đã nói thật 1.827 lần.

Một giả thuyết của tôi bị bác trong lúc đo: các dạng chèm âm `ờ` (`I-xờ-hờ-ta-ra`, `Đờ-ra-kên`)
trượt cổng 2,4% so với 27,4%, nhưng `đỉnh%` **giống nhau** (50,0 so với 51,9) — chúng đọc ổn định
ngang các dạng khác, chỉ không bao giờ thoả cổng. Và ca xấu nhất, `Giếch`, không chèm âm nào.

## Nguồn văn bản là quan toà, và tôi đã dùng số câu thay cho nó (2026-09-10, 21:40)

`patch_stray_surname_is_the_same_name` vừa áp ở ranh giới lô 3 gộp `SELNE VALKRYN` → `SELNE`,
chọn người thắng theo **số câu thoại** (32 so với 3). Đếm trong nguồn:

```
Selene   198 lần trong nguồn      SELENE   7 câu thoại
Selne      0 lần                  SELNE   32 câu thoại   <- bản model viết sai, và nó ĐANG thắng
```

Nhân vật thật tên **Selene**. `SELNE` là lỗi chính tả của model phân tích, và nó thắng vì nó nói
nhiều hơn — đúng cái vòng phản hồi tôi đã ghi cho lớp rơi dấu (`_known_summary` đưa bản nhiều lần
hơn vào prompt lô sau, cái sai tự củng cố). Lớp rơi dấu có một tín hiệu nội tại để phá vòng ấy
(bản nhiều dấu hơn thắng). Lớp sai một ký tự thì **không** có — nhưng nó không cần, vì có một
quan toà tốt hơn số câu, và tôi đã không hỏi: **chính cuốn sách**.

Đếm trên cả 30 nhân vật có tên của lô 3, so với 92 chương nguồn (bỏ dấu, không phân biệt hoa
thường): **4 cái tên không xuất hiện lấy một lần**.

```
SELNE                32 câu thoại    0 lần trong nguồn
SELNE VALKRYN         3              0
SAMAELE               1              0        (Samael: 1.375 lần)
NARRATOR              1              0        (vai, không phải người - lọt vào bảng characters)
```

Ba trong bốn là bản viết sai hoặc nhãn bịa; cái thứ tư là một vai bị lọt. Không một nhân vật
thật nào có 0 lần. Đây là một phép phân biệt **dứt khoát**, rẻ, và đã nằm ngay trên đĩa.

Luật đề nghị: **khi hai cách viết cạnh tranh, cách nào có trong nguồn thì thắng — số câu chỉ
dùng khi cả hai đều có (hoặc cả hai đều không).** Nó làm đúng cả bốn ca đã đo:

- `SELNE` (0 lần) → `SELENE` (198) — sửa đúng cái mà bản vá vừa gộp *ngược*;
- `SAMAELE` (0) → `SAMAEL` (1.375);
- `SỐ BA` (2 câu) và `SỐ BẢY` (7 câu) — **cả hai** có trong nguồn, nên **không gộp**. Đây là ca
  mà một luật "lệch một ký tự thì gộp" sẽ nhập hai nhân vật thật làm một; ngưỡng tỉ lệ cứu được
  (4×), nhưng nguồn văn bản cứu **chắc chắn**;
- `THU LÃNH` / `THỦ LÃNH` — bỏ dấu thì cả hai trỏ về cùng một chuỗi trong nguồn, nên luật này
  không can thiệp và luật rơi dấu vẫn quyết. Hai luật không tranh nhau.

**Chỗ làm:** `scripts/` chứ không phải file khoá. `port_casting.read_casting` đã gộp rơi dấu ở
thời điểm gieo; thêm một vòng gộp theo nguồn ở cùng chỗ là đủ để lô 4 thấy `SELENE` trong danh
sách "đã biết" và dùng nó. Đường tới nguồn có sẵn trong chính project: `chapters.input_path`.

**Module đã vào cây** (`scripts/source_spellings.py`, 7 bài kiểm) và đã thử end-to-end trên bản
sao `port_casting` với chính project lô 3: danh sách "đã biết" ra `SELENE` thay cho `SELNE`,
không còn `SAMAELE`, `THỦ LÃNH` giữ dấu, và `SỐ BA` / `SỐ BẢY` **cả hai còn nguyên**.

**Nhưng chưa nối vào `port_casting`**, và lý do đáng ghi vì nó không phải "sợ sửa file đang chạy"
— chuyện ấy giải được bằng ghi nguyên tử. Ranh giới gọi `port_casting` ở bước 4 cho từng chương
đúc lại, và **gộp tên ở thời điểm gieo đổi cả cái pin**: `SELNE VALKRYN` sẽ được ghim dưới tên
`SELENE`, rồi phân tích của chương đúc lại — registry chưa mang luật nguồn — lại sinh ra `SELNE`,
không khớp pin, và nhân vật ấy bị đúc **giọng mới**. Hai trong năm chương đúc lại (084, 086) có
đúng nhân vật ấy. Nối vào giữa ranh giới là đổi kết cục của chính phép thử đang chạy, theo một
đường tôi chưa lần hết.

Nối ở ranh giới lô 4 → 5, cùng lúc với bản chính của luật vào registry, và thử như một đơn vị.
Giá của việc đợi: lô 4 mang `SELNE` thêm một lô nữa trong prompt "đã biết" — nhãn người nói không
được đọc lên, nên không có gì người nghe nghe thấy.

Ghi thêm một hệ quả nhỏ nhưng thật: `SELNE` đang giữ 32 câu thoại và một chỗ trong kho giọng
dưới tên sai. Sửa nhãn **không** đổi audio (nhãn người nói không được đọc lên), nên đây là lỗi
dữ liệu lan sang lô sau, không phải lỗi người nghe nghe được. Đừng đọc lại chương nào vì nó.

### Nửa thứ hai đã viết, và cố ý CHƯA vào `ORDER` (21:58)

`scripts/pending_patches/patch_the_book_decides_the_spelling.py` mang luật ấy vào registry, kèm
`tests/test_the_book_decides_the_spelling.py` (5 bài) và `tests/test_source_spellings_agree.py`
(6 bài, giữ hai bản không lệch — cùng cách `test_name_marks_agree.py` giữ luật rơi dấu). Áp thử
trên bản sao: **11 bài xanh**.

Nhưng nó **chưa** được xếp vào `ORDER`, và đây là lý do đáng ghi vì nó ngược với phản xạ: cửa số
3 của `before_a_batch` **từ chối khi hàng chờ còn tên**. Xếp bản vá vào hàng chờ lúc này là làm
`launch_batch.sh 4` ở bước 6 của ranh giới không bao giờ chạy được — tức tự chặn chính cái lô
mình đang chờ. Xếp vào sau khi lô 4 đã bay.

## Sửa dự đoán trước khi có kết quả: lô đúc lại có thể KHÔNG thử được bản vá quay vòng (22:10)

Tôi đã viết rằng trong năm chương đúc lại, "chỉ 066/071 là phép thử thật" của
`patch_wrap_prefers_a_stranger`, vì KANG và SAMAEL là hai người thật. Đếm lại kho giọng trong
chính project đúc lại thì câu ấy **chưa đủ**, và có thể sai hẳn.

`CHARACTER_FORMANT_STEPS` có 7 bậc mỗi preset, hai preset nam nên 14 bậc. Project đúc lại được
gieo 36 giọng ghim; trong đó các bậc nam đã có chủ:

```
Thái Sơn      0,87  0,93  0,97  1,00  1,04  1,08  1,16     -> ĐỦ 7 bậc
Thanh Bình          0,93  0,97  1,00  1,04  1,08  1,16     -> 6 bậc, THIẾU 0,87
```

(`Thanh Bình 0,898` cũng có ghim nhưng đó là biến thể theo tuổi, không phải bậc trên thang; và
`formant_ratio_bounds_for_preset` cho cả hai preset nam là 0,85–1,20 nên bậc 0,87 **không** bị
kẹp vào 0,898 — đã tính, không đoán.)

Vậy **13 trên 14 bậc nam đã có chủ, còn đúng một bậc trống**: Thanh Bình 0,87. KANG bị bỏ ghim
khi thua SAMAEL, nên nó sẽ được đúc lại — và kết cục phụ thuộc allocator xếp preset nào trước:

- xếp **Thái Sơn** trước (đủ 7 bậc) → không còn bậc trống → nấc quay vòng chạy → **đây mới là
  phép thử**;
- xếp **Thanh Bình** trước → thấy 0,87 trống → lấy luôn → bản vá **im lặng**, không thử gì.

Cả hai nhánh đều chữa được va chạm của chương 066, nên "chương xanh" **không** phân biệt được
chúng — đúng cái bẫy tài liệu này đã ghi. Thứ phân biệt là giọng KANG nhận: `f087` nghĩa là bậc
trống, tức chưa thử; một bậc đã có chủ nghĩa là nấc quay vòng đã chạy, và lúc ấy mới đọc xem nó
chọn người **không cùng chương 066** hay không.

Nơi bản vá chắc chắn bị thử là **lô 4**, nơi 18+ người nam thật tranh 14 bậc. Lô đúc lại vẫn là
chỗ tệ để chứng minh, và lần này lý do cụ thể hơn: pin lấp gần hết thang, nhưng "gần hết" khác
"hết".

## Lô đúc lại của lô 3: bản vá quay vòng chạy đúng một nửa (2026-09-10, 23:30)

Ranh giới tự chạy xong lúc 23:24 — năm chương đúc lại, lô 4 khởi động, và đây là lần đầu
`patch_wrap_prefers_a_stranger` chạy thật. Kết quả đo trên từng project:

```
lo03r_062  0 va chạm cùng chương
lo03r_066  0
lo03r_071  1        <- KANG + THẰNG ĐIÊN, cùng preset_thanh_binh_f100_p-04
lo03r_084  0        (nhưng chương FAILED - xem dưới)
lo03r_086  0
```

**Nửa đúng, và nó là bằng chứng thật cho bản vá.** Thang `Thanh Bình` có 7 bậc và cả 7 đã có chủ
(pin gieo: IGOR 0,898 · SAMAEL 0,93 · SAMAELE 0,97 · VIKTOR 1,00 · THỦ LÃNH 1,00@-7 · DORON 1,04
· JAKE 1,08 · JAY 1,16), nên KANG **buộc** phải dùng chung — và nó chọn bậc 1,00 của **VIKTOR**,
người không nói câu nào trong chương 071. Đúng việc bản vá được viết ra để làm.

**Nửa mù.** `holders` là `dict[float, str]` ghi bằng `setdefault`, nên một bậc chỉ nhớ **người
đầu tiên**. Sau khi KANG vào bậc 1,00, `holders[1.0]` vẫn khai `VIKTOR`. Đến lượt THẰNG ĐIÊN
(NPC sống đúng trong chương 071), nó đọc bậc ấy thành "người lạ đang giữ" → 0 chương chung →
chọn luôn. KANG, kẻ đang ở cùng chương với nó, **vô hình**. Nên bản vá tránh được va chạm **đầu
tiên** trên mỗi bậc rồi lại xếp người thứ ba vào đúng chỗ vừa bị chiếm — và làm thế một cách tự
tin, vì cái tên nó đọc được là một người lạ thật.
`patch_a_step_remembers_every_holder` (hàng chờ, thứ 2) cho một bậc nhớ **mọi** người giữ nó và
tính giá trên hợp của họ.

Và một phép đo của tôi sai, sửa ở đây: tôi viết rằng thang `Thanh Bình` **còn một bậc trống**
(0,87) nên có thể bản vá không được thử. Sai vì tôi tra thang bằng slug `preset_thanh_binh`,
trong khi tên trong catalog là `Thanh Bình` — slug rơi vào đường mặc định không kẹp, còn thang
thật kẹp 0,87 thành **0,898**, đúng bậc IGOR đang giữ. Thang đã kín thật. Bài học nhỏ: tra một
bảng bằng một cái khoá bịa ra thì nó trả lời, và câu trả lời ấy không phải về thứ mình hỏi.

## Chương 084 mất vì bộ đếm âm tiết của CHÍNH TÔI, bốn tiếng sau khi nó vào cây

Chương 084 đúc lại xong nhưng `failed`, nên `assemble_book` phải lùi nó về bản cũ của lô 3 — dàn
giọng của một phiên bản khác, đúng cái cảnh báo mà script ấy in ra. Lý do:

```
Chúng tôi đang đến Thành phố I-xờ-hờ-ta-ra (I-xờ-hờ-ta-ra Xi-ti).

đếm hiện tại   45 ký tự    9 âm tiết   ->  2,44 âm tiết/giây  -> DƯỚI sàn 3,75, gắn cờ
đếm tách gạch  45 ký tự   18 âm tiết   ->  4,88 âm tiết/giây  -> trên sàn, lẽ ra QUA
```

`patch_pace_counts_syllables_too` đếm âm tiết bằng `text.split()`. Cách đọc tiếng Anh trong dự
án này **luôn** viết bằng âm tiết nối gạch ngang (`Mai-cồ`, `A-ca-đe-mi`, `I-xờ-hờ-ta-ra`), nên
mỗi cái tên thành một âm tiết. Bản thu bị từ 11 lần và chương mất.

Trong docstring của bộ đếm ấy tôi viết rằng đếm thiếu âm tiết ở tên riêng là "chiều sai an
toàn", vì nó chỉ **giữ nguyên cờ** chứ không tha thêm. Câu ấy đúng mà thiếu, và chỗ thiếu là chỗ
đắt: an toàn trước việc **tha nhầm**, không an toàn trước việc **chặn nhầm** — và chặn nhầm thì
mất cả chương. Lần sau viết "sai số một chiều" thì phải nói rõ **an toàn cho ai**.

`patch_a_transliteration_is_many_syllables` (hàng chờ, thứ 3) tách âm tiết ở cả gạch ngang.
Cùng họ với `patch_pace_digits` và với chính bản vá nó đang sửa: đếm cái giọng đọc **phát ra**,
không đếm chữ viết.

## `boundary.sh` báo "đã ghép sách" cho một lượt thử

`assemble_book.py` mặc định **chỉ in rồi thoát 0**; phải có `--apply` mới chép. Bước 7 gọi nó
không cờ, nên log ghi "da ghep sach vao _book" trong khi cuốn sách vẫn 60 chương giữa lúc đã có
92. Một dòng log nói thành công cho một lượt thử tệ hơn không log dòng nào — nó làm người đọc
log thôi kiểm. Đã sửa thành `--apply`.

## Chuỗi cộng dồn bỏ quên project vá của các lô TRƯỚC (2026-09-11, 00:05)

`seed_chain.chain(batch)` lấy **project lô** của mọi lô trước cộng với project vá / đúc lại của
**riêng lô hiện tại**. Đo trên chuỗi của lô 4:

```
truoc:  lo01b · lo02 · lo03 · lo04
sau:    lo01b · lo02 · lo03 · lo03v_075 · lo03r_062 · lo03r_066 · lo03r_071 · lo03r_084 · lo03r_086 · lo04
```

Sáu project của lô 3 bị bỏ, nên sổ cộng dồn gieo cho lô 4 đếm sáu chương ấy theo bản **trước
khi đúc lại** — tức theo cách viết tên trước khi gộp (THU LÃNH chưa về THỦ LÃNH). Số chương thì
vẫn đủ, nhưng *thuộc về ai* thì sai, và sổ ấy chính là thứ quyết ai giữ giọng khi hai người
trùng. Không đếm đôi khi thêm chúng vào: `backfill_exposure` lấy chương theo **tiêu đề** và
project đứng sau thắng, nên một project đúc lại cùng chương chỉ **thay** bản cũ.

Bài kiểm cũ `test_a_batch_with_nothing_yet_has_no_seed` ghim đúng hành vi sai này — nó khẳng
định chuỗi của một lô chưa tồn tại là "các lô trước nó" và liệt kê chỉ project lô. Một bài kiểm
ghim hành vi sai thì không phát hiện được gì; đã sửa cùng lúc.

## `boundary.sh --recast` nhận thêm `auto` và `<lô>:<chương>`

Hai chỗ thiếu lộ ra khi chuẩn bị thả ranh giới lô 4:

- **`auto`**: danh sách chương cần đúc lại chỉ biết được **sau** khi lô chạy xong, nên không thể
  gõ tay lúc thả script. `auto` đọc từ chính `voice_pool_pressure` của lô vừa xong (dòng
  `CÙNG CHƯƠNG ...`), và nếu không tìm thấy gì thì **nói ra** rồi đi tiếp — im lặng ở đó sẽ đọc
  thành "không có va chạm nào".
- **`<lô>:<chương>`**: chương 084 đúc lại ở ranh giới lô 3 nhưng **thất bại**, nên cuốn sách đang
  phát bản cũ của lô 3. Cửa sổ duy nhất để chạy lại nó là một ranh giới, và ranh giới kế tiếp
  thuộc lô 4 — `--recast 3:084` chạy nó qua `launch_repair.sh 3`.

Đã thả: `bash scripts/boundary.sh 4 --recast auto 3:084`.

## Câu ngược chưa ai hỏi: một người HAI giọng — 21 chương, 202 câu, đã lên sách (2026-09-11, 00:20)

`voice_pool_pressure.py` hỏi *hai người có dùng chung một giọng không*. Câu ngược — **một người
có mang hai giọng không** — chưa công cụ nào hỏi, và nó là câu đắt hơn: hai người giống giọng thì
người nghe **lẫn** hai nhân vật; một người đổi giọng giữa chương thì người nghe **mất** nhân vật
ấy.

Đo lần đầu trên cuốn sách 90 chương đã ghép (`scripts/one_person_one_voice.py`):

```
21 chương có một người hai giọng NGAY TRONG cùng chương, 202 câu thoại
   NGƯỜI TRẢ LỜI   19 chương    doan_trang_f100 (69 chương cả sách)  vs  ngoc_linh_f108 (26)
   THỦ LÃNH         7 chương    thanh_binh_f100_p-07 (55)            vs  thanh_binh_f090_p-04 (20)
8 trên 49 người có tên mang nhiều hơn một giọng qua cả cuốn sách
```

Chương 060 là ca đọc rõ nhất: `THU LÃNH` nói 7 câu bằng `f090_p-04` và `THỦ LÃNH` nói 5 câu bằng
`f100_p-07` — **cùng một người, cùng một chương, hai giọng**.

**Vì sao mọi cổng đều xanh.** `verify_casting` kiểm *một người nói ra một giọng*, và dưới mắt nó
đây là **hai** người: hai dòng `characters` khác nhau, mỗi dòng một pin hợp lệ. Lớp tách danh
tính do rơi dấu không chỉ ăn chỗ trong kho giọng (điều tôi đã ghi hôm qua) — nó **đã đi vào
audio**, và đó là hậu quả tôi chưa đo. `patch_dropped_marks_are_the_same_name` chặn lớp ấy từ lô
4 trở đi; 21 chương đã đúc thì vẫn mang hai giọng cho tới khi được đọc lại.

**Và lô đúc lại tự sinh ra một dạng khác của cùng lỗi.** KANG mang `f093_p-04` ở sáu chương và
`f100_p-04` ở đúng chương 071 — vì lô đúc lại 071 bỏ pin của KANG (nó thua SAMAEL) rồi cấp giọng
mới. VIKTOR cũng thế (060 vs 062). Nghĩa là chữa một va chạm **trong** chương có thể tạo một
đổi giọng **giữa** các chương, và cái sau khó nghe ra hơn nhưng tệ hơn cho người theo dõi nhân
vật. Hướng sửa cho `port_casting`: khi phải bỏ pin của ai, ưu tiên giữ **giọng người ấy đang có ở
các chương khác** trừ khi chính giọng ấy là va chạm — chưa làm, cần đo trước.

**Việc phải làm:** đúc lại 21 chương ấy sau khi bản vá gộp tên đã áp:

```bash
bash scripts/launch_repair.sh <lô> --chapters $(python scripts/one_person_one_voice.py --chapters)
# 007 054 056 059 060 061 063 064 065 073 074 076 077 078 079 083 084 085 088 090 091
```

Chúng rải trên ba lô (007 thuộc lô 1; 054–065 lô 2 và 3; 073–091 lô 3), nên cần
`--recast <lô>:<chương>` của `boundary.sh` hoặc ba lượt `launch_repair.sh` riêng. Khoảng 2/3 khối
lượng một lô, vài giờ GPU. Đáng: đây là 202 câu mà người nghe nghe thấy, không phải một cờ trong
sổ.

## Sửa một lớp lỗi làm đổi hình dạng lớp ấy: `NGUOI_TRA_LOI` (2026-09-11, 09:05)

Trước 07:25 hôm nay, **không** project nào trong 100 project có một tên mang gạch dưới. Sau khi
ba bản vá của ranh giới lô 4 áp (trong đó có gộp rơi dấu), bốn project tạo sau đó có
`NGUOI_TRA_LOI` — 45 câu. Cơ chế: danh sách "đã biết" giờ đưa `NGƯỜI TRẢ LỜI` **đủ dấu** vào
prompt (đúng), và Ollama thỉnh thoảng trả về bản ASCII nối bằng gạch dưới. Trước đó nó trả về
`NGUOI TRA LOI` (khoảng trắng) và fold rơi dấu bắt được; gạch dưới thì `normalize_name` không
gộp, `_stripped_and_marks` thấy chữ trần khác nhau, và không pass nào bắt.

Hậu quả đã vào audio: chương 104 **đúc lại** — chính chương được đúc lại để xoá va chạm — có
người ấy nói 10 câu bằng `doan_trang_f115` (giọng mới) và 1 câu bằng giọng ghim `f100`.
`voice_pool_pressure` báo 0 vì nó hỏi câu ngược; `one_person_one_voice` sẽ báo sau khi
`name_marks` cũng biết gạch dưới.

`patch_an_underscore_is_a_space` (hàng chờ, áp ở bước 1 của ranh giới chạy lại): `identity_key`
= `normalize_name` sau khi thay `_` bằng khoảng trắng, dùng **chỉ** ở hai chỗ gom danh tính —
không đổi `normalize_name` chung vì `NPC_LOCAL::`/`ANONYMOUS_*` mang gạch dưới theo thiết kế.
78 bài xanh trên bản sao, kể cả bài giữ NPC không bị gộp.

Bài học đáng giữ: một bản vá đúng có thể **đổi phân bố lỗi** thay vì xoá lỗi. Đo lại lớp ấy
sau mỗi lô — `one_person_one_voice.py` là cái đo — chứ đừng coi "đã vá" là "đã hết".
Ba chương đã đúc với bản lệch (097, 104, và 007 đang dở) cần đúc lại lần nữa sau bản vá.

## `!` ép cả bước 3, nên 097 được làm hai lần (2026-09-11, 09:55)

`4:097!` được viết để ép **đúc lại** một chương đã hoàn thành. Nhưng `forced()` bỏ qua
`already_done` ở *mọi* bước gọi nó, kể cả bước 3 (vá chương hỏng): lô 4 vẫn ghi 097 `failed`, nên
bước 3 vá lại 097 thành `lo04v_097b` (09:25 → 09:47), rồi bước 4 đúc lại nó lần nữa thành
`lo04r_097` — hai mươi phút GPU cho cùng một chương, và hai project mới cùng ngày cho cùng một
tiêu đề. Sửa: bước 3 dùng phép kiểm không-ép (chương có bản hoàn thành thì thôi, bất kể `!`);
`!` chỉ có nghĩa ở bước 4/4b. Một dòng, nhưng `boundary.sh` đang chạy nên đợi điểm lặng.

Cái đúng trong cùng log: mỗi `=== chuong ===` giờ có dòng `project:` theo sau, và lần thứ hai
mang hậu tố `b` — hai lỗi sáng nay không tái diễn.

### Bằng chứng cho `patch_an_underscore_is_a_space` (09:58) — chương 097 vá lại

```
lo04v_097   (07:34, trước bản vá)   NGƯỜI TRẢ LỜI 23 câu @doan_trang_f100   NGUOI_TRA_LOI 11 câu @doan_trang_f115
lo04v_097b  (09:47, sau bản vá)     NGƯỜI TRẢ LỜI 37 câu @doan_trang_f100   (không còn dòng gạch dưới)
```

Cùng chương, cùng nguồn, cùng cách gieo; khác duy nhất là bản vá. Người ấy về **một** giọng, và
là giọng ghim (`f100`, giọng của 69 chương trước đó), không phải giọng mới `f115`. Đây là dạng
bằng chứng "cùng đầu vào, quyết định khác" mà tài liệu này đòi — không phải "chương xanh".

Và trên đường **đúc lại** (10:26), không chỉ đường vá: `lo04r_097` — NGƯỜI TRẢ LỜI 38 câu, một giọng
`f100`, 0 tên gạch dưới; `lo04r_104b` — 11 câu, một giọng `f100`, 0 tên gạch dưới (sáng nay 104
là 10 câu `f115` + 1 câu `f100`). Hai đường gieo, cùng kết quả.

### Đúc lại cho "một người hai giọng" — bằng chứng trên chương 060 (12:30)

Chương 060 là ca đọc rõ nhất hôm qua: THỦ LÃNH 7 câu `f090_p-04` + 5 câu `f100_p-07`, NGƯỜI TRẢ
LỜI 7 câu `ngoc_linh_f108` + 2 câu `doan_trang_f100`. Đúc lại sáng nay (gieo từ cuối chuỗi, sau
bản vá rơi dấu và gạch dưới):

```
lo03r_060   THỦ LÃNH        8 câu   thanh_binh_f100_p-07    (giọng của 55 chương — đúng bản trội)
            NGƯỜI TRẢ LỜI   5 câu   doan_trang_f100         (giọng của 69 chương — đúng bản trội)
            one_person_one_voice: "Không chương nào có một người hai giọng trong cùng chương."
```

Một giọng mỗi người, **và là giọng đa số của cả sách** — không phải giọng thiểu số như đã lo
trước khi kiểm `port_casting`. 061 cùng kết quả. Mười lăm chương còn lại đang đi cùng đường.

## Đặc tả bản vá: giữ cách đọc ghim khi chỉ neo tên phàn nàn (2026-09-11, 17:05 — chưa viết mã)

**Vì sao đường chấp nhận hiện có không cứu được.** `_grant_machine_acceptances` chạy ở cuối
chương, *sau* `_verify_chapter_audio` và các vòng sửa (ràng buộc số 2 của nó: "chỉ sau khi hết
ngân sách sửa"). Nhưng vòng sửa ASR, khi bản đọc-ghim trượt neo tên, đã sinh và đề cử bản
đọc-theo-chữ-viết **trước** khi tới lượt chấp nhận — lúc ấy đoạn không còn gì "outstanding".
Ràng buộc đúng cho trần khung và ASR-không-phán-xử-được lại thành **sai** cho neo tên: neo tên
không phải "vòng sửa còn cứu được", vì cứu bằng cách đổi cách đọc là đổi thứ người nghe nghe.
Đo: 348/348 bản đọc-ghim thua chỉ vì `ASR_LOCKED_NAME_ANCHOR_MISMATCH`.

**Bản vá (file khoá — `pipeline.py` + `database.py`), áp ở ranh giới lô 5 → 6:**

1. Trong vòng sửa ASR, khi ứng viên `locked_spoken_v1` có **cả hai** đường phiên hỏng và hợp mã
   lỗi ⊆ {`ASR_LOCKED_NAME_ANCHOR_MISMATCH`, `ASR_LOCKED_NAME_ANCHOR_REVIEW`}: **không** yêu cầu
   biến thể đọc-theo-chữ-viết; đề cử ứng viên đọc-ghim kèm phán quyết máy cho mã ấy.
2. Tầng database: một đường đề cử có bảo vệ, theo mẫu `_require_candidate_beats_a_cut_off_
   incumbent` — bốn điều kiện kiểm từ chính dữ liệu, không từ lời khai người gọi:
   (a) hai check ASR tồn tại và mã lỗi ⊆ họ neo tên; (b) `pronunciation_delivery_variant` =
   `locked_spoken_v1`; (c) `signal_json` không có `pace_outlier` và không chạm trần khung;
   (d) checksum WAV khớp file trên đĩa. Ghi vào `machine_audio_acceptances` với lý do nêu rõ
   "neo tên là bài chính tả; giữ cách đọc ghim để nhất quán toàn sách".
3. Đường ống chỉ *đề nghị*; database quyết. Không nới `dual_passed` ở chỗ nào khác.

**Lượt đề cử lại 348 đoạn đã lên sách (không cần GPU):** `scripts/keep_the_locked_reading.py
<project>` — với mỗi bản đọc-theo-chữ-viết đang được đề cử mà có anh em đọc-ghim đạt (a)–(d):
đề cử lại anh em ấy, rồi ghép lại chương. Chỗ khó, ghi trước để không giả vờ dễ:
`promote_segment_candidate` so checksum ứng viên với **mốc tín hiệu bền** của đoạn, mà mốc ấy
giờ thuộc về bản đọc-theo-chữ-viết; đường mới phải đặt lại mốc từ `signal_json` của ứng viên
đọc-ghim một cách có kiểm chứng (checksum file). Thử trên bản sao của project thật (084b) trước.

**Dự đoán ghi trước:** sau bản vá, tỉ lệ ứng viên đọc-theo-chữ-viết được đề cử trong lô 6 phải
từ ~48% về **~0** cho các ca chỉ-neo-tên; `python scripts/one_person_one_voice.py` không đổi
(đây là chuyện cách đọc, không phải giọng); và số neo tên `matched=False` không đổi — vì cổng
vẫn nói điều nó thấy, chỉ quyết định là khác.

Đọc thêm mã (16:45), sửa một chỗ trong đặc tả trên: "mốc tín hiệu bền" trong
`promote_segment_candidate` chỉ là `candidate.wav_sha256` so với checksum người gọi truyền vào —
không có bảng mốc riêng, nên (d) là đủ. Chốt chặn thật cho lượt đề cử lại là
`_require_candidate_incumbent_conn`: ứng viên nhớ **đương nhiệm nó đã đấu với** (`incumbent_
sha256`), và khi bản đọc-theo-chữ-viết được đề cử thì checksum của đoạn đổi — đúng lý do 307 bản
bị đánh dấu `invalid: incumbent checksum changed`. Vậy đường mới cần **điều kiện thứ năm**, kiểm
từ dữ liệu: đương nhiệm *hiện tại* của đoạn phải là anh em `source_spelling_v1` của chính ứng
viên ấy (cùng `segment_id`, cùng chuỗi sửa). Trạng thái vào: `dual_failed` hoặc `invalid` với lý
do ấy; ra: `promoted`. Không đường nào khác được đi qua đây.

**Trạng thái 18:45 — mã đã viết, thử trên bản sao project thật, xếp hàng cho ranh giới 5 → 6.**
`scripts/pending_patches/patch_keep_the_locked_reading.py` (kèm `tests/test_keep_the_locked_
reading.py` chép `lo03r_084b` vào thư mục tạm), `scripts/keep_the_locked_reading.py` (lượt đề
cử lại, không GPU), bước 6b của `boundary.sh`. Kết quả trên bản sao 084b: 10/10 đoạn giữ cách
đọc ghim, chương ghép lại trong 38 giây, `cli validate` qua hết. Ba điều khác đặc tả, đều do bài
thử trên dữ liệu thật bắt được, ghi ở `KEEP_THE_LOCKED_READING.md`: CAS cuối phải so với đương
nhiệm *hiện tại* và tự hạ anh em đọc-theo-chữ-viết; CAS trạng thái ứng viên so với hằng số
`dual_passed` làm đường "bản hoàn chỉnh thắng bản bị cắt" (có sẵn, chưa từng chạy thật — 0 dòng
`machine_take_substitutions` trên 47 project) không bao giờ đi qua được; và lượt đề cử lại không
chạy lại cả `_process_chapter` (một chương xong vẫn có đoạn `failed` được máy cấp phép, và bước
tổng hợp sẽ gọi Whisper cho nó) mà gọi `_publish_verified_chapter` — đuôi của `_process_chapter`
tách thành hàm, hai người gọi chung một thân. Lượt thử chỉ-đọc trên cả sách (18:55): **452 đoạn
trong 102 chương** sẽ được chữa; 411 đoạn vẫn phát bản gốc được để yên (không có bằng chứng xếp
hạng bản gốc với bản rõ tiếng); 33 chương đã bị bản đúc lại thay được bỏ qua — không lọc thì
chương cũ ghép lại sẽ đoạt lại chỗ trong sách vì `assemble_book` chọn `completed_at` mới nhất.

## Bản vá: một con số được đọc trọn vẹn, kể cả từ 1000 (2026-09-11, 19:05 — xếp hàng 5 → 6)

`scripts/pending_patches/patch_a_number_is_read_in_full.py`, sau `patch_keep_the_locked_reading`
trong `ORDER`. Chương 106 của lô 4 chết vì **một** đoạn, 10/10 lần thử:

    Tôi bắt đầu thử những mật khẩu dễ đoán nhất như, "password", "123456", thậm chí là "qwerty1234".

    thước chữ      70 ký tự đọc được ở 12,35 kt/s  → dưới sàn 12,5 đúng 0,15
    thước âm tiết  17 âm tiết         ở ~3,0 at/s   → dưới sàn 3,75

Cả hai thước cùng sai một kiểu: `123456` đếm là sáu ký tự và **một** âm tiết, trong khi giọng
đọc phát ra ít nhất "một hai ba bốn năm sáu". `spoken_speakable_chars` đã nở số ra chữ từ
alpha.57, nhưng `vietnamese_number_words` chỉ tới 999 và docstring gọi phần còn lại là "cố ý
không lấp bằng phỏng đoán". Đúng ở chỗ không bịa hệ số; sai ở chỗ có một cách đếm không phải
phỏng đoán: (1) đọc trọn vẹn tới dưới 10^12 theo **ngữ pháp số đếm** — nhóm ba chữ số, "không
trăm" / "lẻ" cho nhóm giữa: 2.024 là "hai nghìn không trăm hai mươi tư"; (2) cho phép đo nhịp,
một dãy từ 1000 lấy **cận dưới** của hai cách đọc có thể (như một số, hay từng chữ số) theo âm
tiết — "123456" trong mật khẩu và "2024" trong một năm không đọc giống nhau, chưa đo VieNeu chọn
cách nào, và lấy cách ngắn hơn thì đếm thiếu chỉ giữ cờ, đếm thừa mới tha nhầm; (3)
`spoken_syllables` đếm trên cùng văn bản đã nở số, nên "22" là ba âm tiết. ASR **không đổi**:
`_fold_number_digits` vẫn dừng ở `NUMBER_FOLD_CEILING = 999`, năm tháng trong bản ghi giữ nguyên.

Đoạn của 106 sau bản vá, cùng thời lượng ~5,67 giây: 88 ký tự (15,5 kt/s), 26 âm tiết (4,6 at/s)
— giữa dải. Bài thử: `tests/test_a_number_is_read_in_full.py` (ngữ pháp tới tỷ; cận dưới; đoạn
106; bản chậm thật vẫn bị bắt; ASR giữ nguyên); bài cũ ghim "đếm thiếu chữ số có chủ ý" được
đổi tên và đổi số. 187 bài liên quan xanh trên cây tạm có cả hai bản vá.

**Đo trước khi tin, trên dữ liệu thật (01:30 ngày 2026-09-12).** Nở chữ số làm số ký tự TĂNG, và
cận trên của thước nhịp (24,5 kt/s cho `normal`) **không** xét âm tiết - nên bản vá này mở ra một
cách trượt mới: một đoạn dày chữ số đọc nhanh có thể vượt trần. Đo bằng chính
`chars_per_second` đã lưu (suy ra `speech_seconds = ký_tự_cũ / cps`, đúng công thức
`validate_audio_array` dùng) trên mọi đoạn có chữ số của các project lô, với dải nhịp đọc từ
settings của từng project:

    321 đoạn có chữ số và có tín hiệu đã lưu
    217 trong đó đổi số đếm sau bản vá
      0 bị gắn cờ MỚI   ·   0 được tha thêm
    2,1 kt/s là biên lùi xa trần nhỏ nhất (22,4 so với trần 24,5, `normal`)

Không có hồi quy trên dữ liệu đã có. Nhưng 2,1 kt/s là biên mỏng, nên **việc cần theo**: nếu một
lô về sau mất chương vì `pace` ở một câu dày chữ số, đọc lại con số này trước khi nghi bản vá nào
khác — cách chữa lúc ấy là cho cận trên xét cả âm tiết như cận dưới đã làm, không phải nới trần.

**Dự đoán ghi trước:** ranh giới 5 → 6 với `--recast auto 4:106` đúc lại 106 và đoạn ấy qua ở lần
đầu (không còn `SEGMENT_FAILED` vì nhịp); lô 6 không mất chương nào vì số ≥ 1000 (năm tháng, số
tiền). Nếu một chương vẫn mất vì nhịp ở câu có số dài, nhìn `_digit_run_spoken`: cận dưới có thể
vẫn thấp hơn cách VieNeu đọc thật — lúc ấy đo bằng `try_a_pronunciation.py` với "123456" và
"2024" rồi thay cận dưới bằng cách đọc đo được.

## Một người một giọng QUA CÁC CHƯƠNG: chế độ `--across` cho ranh giới (2026-09-11, 23:35 — chưa làm)

`one_person_one_voice.py` đã có phần "qua các chương" nhưng chỉ in; `boundary.sh --recast auto`
chỉ hỏi `voice_pool_pressure` (hai người chung giọng **trong cùng chương**). Câu ngược lại — một
người mang hai giọng ở hai chương — phải tự tay đọc rồi gõ `B:NNN`, như đã làm cho chín chương
của NGƯỜI TRẢ LỞI / THỦ LÃNH đêm 2026-09-11.

**Đã làm phần script (23:40):** `one_person_one_voice.py --across --min-chapters N` in ra danh sách
`B:NNN` của những chương mang giọng **thiểu số** của một người có ≥ N chương (mặc định N = 5, để
không đúc lại vì một cái tên hai chương), tra lô của chương từ manifest; hoà thì giọng đứng trước
theo bảng chữ là đa số, cho hai lần chạy cùng câu trả lời. Trên sách 116 chương nó đề nghị 16
chương; ranh giới 5 → 6 nhận 11 (bỏ 5 chương KANG — xem dưới). **Còn phải làm:** `boundary.sh
--recast auto` gộp thêm danh sách ấy — sửa ở điểm yên tĩnh kế, vì script đang chạy.

**Sửa ở đâu và sửa gì, viết sẵn để sau chỉ việc dán** (01:55 ngày 2026-09-12). Khối `auto` hiện
tại chỉ hỏi `voice_pool_pressure` (va chạm **cùng chương**) và chỉ thêm vào `$RECAST`, tức chỉ
chương của lô này. Hai công cụ mới in `B:NNN` cho **lô khác**, nên chúng phải đi vào
`$RECAST_OTHER`. Chèn ngay sau khối `if [ -n "$FOUND" ] ... fi`, trước dòng bỏ trùng lặp:

```bash
  # Hai cau nguoc lai, cho LO KHAC: mot nguoi hai giong qua cac chuong, va giong sai phai/tuoi.
  # Ca hai in dang `B:NNN` va di vao RECAST_OTHER; chuong cua chinh lo nay thi ve RECAST, dung
  # luat nhu tham so dong lenh. Chuong da co ban duc lai hoan thanh se bi `already_done` bo qua
  # (khong co `!`), nen dan them la an toan.
  for TOKEN in $(py scripts/one_person_one_voice.py --across 2>/dev/null)                $(py scripts/voice_matches_the_person.py --recast 2>/dev/null); do
    case "$TOKEN" in
      [0-9]*:[0-9][0-9][0-9])
        if [ "${TOKEN%%:*}" = "$BATCH" ]; then RECAST="$RECAST ${TOKEN#*:}"
        else RECAST_OTHER="$RECAST_OTHER $TOKEN"; fi ;;
    esac
  done
  RECAST_OTHER="$(printf '%s
' $RECAST_OTHER | sort -u | tr '
' ' ')"
  say "auto: qua cac chuong + sai phai/tuoi:$RECAST_OTHER"
```

**Một cái bẫy phải nhớ khi dán:** `voice_matches_the_person --recast` in chương của người bị sai
phái, mà sửa được nó **đòi ghim tuổi trước** (`patch_a_pinned_person_outranks_a_ported_voice`,
chưa áp). Dán khối này trước khi bản vá ấy vào cây thì ranh giới sẽ đúc lại `3:062` mỗi lần và
port vẫn mang giọng cũ sang — tốn GPU, không sửa được gì. Thứ tự đúng: áp bản vá ghim tuổi ở ranh
giới 6 → 7, chạy `cast --age` cho IVAN, **rồi** mới dán khối này. Luật chọn phía nào đúc lại: phía **ít chương hơn** đúc lại theo phía nhiều hơn, trừ khi
phía nhiều hơn là giọng cũ của một lớp lỗi đã biết (như `NGUOI TRA LOI`) — khi ấy chính bản gộp
tên mới là phía đúng. Ghi cả hai con số vào log để người sau kiểm.

**Còn mở, có bằng chứng:** KANG f100 (8 chương: 065, 071, 092, 096, 107, 109, …) vs f093 (5: 066,
067, 087, 090, 091); hai lần đúc lại 090/091 mang f093 và lô 5 gieo từ 091. Đo lại sau lô 5.
Mười tên 1–3 chương (THALIA 3 giọng, SAMAELE 3, WILLEM, IVAN, ROB, NOAH, CHA, VIKTOR, ĐẠI TƯ TẾ):
mỗi tên một quyết định nhỏ, tổng ~12 chương-GPU. Sổ `character_exposure` của lô 5 là bản cũ 21
tên (sửa đường ghi sổ sau khi lô 5 đã khởi động) — hạng "ai giữ giọng khi trùng" trong lô 5 lệch;
lô 6 sẽ có sổ đúng vì launcher ghi vào phần tử cuối chuỗi.

## Hai chỗ hở cùng hình dạng, ghi để sửa ở điểm yên tĩnh (2026-09-12, 01:00)

**1. `_promote_a_finished_take_over_a_cut_off_one` không được bọc.** Nó gọi
`_segment_candidate_item` như `_keep_the_locked_reading` từng gọi, và hàm ấy ném khi checksum văn
bản đọc trôi; một ngoại lệ ở đấy giết chương đang phiên. Đường này chưa từng chạy thật (0 dòng
`machine_take_substitutions` trên 47 project lô, đo 17:59 ngày 2026-09-11 — và CAS trạng thái ứng
viên là lý do nó không chạy được, đã sửa trong `patch_keep_the_locked_reading`). Sau ranh giới
5 → 6 nó sẽ chạy được lần đầu; bọc nó bằng cùng lớp bọc "mọi lỗi là thôi không thay" trước khi lô
nào đụng phải một bản thu bị cắt.

**2. Bước 2 của `boundary.sh` dùng `git add -A "$ROOT"`.** Đã một lần cuốn công việc đang dở của
tôi vào commit của ranh giới (7e5e4bd). Luật hiện tại là "giữ cây sạch khi ranh giới bay" — một
luật dựa vào kỷ luật của người, đúng kiểu luật sẽ hỏng lúc 4 giờ sáng. Sửa đúng:
`apply_all --apply` in ra danh sách file nó đã ghi (nó biết chính xác: `ebook_reader/*`, `tests/*`,
`scripts/pending_patches/apply_all.py`), và bước 2 stage đúng danh sách ấy. Không sửa được lúc
này vì `boundary.sh` đang chạy (bash đọc script theo từng khúc).

## Đặc tả: ghim TUỔI như đang ghim phái, và một thuộc tính đã ghim phải thắng giọng ported (2026-09-12, 01:20)

Bằng chứng, đo bằng `scripts/voice_matches_the_person.py` trên sách 116 chương (451 dòng chương ×
nhân vật × giọng, 61 tên):

    lệch phái, đếm thô                    11 dòng / 5 tên
    trừ luật giọng trẻ con                 1 dòng / 1 tên  <- con số thật
    người đổi tuổi giữa các lô             5 tên, 3 trong đó đổi cả giọng

Con số thật là **IVAN**: `male`, `age=unknown`, 17 câu ở chương 062 đọc bằng `ngoc_linh_f107_p+02`
— preset **nữ** kéo cao, thứ dự án dành cho trẻ con (`AGE_TARGET_PITCH_HZ`: preset nam dừng cách
ống âm một đứa trẻ 0,8 cm). Đường đi của lỗi:

    lô 3, chương 072   `characters.age = child`   (mọi `segments.age` của anh ta: `unknown`)
    lô 3, chương 062   `age = unknown`, giọng đã ghim là giọng trẻ con -> 17 câu giọng nữ
    lô 3, chương 060   `age = unknown`, 3 câu, `thai_son_f100_p+00` — giọng nam, đúng
    lô 4               `age = unknown`, `locked_voice_key = ngoc_linh_f107_p+02` — port mang theo

Thoại: *"T-Tôi tên là Ivan,"*, *"cậu đã m-mượn một ít t-tiền của bọn tôi…"*, *"Khỏe không, người
anh em?"* — một thanh niên hay lắp, không phải một đứa trẻ. Một lần phân loại sai đã theo anh ta
sang mọi lô sau, vì `port_casting` mang `locked_voice_key` đi cùng danh tính. Đúng cơ chế giữ nhất
quán; nó giữ nguyên cả cái sai.

**Chưa có cách sửa.** `cli cast --character X --gender male|female` ghim được phái — docstring của
nó nói đúng lý do tồn tại: *"một lỗi mô hình mà người nghe trả lời trong một giây lại tốn một giờ
máy"*. Tuổi thì không ghim được, mà tuổi mới chọn **họ giọng**, nên lỗ này đắt hơn lỗ mà `cast`
được viết ra để bịt.

**Bản vá đề xuất (file khoá: `cli.py`, `database.py`, `character_registry.py`), áp ở ranh giới 6 → 7:**

1. `cli cast --character X --age adult|teen|child|young|unknown` ghim tuổi, cùng bảng và cùng cách
   với phái đã ghim (`lock_character_gender` → thêm `lock_character_age`). Đọc được trước khi
   casting chạy, như `cast --gender`.
2. `build_registry_and_cast` đọc tuổi đã ghim **trước** tuổi phân tích, y như nó làm với phái.
3. **Thuộc tính đã ghim thắng giọng ported.** Khi tuổi (hoặc phái) đã ghim không còn khớp họ giọng
   của `locked_voice_key` mà `port_casting` mang sang, bỏ giọng ấy và cấp lại — có ghi một dòng
   `runtime_events` nói rõ vì sao, vì đây là chỗ duy nhất "nhất quán" phải nhường "đúng". Không có
   điều 3 thì điều 1 và 2 vô dụng cho mọi lô sau: port vẫn mang giọng cũ.
4. Chỉ SAU ĐÓ mới đúc lại: `python scripts/voice_matches_the_person.py --recast` (hiện in `3:062`).
   Đúc lại trước khi ghim chỉ tốn GPU — công cụ đã in đúng câu cảnh báo ấy.

**Hai sự thật đọc thêm lúc 01:15 ngày 2026-09-12, đổi thiết kế bản vá — ghi ra vì chúng là chỗ
một bản vá "hiển nhiên" sẽ hỏng:**

- **Cột `locked` là của PHÁI.** `locked_character_genders()` lọc `WHERE locked=1 AND gender IN
  ('male','female')`. Nếu việc ghim tuổi cũng đặt `locked=1` thì mọi nhân vật được ghim tuổi bỗng
  có phái "do người quyết", kể cả khi chưa ai nói gì về phái — và `_validate_casting_inputs` sẽ
  thôi báo mâu thuẫn phái cho họ. Vậy tuổi phải có **cột riêng** (`locked_age TEXT NOT NULL
  DEFAULT ''`), đúng khuôn `locked_voice_key` đã thêm bằng `ALTER TABLE` ở `database.py:2335`.
- **Phái đã ghim cũng KHÔNG đi sang lô sau.** `port_casting` mang nhân vật đã biết bằng
  `upsert_character(...)` và docstring nói rõ "Deliberately NOT locked", còn `read_known_characters`
  chỉ đọc `canonical_name, display_name, gender, age, personality`. Nên lời hứa của `cast`
  ("người quyết, và outrank mô hình **vĩnh viễn**") hiện chỉ đúng trong MỘT project: lô sau phân
  tích lại và có thể đổi ý. Bản vá phải mang cả hai thuộc tính đã ghim đi theo chuỗi gieo, như
  `port_pronunciations` mang cách đọc.

**Chỗ đặt luật "đã ghim thắng ported":** `build_registry_and_cast` (`character_registry.py:1413`),
nơi đã đọc cả `locked_character_genders()` lẫn `locked_character_voices()`. Nếu tuổi/phái đã ghim
không khớp họ giọng của `locked_voice_key` (tra bằng `voice_catalog`: preset nữ kéo cao = họ trẻ
con; preset nam = người lớn nam), bỏ pin ấy cho nhân vật đó, ghi một dòng `runtime_events`, để
allocator cấp lại. Không đặt ở `port_casting`: project đích lúc ấy chưa có thuộc tính nào được
ghim, nên nó không có gì để so.

**Trạng thái 01:45 — mã đã viết, 10 bài thử xanh, CỐ Ý chưa xếp hàng.**
`scripts/pending_patches/patch_a_pinned_person_outranks_a_ported_voice.py`. Nó không vào `ORDER`
đêm nay: ba bản vá kia đã chứng minh trên dữ liệu thật, còn đây là thay đổi ở tầng **casting** -
tầng đắt nhất của dự án, nơi một lỗi không hỏng một đoạn mà hỏng dàn giọng của cả lô. Xếp ở ranh
giới 6 → 7, sau khi lô 6 cho thấy ba bản vá kia chạy đúng. Bốn việc nó làm: cột `locked_age` (+
migration cho project cũ), `lock_character_age` / `locked_character_ages`, `cast --age` (và
`--gender` thành không bắt buộc, cần ít nhất một trong hai), `port_casting` mang cả hai thuộc
tính đã ghim theo chuỗi gieo, và `_drop_pins_that_contradict_a_person` ở
`build_registry_and_cast`. Bài thử ghim chặt hai điều dễ trôi: `LOCKABLE_AGES ⊆ ALLOWED_AGES` (hai
module, hai danh sách), và **ghim tuổi KHÔNG được ghim phái** (cột `locked` là của phái).

*(Sửa 10:50 ngày 12-09: không cần `cast --age` — luật bỏ pin của bản vá áp cho mọi tuổi khác `child`,
kể cả `unknown`, và pin của IVAN ở 062 là `ngoc_linh_f107_p+02` mang sang; xem WORK_LOG 10:45.)*

**Dự đoán ghi trước:** sau bản vá và một lần `cast --character IVAN --age adult`, đúc lại 062 cho
IVAN giọng nam; `voice_matches_the_person.py` về 0 dòng lệch phái; `one_person_one_voice --across`
mất IVAN khỏi danh sách (3 chương của anh ta về một giọng). EVERAN **không** đổi: nó là trẻ con
thật, và luật giọng trẻ con đúng.

## Câu hỏi thứ năm: hai người chung một giọng QUA CẢ SÁCH (2026-09-12, 02:50 — đo rồi, chưa thành công cụ)

Bốn câu đã có công cụ: hai người chung giọng **trong một chương** (`voice_pool_pressure`), một
người hai giọng **trong một chương** và **qua các chương** (`one_person_one_voice`, `--across`),
giọng có đúng phái/tuổi (`voice_matches_the_person`). Câu thứ năm chưa có: hai người chung một
giọng **qua cả sách**.

Đo tay trên 118 chương: **92 cặp** dùng chung giọng, **1 cặp cùng chương** (SỐ BỐN + SỐ NĂM,
chương 023 — đã thêm `1:023` vào ranh giới), **2 cặp** mà cả hai đều ≥5 chương với giọng ấy
(SAMAEL+KANG trên f093, KANG+BOWDEN trên f100).

**KHÔNG làm thành công cụ, và lý do — câu này đã có câu trả lời từ lô 1.** Tôi đo lại kho giọng
lúc 03:40 ngày 2026-09-12 và tưởng mình tìm ra gốc rễ: 39 nhân vật trên **14 slot nam** (2 preset
× 7 bậc), 22 trên 27 slot nữ; bốn preset nam không gánh ai (hai giọng tin tức, một miền Trung, một
bị loại). Nhưng `TWO_CHARACTERS_ONE_VOICE.md` đã đi đúng con đường ấy ở lô 1, **và đã tự bác kết
luận "kho giọng nam đã đầy"**: ràng buộc thật không phải tổng nhân vật trên tổng kho, mà là
**số người nam nói trong CHƯƠNG đông nhất**, vì người nghe nghe từng chương một.

Đo lại con số ấy ở quy mô sách (118 chương) — nó vẫn là con số quyết định, và nó vẫn thoải mái:

    nam:  chương đông nhất 7 người (chương 023)  | kho 14 slot  -> còn chỗ
    nữ :  chương đông nhất 5 người (065, 078)    | kho 27 slot  -> còn chỗ

Và ba lần loại preset đều có lý do, hai trong ba là **tính đúng đắn chứ không phải thị hiếu**:
giọng miền Trung đọc sai thanh điệu trên từ thường ("khốn kiếp" → "khôn kiêp", mà thanh điệu mang
nghĩa), giọng tin tức sai văn phong, và Xuân Vĩnh bị một người nghe Việt phán. Nên **đừng mở rộng
pool để chữa việc dùng chung qua sách**: nó không phải thứ cần chữa, và hai trong ba cửa mở ra đều
dẫn tới lỗi phát âm.

Cái còn lại đáng theo: 7 người trên một bậc `f100_p-04` là con số cao, và nếu có ngày một chương
có hơn 14 người nam nói thì lúc ấy pool mới thật sự bó. Theo bằng `voice_pool_pressure` (nó hỏi
đúng câu cùng-chương) chứ không cần công cụ mới.

**Cái bẫy của phép đo, ghi để người sau không đạp lại:** phải giao hai tập *"chương mà người ấy
dùng CHÍNH GIỌNG ẤY"*, không phải *"chương mà người ấy có mặt"*. Bản đầu của tôi giao sai và báo
NGƯỜI TRẢ LỜI + THALIA cùng chương ở sáu chương, trong khi họ chỉ chung giọng `f115` ở hai chương
khác nhau. Cùng lớp lỗi với `one_person_one_voice` trước khi gộp tên: chọn đúng hai tập để giao
mới là câu hỏi.

## Xếp hạng pin theo mức đã nghe: 8 slot nam đang do người 1–2 chương giữ (2026-09-12, 04:20)

Đo trên lô 5 sau khi nó khoá dàn giọng. Kho giọng dùng được cho nhân vật **nam** là 14 slot
(2 preset × 7 bậc; xem `TWO_CHARACTERS_ONE_VOICE.md` về vì sao chỉ hai preset và vì sao không mở
rộng). Tình trạng sở hữu:

    pin trên preset nam: 16 (hai slot mang hai pitch khác nhau nên 16 > 14)
    trống: 0

    người giữ pin, xếp theo số chương:
      THỦ LÃNH 90 · MICHAEL 42 · SAMAEL 29 · JAKE 9 · BOWDEN 6 · WILLEM 6 · CÔNG TƯỚC 3 · RAY 3
      ARTHUR 2 · JAY 2 · SAM 2 · ĐẠI TƯ TẾ 2 · DORON STORMWATCH 1 · IGOR 1 · REICHARDT 1 · VALE 1

    người ≥3 chương KHÔNG có pin:
      KANG 13 · SAMAELE 3 · IVAN 3 · ROB 3 · LYLE 3

**Tám slot đang do người 1–2 chương giữ, còn KANG với 13 chương thì không có gì.** Đó là thứ tự
ngược, và nó là gốc của cả họ lỗi "một người hai giọng qua các chương": người không có pin bị rút
thăm lại giọng ở **mọi** lô sau, còn người có pin thì giữ mãi dù chỉ nói ba câu trong một chương
cách đây một trăm chương.

`port_casting` **đã** có đúng học thuyết này — luật va chạm xếp hạng theo sổ cộng dồn rồi số câu —
nhưng nó chỉ áp khi hai người **cùng đòi một slot lúc chuyển lô**, không bao giờ áp cho việc sở
hữu đang đứng. Một người giữ pin mà im lặng thì không va chạm với ai, nên không bao giờ bị xét
lại.

**Đề xuất, và cái giá của nó:** một bước "xếp lại pin" ở ranh giới, đọc sổ cộng dồn đủ 62 tên,
và chuyển pin từ người ít chương sang người nhiều chương khi slot khan. Giá: mỗi lần chuyển pin
đòi **đúc lại những chương của người mất pin** (1–2 chương mỗi người, ~25 phút GPU một chương),
vì giọng của họ đổi. Với tám slot đang bị giữ bởi người 1–2 chương, đổi năm slot cho năm người
≥3 chương tốn khoảng 6–8 chương đúc lại (~3 giờ GPU) và cho KANG, LYLE, ROB, IVAN, SAMAELE một
giọng ổn định vĩnh viễn.

**Chưa làm, và lý do:** đây là thay đổi ở tầng casting kèm chi phí GPU thật và một quyết định
đánh đổi (đổi giọng của bốn nhân vật một chương để bốn nhân vật ba-mười-ba chương được ổn định).
Việc ấy thuộc chủ sách. Số liệu đã đủ để quyết trong một phút.

Công cụ đã có để dùng khi quyết: `scripts/pin_the_book_cast.py` (ghim theo giọng đa số của cả
sách, tôn trọng pin đã có — hôm nay ghim được 0 người, đúng vì kho nam đã kín).

## Hai bản sửa cho cổng nhịp, từ ca chương 140 (2026-09-12, 06:05 — đo rồi, chưa vá)

Ca đầy đủ ở `docs/A_BAND_IN_THE_VALLEY.md`. Tóm: một đoạn 24 ký tự của lô 5 thử 10 lần, ra đúng
**4 giá trị lặp lại** (24,79 · 27,03 · 29,70 · 12,45 kt/s) nằm **hai bên** dải [12,5 .. 24,5],
không giá trị nào bên trong; hai lần gần nhất trượt 1,2% và 0,4%.

**1. `pace_retry_reachability.py` báo "trong tầm với" cho một ca không tới được.** Nó ước lượng
38,9% mỗi lần thử và 99% cho 10 lần; thực tế 0/10. Nguyên nhân: nó khớp một phân bố **liên tục,
một đỉnh** vào các giá trị quan sát, còn dữ liệu là hai cực. Sửa: in thêm **số giá trị PHÂN BIỆT**
và **khoảng trống lớn nhất** giữa chúng, rồi gọi một ca là "không tới được" khi cả dải nằm trong
một khoảng trống. Không cần giả định phân bố, và câu "10 lần, 4 giá trị, khoảng trống 0,96 s chứa
cả dải" là câu người đọc tin được.

**2. Đường tempo không với tới chỗ cần.** `POSTPROCESS_PROFILE_TEMPO` (atempo 0,94, không đổi cao
độ) biến đúng lần thử gần trần nhất — 24,79 → **23,30 kt/s, QUA** — và lần ấy xuất hiện 4/10 lượt.
Nhưng ứng viên tempo chỉ nằm trong thang sửa của **ASR** (`repair_round == max`), còn đoạn này chết
ở vòng thử lại **TTS** nên không bao giờ tới. Sửa: khi vòng TTS cạn lượt vì **pace** (không phải
vì cờ chặn nào khác) và bản thu gần nhất chỉ trượt **cận trên**, áp tempo 0,94 lên chính bản ấy
rồi cho nó đi qua cổng nhịp một lần nữa. Chỉ một chiều (làm chậm), chỉ cho cận trên, và chỉ khi
`split` đã từ chối — ba điều kiện kiểm được từ dữ liệu.

**CẬP NHẬT 06:55 — dự đoán của tôi sai, và mục này hạ cấp.** Bước 3 vá chương 140 xong trong 26
phút và đoạn ấy **qua ngay lần thử đầu**: 1,68 s, 21,28 kt/s. Thứ đổi là **phiếu diễn** —
`intensity` từ 1 xuống 0 sau khi lượt vá phân tích lại chương — không phải hạt giống. Nên:

- **Bản sửa (2) đường tempo: hạ xuống "theo dõi".** Chưa có ca nào chứng minh retry không tới
  được; ca duy nhất tưởng là nó thì đã tự khỏi bằng đường có sẵn (phân tích lại ở bước 3). Điều
  kiện để áp: một đoạn trượt nhịp qua **ít nhất hai lượt vá** với hai phiếu diễn khác nhau.
- **Bản sửa (1) — ĐÃ LÀM 13:05 ngày 12-09** (`_shape`: cột "giá trị" phân biệt và "trống" rộng nhất, dấu `*` khi cả dải nằm trong một khoảng trống, và ghi chú rằng đó là câu hỏi của một lượt; test với đúng dữ liệu 140). Lý do gốc vẫn đúng: nó nên tách **"phương sai trong
  một lượt"** (mười lần thử cho bốn giá trị, cách nhau 80 ms — đo được và vẫn đúng) khỏi **"cơ hội
  qua sau khi phân tích lại"** (thứ thật sự quyết định có nên vá lại chương). Con số 38,9% của nó
  hoá ra lạc quan mà ĐÚNG cho câu thứ hai.

Chi tiết và phần tự bác bỏ ở `docs/A_BAND_IN_THE_VALLEY.md`.

## Cùng tổ hợp cờ ấy còn nằm ở `background_runner._detached_creation_flags` (2026-09-12)

`CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` — y hệt cờ watchdog vừa sửa
(xem `SURVIVING_AN_INTERRUPTION.md`, mục 23:14). Hôm nay **vô hại** vì supervisor là
`pythonw.exe` (GUI subsystem, không bao giờ có console) và mọi con của nó đều `pythonw` hoặc
gọi qua `CREATE_NO_WINDOW`. Nhưng nếu một ngày `pythonw.exe` không có trong venv,
`_default_python_executable` rơi về `python.exe`, và khi ấy worker `multiprocessing` sẽ mở
một cửa sổ console **sống suốt lượt chạy**. Sửa đúng là bỏ `DETACHED_PROCESS` như watchdog;
file này bị khoá nên đi qua `pending_patches`. **Bản vá đã viết 13:15 ngày 12-09:**
`patch_a_supervisor_with_a_console_of_its_own.py`, áp thử sạch trên bản sao, test của nó + `test_background_runner`
xanh. CHƯA xếp hàng — xếp ở ranh giới 7 → 8 hoặc sau, cùng lúc với bản vá khác cho đỡ một lượt test. Không gấp.

## `boundary.sh` bước 1 ghi "bo test: (khong thay dong tong ket)" dù test xanh (2026-09-12)

Ranh giới 5→6 lúc 06:20:04 ghi dòng ấy vào log và vào commit `054a0d1`, trong khi `apply_all`
in rõ *"Xanh hết. Giờ mới được chạy lượt mới."* Nguyên nhân: ranh giới tìm chuỗi tổng kết tiếng
Anh của pytest (`N passed`) trong output, còn `apply_all` chạy pytest với `-q` và chỉ in phán
quyết tiếng Việt của chính nó. Không nguy hiểm — nếu test đỏ, `apply_all` trả mã khác 0 và ranh
giới dừng ở đó — nhưng commit tự động mất con số. Sửa: bắt cả `Xanh hết` (và `TEST ĐỎ`) làm
dòng tổng kết. **Chỉ sửa khi không có ranh giới nào đang chạy**: bash đọc script theo từng đoạn,
sửa file đang chạy là hỏng nó.

## Hàng cho ranh giới 7 → 8 (2026-09-12, 15:45) — hai bản vá đã viết, đã áp thử, CHƯA xếp

1. `patch_a_supervisor_with_a_console_of_its_own.py` — bỏ `DETACHED_PROCESS` ở supervisor (bẫy tiềm ẩn).
2. `patch_a_tie_goes_to_the_emptier_step.py` — hoà về chương chung thì chọn bậc ít người giữ hơn
   (lô 6: sáu người chồng một bậc). Cả hai nhỏ, tất định, có test; xếp cùng lúc cho đỡ một lượt test.
3. `patch_two_children_in_one_chapter_get_two_voices.py` — hai đứa trẻ cùng chương phải là hai giọng (lô 7, chương 186).

**22:50: cả ba đã xếp vào ORDER** (ranh giới 7 → 8 đang chờ lô 7).
