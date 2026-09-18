# Ranh giới 6 và buổi sáng cài driver (viết 2026-09-18, 02:5x — trước khi cả hai việc xảy ra)

Hai việc đòi cùng một cái GPU trong cùng một giờ, và cả hai đều đã hẹn:

| lúc | việc | cần gì |
|---|---|---|
| ~08:15 (ước từ tốc độ 688 câu/giờ lúc 02:52) | lô 6 đọc xong câu cuối | — |
| ngay sau đó | ranh giới 6: vá, test, vá chương hỏng, **đúc lại giọng**, ghép sách | GPU cho bước 3/4/4b |
| 09:00 | chủ sách cài BIOS + driver NVIDIA, khởi động lại **nhiều lần**, thử MUX | GPU rảnh, máy được reboot |

Viết trước để lúc ấy không phải quyết định dưới áp lực thời gian. **Luật: 9:00 là của chủ sách.**

## Quyết định theo đồng hồ, khi lô 6 vừa xong

Xem `date` rồi chọn đúng một nhánh:

- **Trước 07:45** → chạy cả ranh giới, nhưng KHÔNG thả lô 7. Hai lệnh, đúng thứ tự:

      runtime/.venv/Scripts/python.exe scripts/one_person_one_voice.py | tail -1
      bash scripts/boundary.sh 6 --recast auto <danh sách vừa in> 1:010 1:027 2:094 3:136 --no-next

  **Cú pháp quan trọng:** `NNN` trơn là chương của **lô này** (219..303); chương của lô khác phải
  viết `B:NNN`. Bốn chương bị cắt ra `_quarantine_2026-09-17` thuộc lô 1, 1, 2, 3 nên là
  `1:010 1:027 2:094 3:136` — viết trơn `010` là sai lô và ranh giới sẽ đi tìm chương 010 trong lô 6.

  Phải **chạy lại** `one_person_one_voice.py` ngay lúc ấy chứ không dùng danh sách cũ
  (`3:137 3:139 4:167` đo hôm 16-09): sách đã đổi 85 chương từ lúc ấy, nên danh sách đổi.

  **ĐÃ CHẠY LÚC 07:22 và danh sách là 27 chương** — không phải 12. Tính từ số thật (84 đoạn/chương,
  4,3 giây/đoạn đo trên lô 6) thì 27 chương ≈ **2,7 giờ GPU**, tức KHÔNG còn là việc làm kèm buổi
  sáng. Đề xuất cắt xuống **9 chương ≈ 55 phút**: bốn chương trong `_quarantine_2026-09-17`
  (`1:010 1:027 2:094 3:136`) cộng các chương lô 5 (`5:180 5:183 5:184 5:189 5:196`); phần còn lại
  chờ quyết định về giọng mới, vì kho giọng nới ra thì nhiều chương trong đó tự hết va chạm. Lý lẽ
  và số liệu: mục *"Danh sách đúc lại đã phình từ 12 lên 27 chương"* trong `docs/OPTIMISATION_QUEUE.md`.
  `--recast auto` chỉ tự tìm va chạm giọng **trong lô vừa xong**, không thấy lô khác.

  Bốn chương bị cắt được thử lại vì máy đúc lại đã khác: `keep_the_chapter_cast.py` ghim dàn giọng
  của chính chương ấy trước khi thu, và cổng `ship_only_recasts_that_help.py` vẫn đứng sau — tệ hơn
  thì nó lại bị dời ra (thoát 10, ranh giới đi tiếp). Không mất gì ngoài thời gian GPU.

  (`--no-next` giữ GPU trống cho chủ sách; bước 6b và 7 vẫn chạy, chúng không cần GPU.)

- **07:45 – 08:45** → chỉ chạy phần KHÔNG cần GPU, rồi dừng:

      bash scripts/boundary.sh 6 --dry-run          # xem nó định làm gì, không sửa gì
      runtime/.venv/Scripts/python.exe scripts/pending_patches/apply_all.py --apply

  rồi **để nguyên**, chờ chủ sách cài xong. Vá chương + đúc lại + thả lô 7 làm sau.

- **Sau 08:45 hoặc lô chưa xong** → không bắt đầu gì mới. Chờ. Nếu 09:00 lô vẫn đang đọc thì dừng
  theo lệnh của chủ sách (*"dừng lô để cài driver"*):

      runtime/.venv/Scripts/python.exe -m ebook_reader.cli stop
      # và dừng cả tiến trình canh: taskkill theo pid của boundary.sh trong runtime/big_batch_chain.log

## Sau khi chủ sách cài xong driver

Kiểm trước khi chạy lại bất cứ thứ gì có GPU — driver mới có thể làm torch mất CUDA:

    nvidia-smi
    runtime/.venv/Scripts/python.exe -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
    runtime/.venv/Scripts/python.exe -m ebook_reader.cli doctor

Cả ba xanh thì tiếp phần còn lại của ranh giới (hoặc cả ranh giới nếu nhánh trên chưa chạy), rồi thả
lô 7:

    bash scripts/launch_batch.sh 7 --seed-from "<SEED ghi trong log ranh giới>"

Ghi kết quả ba lệnh kiểm vào `docs/DEPENDENCIES.md` — driver là một phiên bản như mọi phiên bản khác,
và lần này nó đổi giữa hai lô nên phải có mốc.

**Nếu CUDA chết sau khi cài:** đã có bộ quay về trong `D:\Drivers\2026-09-18_Lecoo_N176\02_NVIDIA\`
(bản 581.80 bên bán chỉ định, chữ ký NVIDIA hợp lệ) và nút "Quay về NVIDIA 581.80" trong
`CAI_DAT_N176.hta`. Lô 7 chờ được; một dây chuyền không có CUDA thì không.

## Bốn đoạn đang hỏng, và điều phải chờ đợi ở bước 3 (đọc DB lúc 03:2x và 03:5x)

Cả bốn chương đều đã `completed` và đã có audio (bước ghép sách không bị chặn); các đoạn này chỉ bị
đánh dấu `ASR_MISMATCH_UNRESOLVED`, tức máy nghe lại không khớp chữ. ~~Bước 3 sẽ thu lại chúng.~~

**SAI — sửa 18-09 11:5x.** Bước 3 (`launch_repair.sh N`, không `--chapters`) chỉ chạy lại chương mà
lô **chưa hoàn thành**; đoạn hỏng nằm trong chương đã `completed` thì nó không nhìn tới. Cả hai lượt
ranh giới 6 (10:08 và 11:43) đều ghi `khong co chuong hong.` Bốn đoạn dưới đây vì thế **lên sách
nguyên như cũ**. Cột "chờ đợi gì ở bước 3" giữ lại làm dự đoán cho lần thu lại thật: đường duy nhất
hiện có là đúc lại cả chương (`--recast 6:234` ở ranh giới 7), 6 phút GPU mỗi chương cho một đoạn — để ranh giới
7, gộp với 225 sau khi `patch_a_censored_word_is_a_pause.py` vào cây. Một bước "thu lại đoạn hỏng
trong chương đã xong" rẻ hơn thì chưa có; ghi vào hàng tối ưu.

| chương | sách viết | Whisper nghe ra | chờ đợi gì ở bước 3 |
|---|---|---|---|
| 225 (đoạn 66) | `“Cái #&!@! Không phải lại nữa chứ?”` | *Cái thằng và... À còng...* | **vẫn hỏng, và đúng như vậy.** Giọng đọc tên ký hiệu (`#` → "thăng", `@` → "a còng"); thu lại bao nhiêu lần cũng thế. Chỉ `patch_a_censored_word_is_a_pause.py` chữa được, mà bản vá ấy phải xếp SAU ranh giới 6. Đừng đuổi theo nó ở bước 3. |
| 234 (đoạn 13) | `“Chất sống? Môi trường nguyên thủy?”` | *Môi trường Nguyên Thủy* | **nên khỏi.** Giọng đọc bỏ hẳn câu hỏi đầu — một lần thu lại với hạt giống khác thường là xong (ca chương 140 đã vậy). Kiểm lại sau bước 3. |
| 261 (đoạn 68) | `Jacob day day trán:` | *Rồi cọp dây dây chán* | **có thể vẫn hỏng, và không phải lỗi giọng đọc.** Tên "Jacob" cộng "day day" là chỗ Whisper hay chép sai (cả lô có 1.283 cảnh báo cùng họ: neo tên khoá). Nếu hai lượt thu lại vẫn trượt thì để nguyên và ghi vào hàng chờ, đừng vá gấp. |
| 266 (đoạn 12) | `“Thích khách!”` | *Trời cắt* (giống 0,18) | **có thể vẫn hỏng.** Bản thu 0,48 s cho hai âm tiết — 4,2 âm tiết/giây, nằm trong dải người nói bình thường, nên có lẽ không bị cắt cụt; Whisper nghe sai một clip nửa giây không ngữ cảnh. Thu lại hai lượt vẫn trượt thì để nguyên. |

Thêm một chỗ mù đã đo được: cổng nhịp chỉ soi đoạn có ≥ 24 ký tự (`rate_check_min_chars`), nên với
mấy đoạn này **ASR là chốt duy nhất**. Cả bốn đoạn hỏng của lô đều ngắn ≤ 6 từ, còn 3.828 đoạn dài
hơn 6 từ thì không một đoạn nào hỏng. Xem mục *"Đoạn NGẮN"* trong `docs/OPTIMISATION_QUEUE.md`:
việc đầu tiên là ĐO xem lối lặp-3 clip có giúp không, và tuyệt đối không mách chữ cho Whisper.

Số liệu kèm theo lúc 03:22: 2.690 đoạn `verified`, 1.302 `warning` (1.283 là neo tên khoá, 19 là
"dòng thời gian bản chép không thể có"), 3 `failed`, 1.286 lần **máy** cho qua, 0 lần người nghe cho
qua — tức chưa có phán quyết tai người nào bị các lượt thu lại làm mất hiệu lực.

## Hàng chờ đã xếp cho ranh giới này

`pending_patches/apply_all.py` `ORDER` hiện có hai bản vá, cả hai đã thử trên bản sao:

1. `patch_a_dead_belt_should_not_look_like_a_belt.py` — bỏ năm chốt chặn tải mạng đã chết của
   transformers trong `worker.py` (không đổi hành vi).
2. `patch_the_sdk_that_makes_the_voice_is_checked_too.py` — đưa `vieneu` và `sea-g2p` vào bảng phiên
   bản bắt buộc của hợp đồng chạy.

**Chưa xếp, và có lý do:** `patch_a_censored_word_is_a_pause.py` đổi chuỗi nói của chương 225 (đã thu
trong lô 6) nên phải xếp **sau** khi ranh giới 6 xong hẳn — xem docstring của nó.

## Còn chờ tai chủ sách

Nâng VieNeu 3.3.0 → 3.8.1 và các giọng mới: chỉ làm sau khi chủ sách chấm trên trang nghe
(`voice-review-page` trong bộ nhớ). Nếu chấm xong trước ranh giới thì `scripts/propose_a_new_voice.py`
sinh bản vá thêm giọng; nếu chưa, ranh giới 6 cứ chạy với kho giọng hiện tại — không chờ.

## Tai chủ sách đã chấm (18-09, 09:xx–11:xx) — ranh giới 6 dừng lại để lô 7 mở đầu bằng người kể mới

Ranh giới 6 được **cố ý dừng** lúc ~10:1x, trước khi tạo project nào, vì kết quả trang chấm giọng đổi
chính kho giọng mà lô 7 sẽ dùng. Quyết định của chủ sách (db artifact `danh_gia`):

- Nâng VieNeu 3.3.0 → 3.8.1: bảy giọng đang chạy "như cũ".
- Nhận cả 11 giọng mới; **mở lại Xuân Vĩnh** — ở 3.8.1 nó thành giọng nam tự nhiên miền Bắc.
- **Đức Trí dẫn chuyện từ chương 304** (lô 7). 000..303 giữ Phạm Tuyên.
- Nghe từng nấc rồi chọn: Đức Trí ×1,10, Thiền Tâm Đức ×1,05, Kim Thanh ×1,10, Mỹ Duyên giữ nguyên;
  Adam bựa và Mạnh Dũng hạ −2 nửa cung (như cái −4 của Thanh Bình).

Năm bản vá khoá, xếp theo thứ tự này (mỗi cái neo vào văn bản cái trước để lại):

1. `patch_vieneu_3_8_1.py` — pin, `uv.lock` sinh sẵn, hợp đồng chạy. **Sau khi áp:**
   `pip install --no-deps vieneu==3.8.1` và `pip uninstall -y perth` trong `runtime/.venv`,
   không thì test hợp đồng đỏ.
2. `patch_a_slow_voice_reads_at_its_own_speed.py` — `PRESET_SPEED_FACTOR`, tăng tốc bằng WORLD sau
   bước cao độ, giữ nguyên F0 và phổ.
3. `patch_a_slow_voice_is_judged_by_its_own_pace.py` — `PRESET_PACE_SCALE`: ở đúng nấc chủ sách chọn,
   cổng nhịp vẫn gọi 8/9/13/8 trên 25 câu là "chậm". Không phải số đo sai mà thước sai — băng
   12,5..24,5 là phân vị 2 của bảy giọng đang chạy (0,94..1,16 lần trung vị 15,64 kt/s), còn bốn giọng
   kể chuyện ở 0,77..0,81. Cổng nhân **sàn** với nhịp riêng của giọng; cận trên và cận cứng không đổi.
   Ngân sách khung sinh cũng theo nhịp THÔ của giọng, không thì câu dài của Đức Trí bị cắt cụt.
4. `patch_a_book_can_change_its_narrator.py` — `voices.other_narrators`: bộ phân vai không trao giọng
   của người kể KHÁC trong cuốn cho nhân vật nào. Cả hai chiều: sau 304 người nghe đã quen Phạm Tuyên
   là giọng kể; trước 304 một nhân vật được trao Đức Trí sẽ mang pin ấy sang lô 7.
5. `patch_the_pool_gains_voices.py` — 11 giọng (nối CUỐI tuple), Xuân Vĩnh (Bắc, bỏ cấm, đo lại), số
   tốc độ / nhịp / cao độ ở trên, và preview.

Không khoá, sửa thẳng: `cli create --narrator / --other-narrator`; lịch người kể `EBOOK_NARRATORS`
(`0=Phạm Tuyên;304=Đức Trí`, rỗng trong `book1.env`) trong `scripts/book_paths.py`, đọc bởi
`launch_batch.sh` (theo dải) và `launch_repair.sh` (theo từng chương — vá chương cũ vẫn là người kể
cũ); một dải vắt qua chương 304 bị từ chối. `voice_pool_pressure.py` không đếm người kể khác.

**Trúc Ly đổi giọng ở 3.8.1.** So bản thu thật của cùng 5 câu giữa hai bản: sáu giọng lệch dưới 0,7
nửa cung, riêng Trúc Ly 219,5 → 257,0 Hz (+2,7 nửa cung), ống thanh 14,98 → 14,39 cm. Chủ sách chấm
"như cũ" và quyết nâng; bảng số theo giọng engine thật sự phát nên Trúc Ly được đo lại từ preview mới.
Nhân vật đang ghim Trúc Ly sẽ nghe cao hơn từ lô 7 — đã báo chủ sách.

Kho sau bản vá: nam 3 → 11 preset phân vai được (cuốn 2 trừ hai người kể còn 9), nữ 5 → 8. Danh sách
đúc lại 27 chương ghi ở trên sinh ra từ kho cũ; tính lại sau khi áp.
