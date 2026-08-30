# Throughput: tại sao máy đang rảnh và làm gì với nó

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

## Việc nhỏ, an toàn, làm kèm

- Một lần chạy 2 chương tốn **16 lượt nạp VieNeu + 13 lượt nạp Whisper**. Trong vòng repair hai model thay
  phiên liên tục, mà VRAM chỉ dùng 1,3/8,15 GB — giữ cả hai thường trú trong giai đoạn đó là hợp lệ theo
  đúng chữ của invariant ("không giữ đồng thời **khi không cần**"), và bỏ được phần lớn 29 lượt nạp đó.

## Đừng tối ưu nhầm chỗ

Đĩa 99% idle và CPU 2,5% — **đừng** đụng vào fsync, checksum, hay số lần ghi `.part`. Chúng không phải nút
thắt và chúng là thứ giữ cho artifact an toàn khi crash.
