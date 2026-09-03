# Throughput: tại sao máy đang rảnh và làm gì với nó

## Nút thắt đổi theo giai đoạn - đừng đọc một con số rồi kết luận

Đo lần đầu chỉ bắt giai đoạn `chapter_synthesis` và kết luận "không gì bão hoà". Đo lại trong
giai đoạn `analysis` cho ra hình dạng **khác hẳn**:

| Tài nguyên | Analysis (Ollama qwen3:8b) | Synthesis (VieNeu) | Tổng |
|---|---|---|---|
| GPU compute | 30-48% | 14-18% | 100% |
| **VRAM** | **6,66 GB (82%)** | 1,30 GB (16%) | 8,15 GB |
| CPU | 42% ≈ 13 core | 0,8 core | 32 core |
| RAM | 13,1 GB | 12 GB | 31,3 GB |

**Analysis nghẽn VRAM, synthesis thì rảnh mọi thứ.** Hệ quả trực tiếp: số worker song song
**không được** là hằng số. Trong analysis, VRAM chỉ còn ~1,5 GB - thêm một process VieNeu hay
Whisper vào đó là OOM. Trong synthesis còn ~6,8 GB, thoải mái vài process.

Vì thế bước "chồng lấn giai đoạn" ở mục kế hoạch bên dưới **không miễn phí như tôi từng viết**:
nó đòi Ollama, VieNeu và Whisper cùng thường trú, mà riêng Ollama đã chiếm 82%. Phải đo lại
trước khi làm, hoặc phải cho Ollama nhả model giữa chừng.

## Số đo, ngày 2026-08-31

Đo trong lúc chạy thật giai đoạn `chapter_synthesis`, máy Ryzen 9845HX + RTX 5060 Laptop 8 GB + 32 GB RAM:

| Tài nguyên | Đang dùng | Tổng |
|---|---|---|
| GPU compute | **14–18%** | 100% |
| VRAM | **1,30 GB** | 8,15 GB |
| CPU (tổng mọi process) | **0,8 core** | 32 core |
| Đĩa | 99,1% idle, 7 write/s, 2,2 ms/write | — |
| RAM | 12 GB | 31 GB |

Một segment mất ~6,7 giây cho ~7,4 giây audio (≈1× realtime). Tính cả analysis thì cả pipeline chạy
khoảng **4,3× realtime**. Với 915 chương, đó là cỡ **33 ngày** chạy liên tục.

**Không tài nguyên nào bão hoà.** Đây là điểm mấu chốt: không phải thiếu CPU, không phải thiếu VRAM,
không phải nghẽn đĩa.

## Nguyên nhân gốc

VieNeu sinh audio **tự hồi quy theo từng frame**: mỗi bước là một matmul rất nhỏ có phụ thuộc tuần tự vào
bước trước. GPU chạy vài micro giây rồi chờ launch bước kế. 15% utilization là con số kinh điển của decode
tự hồi quy đơn luồng — tăng CPU hay đĩa không giúp gì.

Cách duy nhất nâng utilization cho decode tự hồi quy là **cho nhiều câu chạy đồng thời**, để mỗi bước làm
việc trên một matmul lớn hơn. `TTSCoordinator` có truyền `Vieneu(max_batch_size=8)` nhưng **không bao giờ gọi
`infer_batch`** — mỗi segment một lần `infer` riêng.

## Vì sao không đơn giản bật batching lên

```python
def _set_generation_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed % (2**32))
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
```

Seed là **global cho cả process**. Batch nhiều segment trong cùng một lần forward, hoặc chạy nhiều luồng
trong cùng process, đều làm audio của một câu phụ thuộc vào những câu đứng cạnh nó trong batch. Điều đó phá:

- "Khi resume, settings và voice mapping phải giữ nguyên" — và audio sinh lại phải giống hệt;
- mô hình immutable candidate của ASR/perceptual repair, vốn khóa từng candidate theo `generation_seed`.

Đây là đánh đổi **cố ý**, không phải sơ suất. Đừng gỡ nó bằng cách nới lỏng tính tất định.

## Hướng đã chọn: song song theo **tiến trình**, không theo luồng

Mỗi process con có **global RNG riêng**, nên chạy N process, mỗi process xử lý **một segment tại một thời
điểm**, cho ra audio **giống hệt** như hiện tại — trong khi GPU nhận N luồng decode đồng thời và utilization
tăng theo. Đây là cách duy nhất đạt được hiệu ứng batching mà không đụng tới invariant tất định.

### Ranh giới thiết kế bắt buộc giữ

- **Chỉ process cha ghi SQLite.** Process con không mở database. Cha vẫn là single writer, nên mọi
  transaction/CAS/checkpoint hiện tại giữ nguyên ngữ nghĩa.
- **Process con chỉ làm phần thuần hàm**: seed → inference → pitch variant → cân mức → ghi WAV atomic
  (`.part` + fsync + replace) → checksum → trả metrics. Không quyết định trạng thái.
- **Một segment không bao giờ bị chia cho hai process.** Đơn vị công việc là một segment trọn vẹn.
- **Lease worker không đổi.** Process con là con của worker, không phải worker thứ hai; `process_utils`
  đã có sẵn hàm kết thúc cả cây process, và invariant "kết thúc process con trước process cha" vẫn áp dụng.
- **Crash ở bất kỳ đâu vẫn an toàn.** Cha chỉ checkpoint sau khi nhận đủ kết quả; job dở dang chỉ đơn giản
  là làm lại. Không được để process con ghi vào đường dẫn artifact đang giữ.

### Cần đo trước khi chốt số process

- VRAM thực của **một** process VieNeu, gồm cả CUDA context riêng (trên Windows mỗi context tốn thêm vài
  trăm MB — nên 4 process **không** đơn giản là 4 × 1,3 GB).
- Còn đủ chỗ cho Whisper trong vòng repair, nơi TTS và Whisper thay phiên liên tục.
- Số process phải **thích ứng** theo VRAM trống và theo `resource_manager` khi có foreground pressure,
  không hard-code theo một máy (đúng như invariant đã có).

### Test bắt buộc

1. **Tất định**: cùng `generation_seed` cho ra WAV có cùng SHA-256, bất kể segment đó chạy ở process nào,
   và bất kể pool có bao nhiêu process.
2. **Crash/resume**: giết cha giữa chừng → không còn process con mồ côi, artifact đã commit nguyên vẹn,
   phần dở được làm lại.
3. **Single writer**: process con không mở được database.
4. **Thích ứng tài nguyên**: pool co lại khi có foreground pressure và giãn ra khi hết.

## Toàn cảnh: chỗ nào đang bỏ phí

Không chỉ TTS. Bảng dưới là mọi giai đoạn và mức dùng tài nguyên hiện tại:

| Giai đoạn | Chạy ở đâu | Hiện tại | Bỏ phí |
|---|---|---|---|
| Analysis (Ollama qwen3:8b) | GPU | 30-48% GPU, **1 request một lúc**, `OLLAMA_NUM_PARALLEL=1` | GPU + 19 core |
| TTS (VieNeu) | GPU | 15% GPU, **1 segment một lúc** | GPU + 32 core |
| ASR (Whisper turbo) | GPU | **1 segment một lúc** | GPU + 32 core |
| Perceptual QA (UTMOSv2) | **CPU** | **1 segment một lúc**, 3 lượt mỗi segment | **31/32 core** |
| Pitch WORLD, LUFS, checksum | CPU | inline, tuần tự | 31/32 core |
| Ghép chương (FFmpeg) | CPU | `-threads 1` | — |

`-threads 1` của FFmpeg là **cố ý** đi cùng `-fflags +bitexact` để chương ghép ra byte giống hệt nhau.
Đừng đổi nó để lấy tốc độ; nó không phải nút thắt.

## Đã đo: perceptual QA song song (bước 1)

`scripts/benchmark_parallelism.py --stage perceptual`, 24 segment đã commit, đo **trong lúc**
một run analysis khác đang dùng GPU và ~13 core - tức là điều kiện thực tế, không phải máy trống:

| worker | giây | job/phút | speedup | đầu ra |
|---|---|---|---|---|
| 1 | 186,1 | 7,7 | 1,00x | - |
| **4** | **112,3** | **12,8** | **1,66x** | **giống hệt** |
| 8 | 139,3 | 10,3 | 1,34x | giống hệt |
| 12 | 132,8 | 10,8 | 1,40x | giống hệt |
| 16 | 180,7 | 8,0 | 1,03x | giống hệt |

Hai kết luận:

1. ~~**Tất định giữ nguyên ở mọi cỡ pool.**~~ **Sai — và sai vì chính công cụ đo.** Script khi đó
   so kết quả sau khi `round(..., 4)`, nên nó báo "identical" trong khi điểm thật lệch khoảng
   **5e-07**. Chỉ khi chấm lại bằng pool thật, so từng bit, mới lộ ra. Xem mục dưới.
2. **Quá 4 worker thì tệ đi**, và lý do không phải thiếu core. Torch mặc định lấy một luồng mỗi
   core, nên 8 process đòi 8 x 32 = 256 luồng trên 32 core. Cỡ pool chỉ có nghĩa khi **từng
   thành viên bị ghim số luồng** - `--worker-threads` của script làm việc đó.

Vì thế đừng đọc "4 là tối ưu" thành một hằng số. Nó là tối ưu **khi chưa ghim luồng**.

## Số luồng torch làm đổi điểm UTMOSv2 — và điều đó đã đúng từ trước khi có pool

Đo trực tiếp, cùng một file, cùng một checkpoint, chỉ đổi `torch.set_num_threads`:

| file | 16 luồng | 2 luồng | 1 luồng |
|---|---|---|---|
| round_000 | 2.888798236846924 | 2.888798236846924 | 2.888798713684082 |
| round_001 | 2.445344924926758 | 2.445345401763916 | 2.4453461170196533 |
| round_004 | 2.4776558876037598 | 2.477656126022339 | 2.477656364440918 |

Torch chia matmul cho các luồng rồi cộng lại **theo thứ tự luồng nào xong trước**, nên số luồng đổi
thì mấy bit cuối đổi. Đây **không phải** hệ quả của việc song song hoá: điểm UTMOSv2 vốn đã phụ thuộc
vào số core của máy, chỉ là chưa ai nhìn ra.

Nó chỉ trở thành lỗi đúng nghĩa khi **một take được chấm ở process con còn baseline của preset đó
được chấm ở process cha**: phán quyết là hiệu của hai số, mà hai số lại đến từ hai chế độ số học
khác nhau. Lần chạy thử đầu tiên lệch đúng như vậy — 11/16 file.

Cách sửa: ghim số luồng **bên trong chính verifier** (`_pin_threads`, gọi từ `load()`), nên cha và
con dùng cùng một con số qua cùng một đường code. Không phải nới lỏng bằng dung sai, mà là làm cho
hai bên giống nhau **theo thiết kế**.

Sau khi sửa, chấm lại 24 file thật: **0 lệch, 3,08x nhanh hơn**.

### Bài học về công cụ đo

Script benchmark khi đó so kết quả đã `round(..., 4)`. Nó báo "identical" ở mọi cỡ pool và **tôi đã
tin**. Một phép so không nhìn thấy được sai khác thì tệ hơn là không so, vì nó được tin tưởng. Giờ
script so số thực đầy đủ, không làm tròn.

Và unit test cũng không bắt được: chúng dùng model giả trả về số cố định. Chỉ có chạy thật với
UTMOSv2 thật trên WAV thật mới lộ. **Việc gì đụng tới số học dấu phẩy động thì phải kiểm chứng bằng
dữ liệu thật.**

## Đã đo: TTS song song (bước 2) — 3 process, 2,16×

`scripts/benchmark_parallelism.py --stage tts` sinh lại segment đã commit bằng đúng seed và
voice profile của nó, rồi so checksum waveform. **Đầu ra giống hệt ở mọi cỡ pool** — điều
kiện tất định đạt, nên các con số dưới mới có nghĩa.

48 segment, 1 luồng torch mỗi worker:

| worker | giây | job/phút | speedup | GPU đỉnh | VRAM đỉnh | đầu ra |
|---|---|---|---|---|---|---|
| 1 | 228,8 | 12,6 | 1,00× | 23% | 1834 MiB | — |
| **3** | **105,9** | **27,2** | **2,16×** | **90%** | 5484 MiB | giống hệt |
| 5 | 104,6 | 27,5 | 2,19× | 88% | 7318 MiB | giống hệt |

**Chốt 3 worker.** 5 worker chỉ hơn 0,03× nhưng chiếm 7318/8151 MiB — không còn chỗ cho
foreground lẫn cho Whisper thường trú, đổi lấy một khoản gần bằng sai số.

### Cẩn thận khi đọc lại số này: số job ít làm hỏng kết luận

Cùng bộ đo, **12** segment thay vì 48 cho ra 3 worker = **1,42×**. Không phải nhiễu: mỗi
process phải tự nạp VieNeu, và với 4 job mỗi worker thì chi phí nạp chưa kịp khấu hao. Nếu
chỉ chạy bản 12 job rồi kết luận thì đã bỏ đi một nửa phần lợi có thật.

Quy tắc rút ra: **số job mỗi worker phải đủ lớn để chi phí khởi động nhỏ so với công việc**,
nếu không benchmark đang đo tốc độ nạp model chứ không đo throughput.

### GPU đã thực sự bão hoà

23% → 90%. Đây là lần đầu một giai đoạn trên máy này chạm trần GPU. Nghĩa là sau bước này,
TTS **không còn** là chỗ để vắt thêm bằng cách tăng song song — muốn nhanh nữa phải giảm
số lần sinh (bớt retry, bớt candidate) chứ không phải thêm worker.

## Đã đo: song song hoá phía client cho Ollama — **không cho gì cả**

Giai đoạn phân tích để GPU rảnh 57–82% (đo được 18–43% khi đang chạy) và còn ~2 GB VRAM,
nên nhìn thì rất giống chỗ có dư địa. Đo thật thì không.

Gửi 1, 2, 3 request đồng thời tới `/api/generate`, **xen kẽ các mức và lặp 4 vòng** để tải
nền trôi thì triệt tiêu:

| đồng thời | trung vị | dao động | speedup |
|---|---|---|---|
| 1 | 60,7 tok/s | 59,9–61,1 | 1,00× |
| 2 | 60,9 tok/s | 60,8–61,1 | 1,00× |
| 3 | 61,0 tok/s | 60,9–61,0 | 1,01× |

Server đang **tuần tự hoá** request; request thứ hai chỉ xếp hàng. `OLLAMA_NUM_PARALLEL`
mặc định là 1, và nó là biến môi trường của **server**, không phải thứ sửa trong mã ứng
dụng được. Muốn thử phải khởi động lại Ollama, nên việc này bị chặn cho tới khi không còn
run nào đang dùng nó.

### Cảnh báo về cách đo: lần đầu tôi đo ra 20,69×

Lần chạy đầu, tuần tự từ c=1 lên c=4, cho ra `1,00× / 6,27× / 20,69× / 20,67×`. Con số vô
lý, và nguyên nhân là **một run đang dùng chung Ollama**: mức c=1 hứng trọn lúc nghẽn
(3,0 tok/s) còn các mức sau chạy lúc rảnh (61 tok/s). Đo tăng dần trong khi tải nền giảm
dần thì **kết quả là hình dạng của tải nền**, không phải của thứ đang đo.

Cách chữa: **xen kẽ các mức và lặp lại**. Sau khi xen kẽ, dao động rơi xuống ±1 tok/s và
câu trả lời thật lộ ra là 1,00×.

## Thứ tự triển khai, mỗi bước phải đo trước và sau

Xếp theo **giá trị chia cho rủi ro**, không phải theo mức hấp dẫn:

1. **Perceptual QA song song trên CPU.** An toàn nhất trong tất cả: chấm UTMOSv2 là hàm **thuần đọc file**
   — không ghi artifact, không ghi SQLite, không quyết định trạng thái. 31 core đang rảnh hoàn toàn.
   (Lưu ý vẫn phải dùng **process** chứ không phải thread: `_preserved_inference_rng` cũng seed global.)
2. **TTS song song theo process.** Con ghi WAV atomic vào đường dẫn candidate riêng của nó rồi trả metrics;
   cha giữ độc quyền ghi SQLite.
3. **Whisper song song theo process.** Cùng khuôn mẫu; decode ở `temperature=0` nên tất định theo audio.
4. **Chồng lấn giai đoạn**: xác minh chương N-1 trong khi TTS sinh chương N. Cần cả hai model thường trú,
   mà VRAM thì thừa chỗ.
5. **Analysis nhiều request đồng thời.** Để cuối vì nó chạm vào candidate ledger bền và nhánh chia batch —
   rủi ro cao nhất, lợi ích không rõ bằng.

`scripts/benchmark_parallelism.py` đo trần thật cho từng bước trước khi sửa pipeline: bao nhiêu worker thì
vừa VRAM (**gồm cả CUDA context riêng của từng process**, không rẻ trên Windows), throughput dừng cải thiện
ở đâu, và quan trọng nhất — **kết quả có còn giống hệt bản một worker không**. Không đạt điều kiện cuối thì
số throughput vô nghĩa.

## Vẫn phải nhường foreground

Invariant "tự nhường foreground và tự tăng lại" không được đánh đổi lấy throughput. Kích thước pool phải
**thích ứng** theo VRAM trống và theo `resource_manager`, chứ không hard-code theo một máy.

## Việc nhỏ, an toàn, làm kèm

- Một lần chạy 2 chương tốn **16 lượt nạp VieNeu + 13 lượt nạp Whisper**. Trong vòng repair hai model thay
  phiên liên tục, mà VRAM chỉ dùng 1,3/8,15 GB — giữ cả hai thường trú trong giai đoạn đó là hợp lệ theo
  đúng chữ của invariant ("không giữ đồng thời **khi không cần**"), và bỏ được phần lớn 29 lượt nạp đó.

## Đừng tối ưu nhầm chỗ

Đĩa 99% idle và CPU 2,5% — **đừng** đụng vào fsync, checksum, hay số lần ghi `.part`. Chúng không phải nút
thắt và chúng là thứ giữ cho artifact an toàn khi crash.

## Pha tốn nhất của một lần chạy là pha duy nhất không dùng pool (đo 2026-09-04)

Chủ sách hỏi máy đã bị vắt kiệt chưa. Lấy mẫu GPU 25 giây ngay giữa lúc alpha.43 tạo
candidate clarity:

    GPU  : trung bình 23,7%   trung vị 16,0%   đỉnh 100%
    VRAM : trung bình 1.558 MiB   đỉnh 2.719 MiB / 8.151 MiB

Hơn 5 GB VRAM nằm không, và đỉnh 2.719 MiB xấp xỉ đúng `TTS_POOL_BASE_VRAM_MB` = 2.733,
tức **một model duy nhất**, dù log đã báo "Pool TTS song song: 3 tiến trình" trước đó.

Đọc code thì rõ: `pipeline.py` sinh candidate bằng một vòng lặp thẳng -
`for index, (item, candidate) in enumerate(generation_jobs, 1)`. Pha tổng hợp chính dùng
pool; pha sửa clarity thì không.

### Nó tốn bao nhiêu

Quy thời gian cho pha đang hoạt động trên log alpha.32, chỉ tính những bước liên tiếp
(bước nhảy cách quãng là lúc chạy dừng chứ không phải lúc pha làm việc):

| pha | công việc thật | số việc | trung vị mỗi việc |
|---|---|---|---|
| **Tạo candidate clarity (tuần tự)** | **4.707s** | 826 | **5,45s** |
| Kiểm tra phát âm (ASR) | 4.252s | 2.311 | 1,54s |
| Tạo audio chapter (**có pool**) | 2.658s | 2.466 | — |
| Kiểm tra candidate clarity | 2.325s | 1.652 | 0,85s |
| Perceptual QA chapter | 1.106s | 2.385 | — |

**Pha tốn nhất cả lần chạy chính là pha duy nhất chạy tuần tự.** Đường có pool đi được
0,93 việc/giây; đường tuần tự đi được 0,18 việc/giây.

Không đọc thẳng tỉ số 5,3× ấy thành mức tăng tốc hứa hẹn: candidate là bản sửa, văn bản và
tham số khác bản chính nên mỗi cái vốn đắt hơn. Mức đúng để kỳ vọng là mức song song của
pool - 3 tiến trình như lần chạy này chọn - nên 4.707s có thể xuống khoảng 1.600-2.400s,
tiết kiệm ~2.300-3.100s trên ~15.600s công việc đo được. Khoảng **15-20% một lần chạy**.

Điểm đáng chú ý nhất: **cơ chế đã có sẵn.** `_synthesis_pool` đang được đường tổng hợp
chính dùng, và nó đã tự co giãn theo VRAM qua `workers_for_vram`. Đây không phải xây mới,
mà là cho một vòng lặp dùng thứ vòng lặp bên cạnh đã dùng.

### Một con số suýt bị báo sai

Cách quy thời gian đầu tiên gán thời gian trôi qua cho *nhãn nhìn thấy gần nhất*, và nó cho
ra "Chuẩn bị và chia văn bản: 3.983s = 18,4%" - nghe như việc xử lý văn bản đang ăn một
phần năm lần chạy. Cách chặt hơn, chỉ tính khoảng giữa hai bước liên tiếp *cùng một nhãn*,
làm nhãn ấy **biến mất hoàn toàn**: nó không có bước liên tiếp nào, nên 3.983s kia là thời
gian rảnh bị gán nhầm chứ không phải công việc. Khi quy thời gian theo nhãn, hãy đòi hỏi
bằng chứng rằng nhãn ấy thực sự đang tiến triển.

### Việc cần làm (chưa làm - `pipeline.py` bị khoá lúc alpha.43 chạy)

Cho vòng sinh candidate dùng `_synthesis_pool` như đường tổng hợp chính. Đo lại bằng chính
phép đo trên: thời gian pha, và mẫu GPU/VRAM giữa lúc chạy.

## Whisper được nạp 189 lần trong một lần chạy, mất 25 phút (đo 2026-09-04)

Theo dõi log alpha.43 thấy `Nạp faster-whisper` lặp lại mỗi khoảng 70 giây. Đếm trên cả
alpha.32:

    189 lần nạp trong 378 phút, cách nhau trung vị 50 giây
    mỗi lần trung vị 7,15s  ->  tổng 1.502s = 25 phút = 9,6% công việc thật của lần chạy

(7,15s là *cận trên*: nó đo từ dòng "Nạp" tới dòng log kế tiếp, nên có thể gồm cả lần giải
mã đầu. Số lần nạp thì chính xác.)

### Vì sao lại nạp nhiều thế

129 trong 189 lần rơi ngay vào lúc vào pha "Kiểm tra candidate clarity". Vòng sửa chạy
theo nhịp: sinh candidate (TTS) → kiểm candidate (ASR) → vòng sau. Hai model thay nhau
chiếm VRAM và đá nhau ra mỗi vòng. 826 candidate chia cho 129 vòng là **6,4 candidate mỗi
vòng**, tức mỗi vòng **nạp 7 giây để làm khoảng 5 giây việc**.

### Cách sửa rẻ nhất, và vì sao nó rẻ

Giữ Whisper nằm lại trong suốt vòng sửa. Nghe như phải đánh đổi VRAM, nhưng phép đo nói
không: **giữa vòng sửa, VRAM đỉnh chỉ 2.719 MiB trên 8.151** vì vòng ấy chạy tuần tự với
một model TTS duy nhất. Whisper turbo float16 khoảng 1,5 GB, thừa chỗ trong 5,4 GB đang bỏ
không. Tiết kiệm ~1.400s mà không lấy đi gì.

**Giữ Whisper thường trú suốt cả lần chạy thì lại không đáng** - và đây là chỗ dễ nhầm.
1,5 GB ấy lấy mất một tiến trình của pool TTS ở pha tổng hợp chính: pha ấy tốn 2.658s với 3
tiến trình, còn 2 tiến trình thì thành ~3.987s, đắt thêm 1.329s - gần đúng bằng số tiết
kiệm được. Hoà. Và nếu vòng sinh candidate được cho dùng pool (mục trên), đánh đổi ấy còn
tệ hơn. Phạm vi mới là thứ làm cách sửa này đúng: **thường trú trong vòng sửa, không thường
trú ngoài nó.**

### Việc cần làm (chưa làm - `pipeline.py`/`asr.py` bị khoá lúc alpha.43 chạy)

Giữ model ASR sống qua các vòng của một chương thay vì nạp lại mỗi vòng. Đo lại bằng chính
cách đếm trên: số lần nạp mỗi lần chạy.

### Đính chính: đổi engine đã xử lý phần lớn chuyện nạp lại

Đo lại đúng cách ấy trên alpha.43, lần chạy dùng `asr.engine = faster`:

| | mỗi lần nạp (trung vị) | 189 lần | trên ~15.600s |
|---|---|---|---|
| alpha.32 — openai-whisper | 7,15s | 1.502s | **9,6%** |
| alpha.43 — faster-whisper | **1,31s** | ~248s | **1,6%** |

CTranslate2 nạp nhanh hơn PyTorch khoảng 5,5 lần, nên **giá trị của mục "giữ Whisper thường
trú" tụt từ ~1.400s xuống ~230s**. Vẫn dương, nhưng nhỏ hơn nhiều và không còn đáng đứng
trên mục nào khác. Việc đổi engine — làm vì tốc độ giải mã — đã sửa gần hết một vấn đề khác
mà tôi đang định sửa riêng.

(Mẫu của alpha.43 còn nhỏ: 13 lần nạp trong 18 phút. Nhưng 7,15 so với 1,31 không phải
nhiễu, và cả hai đo bằng cùng một cách: khoảng cách từ dòng "Nạp" tới dòng log kế tiếp.)

Bài học đáng giữ hơn con số: **tôi suýt ship một thay đổi tin là đáng 1.400s trong khi nó
đáng 230s**, vì đo nó trên một lần chạy dùng engine cũ rồi xếp hàng nó cho tương lai dùng
engine mới. Khi một thay đổi khác đang bay, hãy đo lại nền trên chính lần chạy ấy trước khi
xếp thứ tự.
