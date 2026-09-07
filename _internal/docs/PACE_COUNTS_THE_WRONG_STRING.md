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

## Rộng bao nhiêu — và ba lần tôi đoán sai con số này

**Mọi tiêu đề chương trong sách đều có số** (`Chương N - N: …`), nhưng phép kiểm nhịp chỉ chạy
khi segment có từ `rate_check_min_chars = 24` ký tự trở lên. Đó là điều quyết định, và tôi đã
bỏ sót nó ở lần ước đầu tiên.

Số **quan sát được** trên chín chương của alpha.57:

| tiêu đề | ký tự viết | bị kiểm? | nhịp đo được | kết quả |
|---|---|---|---|---|
| ch019 `Chương 18 - 18: Bịp bợm` | 16 | **không** | – | qua |
| ch020, ch021, ch022, ch024, ch025 | 17–21 | **không** | – | qua |
| **ch023 `Chương 22 - 22: Ấn tượng đầu tiên`** | **24** | **có** | **10,68** | **CHẾT** |
| ch026 `Chương 25 - 25: Danh tiếng…` | 36 | có | 13,20 | qua |
| ch027 `Chương 26: Phản diện phụ…` | 28 | có | 14,52 | qua |

**Một trên ba tiêu đề bị kiểm đã chết. Một trên chín chương mất tiêu đề.** Đó là quan sát, không
phải mô hình.

### Ba lần ước, ba lần sai theo cùng một hướng

| lần | giả định nhịp đọc tự nhiên | dự đoán cả cuốn | sai ở đâu |
|---|---|---|---|
| 1 | 15,8 kt/s | 241 chương | quên mất `rate_check_min_chars`, và giả định quá thấp |
| 2 | 15,8 kt/s, có lọc | 180 chương | vẫn giả định quá thấp |
| 3 | 17,3 kt/s (hiệu chỉnh trên **3** mẫu) | 180, "67 cái chắc chắn" | **ch026 nằm trong nhóm 67 ấy và đã qua** |

Mỗi lần hiệu chỉnh lại, con số tụt xuống. Nhịp đọc thật của ch026 tính ngược ra là **19,1
kt/s**, cao hơn hằng số tôi dùng 10%. Cả ước lượng dựng trên một hằng số tôi chưa đo tử tế, và
biên dao động của nó nuốt trọn khoảng cách tới ngưỡng.

**Nên tôi không đưa con số cho cả cuốn nữa.** Cái đứng vững:

- **Cơ chế chắc chắn** — khớp đến số lẻ thứ hai trên ch023, và giải thích được vì sao 11 lần
  thử cho 11 kết quả y hệt.
- **Tần suất quan sát được: 1/9 chương, 1/3 tiêu đề bị kiểm.** Muốn con số cho cả cuốn thì phải
  đo nhịp đọc tự nhiên trên vài trăm segment có chữ số, chứ không phải trên ba cái.

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
