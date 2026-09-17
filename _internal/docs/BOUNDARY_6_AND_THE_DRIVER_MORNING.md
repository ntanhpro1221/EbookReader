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
