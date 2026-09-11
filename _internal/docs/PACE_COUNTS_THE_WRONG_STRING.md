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

## Đã sửa 2026-09-08 05:20

`spoken_speakable_chars()` trong `audio_io.py`: nở chữ số ra chữ đọc bằng
`vietnamese_number_words` rồi mới đếm. Dùng ở cả hai chỗ từng đếm sai —
`segment_duration_policy` (số khung cho phép sinh) và phép kiểm nhịp.

Tiêu đề chương 023 giờ đo **17,78 kt/s** thay vì 10,68.

### Ba chỗ cố ý KHÔNG đụng

1. **`is_short_utterance` vẫn đếm chữ viết.** Nó trả lời câu hỏi khác — *"đây có phải một câu
   ngắn không?"* — và với câu hỏi ấy thì độ dài viết mới là thứ đáng đếm.
2. **Số từ 1000 trở lên vẫn tính theo chữ viết**, vì `vietnamese_number_words` dừng ở 999.
   Chúng vẫn bị đếm thiếu. Bịa một hệ số ước cho chúng là đoán, mà đoán chính là thứ đã tạo ra
   lỗi này.
3. **`rate_check_min_chars` giữ nguyên 24.** Nhưng lưu ý hệ quả: đếm theo chữ đọc làm nhiều
   segment vượt ngưỡng 24 hơn trước, nên **nhiều segment bị kiểm nhịp hơn**. Ví dụ
   `Chương 129 - 129: Lật bàn [I]` đi từ 19 lên 49 ký tự. Đó là đúng hướng — một câu 49 ký tự
   đọc thì đủ dài để đo nhịp thật — nhưng nó là thay đổi hành vi, không phải chỉ sửa số học.

### Kiểm trước khi áp

- **0/14 phán quyết người nghe dính segment có chữ số**, nên đổi số khung sinh không làm mất
  phán quyết nào.
- Ba test ghim: tiêu đề ch023 đếm 24→40 và vượt sàn; văn bản không có số đếm **y hệt như trước**;
  số quá lớn để đọc thành chữ thì để nguyên chứ không đoán.

## Chương hai (2026-09-10): cùng thước, sai theo cách khác — từ ngắn

Lô 3 mất chương 075 vì một câu dẫn truyện, 10/10 lần, mỗi lần một seed:

```
"Và Alice đã ở đó để tận dụng sơ hở ấy."   27 ký tự đọc · 11 từ · 1 chỗ nghỉ
11,00  11,38  11,38  11,80  11,38  11,00  10,64  11,38  11,80  11,00 chars/s   (sàn 12,5)
split     = segment too short to split safely   (38 < 100)
pace_band = already normal
```

Mười con số trong một dải 1,2 chars/s không phải xui: là số học, lần thứ hai. Câu này có
**2,25 chữ mỗi từ**; trung vị của 8.301 bản thu đã qua ở lô 1–3 là **3,33**. Cùng một tốc độ
đọc — âm tiết mỗi giây — thì câu toàn từ ngắn ("ở đó để", "sơ hở ấy") cho ra ít chữ mỗi giây
hơn, và thước "chars/s", vốn vay mượn cho "tốc độ đọc", gọi nó là chậm.

Đo lại theo âm tiết (tiếng Việt đơn âm, từ = âm tiết): 11 / (27 / 11,00) = **4,48 âm tiết/giây**.
Phân bố của kho: p0.5 3,22 · p1 3,51 · p2 3,76 · **p50 4,67** · p98 6,07. Bản thu ấy đọc ở
nhịp bình thường của chính giọng này. Chỉ có thước chậm.

Cả cuốn tới giờ chỉ **hai** bản thu đã qua có ≤ 2,3 chữ/từ — và chúng qua vì đọc **nhanh**
(6,2 âm tiết/giây). Tức là câu toàn từ ngắn phải đọc nhanh hơn người khác mới được thước chữ
công nhận là "không chậm". Đó là định nghĩa của một thước lệch.

### Sửa thế nào, và vì sao không phải là hạ sàn

Hạ sàn 12,5 là đổi một con số bịa lấy một con số bịa khác. Sửa đúng họ với chương một: thêm
**phép đếm thứ hai** — âm tiết mỗi giây, sàn 3,75 (p2 của kho, cùng cách chọn 12,5) — và chỉ
kết tội "chậm" khi **cả hai** cùng nói chậm (`pace_is_outlier` trong `audio_io.py`, hàng chờ
`patch_pace_counts_syllables_too`). Cận trên giữ nguyên theo chữ.

Thay đổi một chiều: chỉ **bớt** cờ, không thêm. Bản thu được tha thêm phải có nhịp âm tiết
trong dải bình thường. Đếm từ thay cho âm tiết đếm **thiếu** ở tên nước ngoài ("Alice" hai âm
tiết) và chữ số — tức nhịp âm tiết đo ra thấp hơn thật — nên sai số nghiêng về giữ cờ như cũ,
không nghiêng về tha.

Phép thử đầu tiên là chính chương 075, chạy lại ở lô vá lô 3: câu ấy ở 4,48 âm tiết/giây phải
qua ngay lần đầu. Nếu nó vẫn thử mười lần thì bản vá sai, và số 10 sẽ nói thế trước khi ai
kịp nghe.

### Rộng bao nhiêu — đếm trước khi đoán, lần này

Trong lô 3 tới 19:50 (20/32 chương), 22 segment chạm sàn nhịp; 17 ở phía chậm. Nhìn cột
chữ/từ của 17 cái ấy: 2,45 · 2,67 · 2,67 · 2,78 · 2,88 · 2,90 · 2,92 · 2,93 · 3,00 · 3,10 · 3,10
· 3,21 · 3,25 · 3,33 · 3,44 · 3,52 — quá nửa dưới trung vị kho 3,33, và ba cái tốn nhiều lần
thử nhất (11, 9, 4) đều ≤ 2,92. Tổng cộng ~38 lần sinh thừa cho một lớp lỗi mà seed không
chữa được, cộng một chương mất. Với bản vá, câu 9 lần thử ("Thalia hừ mũi…", 11 từ, 32 ký tự
đọc, 11,1 chars/s) đo 3,81 âm tiết/giây — vừa qua sàn 3,75; nó là ca **sát ngưỡng**, và nếu
lô 4 còn thấy nó thử lại vài lần thì sàn âm tiết đang đúng chỗ, không phải sai.

### Chứng minh trên audio thật, 21:38 ngày 2026-09-10

Chương 075 chạy lại ở lô vá, cùng một đoạn (cùng hash văn bản `2dd21f158c6c`):

```
              trước bản vá                    sau bản vá
số lần thử    11 (10 lần sinh + 1 chia nhỏ)   1
nhịp chữ      10,64 … 11,80 kt/s              10,64 kt/s
nhịp âm tiết  (không đo)                      4,50 /giây   (sàn 3,75)
pace_outlier  1                               0
kết cục       SEGMENT_FAILED, mất chương       signal_passed, không cờ nào
```

Đây là dạng bằng chứng tốt nhất mà một lô vá cho được, và nó khác hẳn ba bản vá "chưa chứng
minh": phép đo từng chặn **đã tái diễn** — 10,64 kt/s là con số *thấp nhất* trong cả mười lần
thử trước, tức sàn cũ 12,5 chắc chắn sẽ bắn — nhưng lần này nó đi đường khác. Không phải "chạy
lại thì xanh"; là "cùng một con số, quyết định khác".

### Dự đoán ghi TRƯỚC khi ranh giới lô 4 chạy (2026-09-11, 07:05)

Lô 4 hỏng đúng 2 chương, **cùng một nguyên nhân** theo nhãn mới (`SEGMENT_FAILED — speech pace N
chars/s`), nhưng hai ca khác hẳn nhau, và chỉ một cái được bản vá trong hàng chờ cứu:

```
097  'Sơ A-lờ-va-ra sững sờ, hai mắt mở to.'          11 lần thử, 11,53 kt/s
     25 ký tự đọc · âm tiết: đếm nay 8 -> 3,69/giây (DƯỚI sàn 3,75)
                              tách gạch 11 -> 5,07/giây      => bản vá CỨU ĐƯỢC
106  '... như, "password", "123456", thậm chí là "qwerty"'   11 lần thử, 12,35 kt/s
     70 ký tự đọc · âm tiết: đếm nay 17 -> 3,00/giây
                              tách gạch 17 -> 3,00/giây      => bản vá KHÔNG cứu
```

097 là đúng lớp đã làm mất chương 084: một cách đọc nối gạch (`A-lờ-va-ra`) đếm thành một âm
tiết. `patch_a_transliteration_is_many_syllables` áp ở bước 1 của ranh giới, trước lô vá ở bước
3, nên **097 phải qua ngay lần thử đầu**. Nếu nó vẫn thử mười một lần thì bản vá sai.

106 thì rơi vào đúng **hai giới hạn còn lại** mà docstring của bộ đếm đã nói ra: chữ số và tên
tiếng Anh **chưa có cách đọc trong sổ**. `password` đếm 1 âm tiết (đọc ra 2), `qwerty` đếm 1,
`123456` đếm 1 — `vietnamese_number_words` chỉ nở tới 999 nên số sáu chữ số để nguyên. Nếu số ấy
được đọc từng chữ số thì câu có ~26 âm tiết, tức 4,6/giây và hoàn toàn bình thường; bản thu có
lẽ không chậm, chỉ thước vẫn đếm thiếu.

**Chưa vá 106**, và cố ý: tôi không biết giọng đọc phát ra `123456` thành mấy âm tiết, và đoán
con số ấy là đúng thứ đã sinh ra cả hai lỗi trước. Hướng đo được: cho `password`/`qwerty` một
cách đọc trong sổ (máy phát âm vốn để làm việc ấy) và đếm số dài theo từng chữ số — nhưng phải
**nghe** hoặc đo trước, không sửa mù.
