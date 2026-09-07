# Thước đo nhịp đếm chữ viết, còn giọng đọc phát ra chữ nói

Đo 2026-09-08 04:20, khi alpha.57 để lại hai segment **không có audio nào cả** sau 11 lần thử.

## Hiện tượng

```
c00005_s0000000  'Chương 22 - 22: Ấn tượng đầu tiên'
   error: high-quality TTS retry required: speech pace 10.68 chars/s;
          split=segment too short to split safely; pace_band=already normal
```

Mười một lần thử, mười một lần cùng một lỗi. Không phải xui — **không thể qua được**.

Chương ấy mất tiêu đề, và mất tiêu đề thì chương không xuất bản được.

## Vì sao không thể qua

`segment_duration_policy` và phép kiểm nhịp đều đếm như nhau:

```python
speakable_chars = sum(char.isalnum() for char in text)
```

Trên `text` **như nó được viết**. Nhưng `spoken_text()` không nở số ra chữ — `22` đi thẳng vào
TTS, và VieNeu đọc nó thành *"hai mươi hai"*.

| | ký tự |
|---|---|
| `Chương 22 - 22: Ấn tượng đầu tiên` | **24** |
| `Chương hai mươi hai - hai mươi hai: Ấn tượng đầu tiên` | **40** |

Giọng đọc phát ra lượng tiếng của 40 ký tự, thước đo chia cho 24. Ở thời lượng 2,25 giây:

| cách đếm | nhịp | dải cho phép |
|---|---|---|
| theo chữ **viết** | **10,67 kt/s** | dưới sàn 12,5 ⇒ **trượt** |
| theo chữ **đọc** | **17,78 kt/s** | giữa dải [12,5 – 24,5] ⇒ đạt |

Báo cáo lỗi ghi **10,68**. Khớp đến số lẻ thứ hai.

## Dự án đã có sẵn công cụ đúng, và đang dùng nó ở chỗ khác

`vietnamese_number_words` nằm trong `text_processing.py`, và `asr.py:221` gọi nó **chính vì lý
do này** — để so bản ghi với văn bản thì phải nở số ra chữ trước. ASR biết số nở ra; thước đo
nhịp thì không.

## Rộng bao nhiêu

**Mọi tiêu đề chương trong sách đều có số** (`Chương N - N: …`). Nhưng không phải cái nào cũng
bị kiểm: phép kiểm nhịp chỉ chạy khi segment có từ `rate_check_min_chars = 24` ký tự trở lên.

| | |
|---|---|
| tiêu đề có số | 476/478 |
| đủ dài để **bị kiểm** | **274** |
| dự đoán trượt | **180** (38% tổng số chương) |
| trong đó **xa dưới ngưỡng** (<11 kt/s) nên gần như chắc | **67** |

> **Con số 180 mỏng, con số 67 chắc.** Mô hình hiệu chỉnh trên vỏn vẹn **ba** tiêu đề đã chạy
> thật (nhịp đọc tự nhiên 17,3 kt/s trên chữ đọc). Ước đầu tiên của tôi dùng 15,8 và cho 241
> cái; nó dự thừa — chương 012 bị dự là chết mà thật ra đo được 13,87 kt/s và qua. Những cái
> sát ngưỡng là tung đồng xu; những cái dưới 11 thì không.
>
> **Cơ chế thì chắc chắn**, độc lập với con số: nó khớp đến số lẻ thứ hai trên chương 023.

## Hướng sửa

Đếm ký tự **sau khi nở số**, dùng đúng `vietnamese_number_words` mà ASR đang dùng. Nó chạm vào:

- `segment_duration_policy` — `generation_seconds` sẽ **tăng** cho văn bản có số, tức cho mô
  hình thêm khung để nói hết. Đúng hướng.
- phép kiểm nhịp — nhịp đo sẽ đúng với thứ tai nghe được.

Đây là thay đổi rộng: mọi segment có chữ số đều đổi. Cần cả bộ test và tốt nhất là một lượt
chạy thật trước khi tin.

## Cùng một hình dạng, lần thứ tư trong một đêm

| phép kiểm | định đo | thực tế đo |
|---|---|---|
| neo tên | tên đọc sai | đoạn chỉ gồm một tên ngắn |
| `is_vocalization_only` | tiếng cười | tiếng cười — trừ khi viết `Ahaha` |
| trần khung | mô hình lảm nhảm | câu không hạ giọng |
| **nhịp đọc** | **đọc quá chậm** | **văn bản có chữ số** |

Xem [WHY_A_GOOD_TAKE_GETS_THROWN_AWAY.md](WHY_A_GOOD_TAKE_GETS_THROWN_AWAY.md).
