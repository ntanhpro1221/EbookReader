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
