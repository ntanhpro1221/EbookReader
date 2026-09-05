# Đọc một từ tiếng Anh bằng âm thuần Việt: công thức và nguồn

Không phải bảng tra từng từ. Mỗi luật dưới đây đến từ âm vị học tiếng Việt hoặc từ nghiên
cứu về cách tiếng Việt hấp thụ từ vay mượn, và ví dụ chỉ dùng để **kiểm tra luật**, không
phải để mã hoá cứng.

## Đường đi

```
từ tiếng Anh → CMUdict (ARPAbet) → tách âm tiết → luật dưới đây → âm tiết tiếng Việt
```

CMUdict cho phiên âm âm vị chuẩn, tương đương IPA. Đi qua âm vị chứ không qua chữ viết là
điều bắt buộc: `knight` và `night` viết khác nhau nhưng đọc y hệt, còn `read` một chữ viết
lại có hai cách đọc.

## Ràng buộc nền: tiếng Việt cho phép những gì

| | tiếng Việt |
|---|---|
| phụ âm cuối | **chỉ 6**: /p, t, k, m, n, ŋ/ |
| cụm phụ âm đầu | **không có**, trừ /Cw/ |
| cụm phụ âm cuối | **không có** |

Nguồn: [Vietnamese phonology (Wikipedia)](https://en.wikipedia.org/wiki/Vietnamese_phonology).

Mọi luật còn lại chỉ là hệ quả của ba dòng này.

## Luật 1 — Phụ âm cuối phải hạ xuống một trong sáu âm, không được biến mất

Trước đây chỉ 7 âm ARPAbet được ánh xạ và **mọi âm khác bị bỏ im lặng**, nên `Card` ra `Ca`,
`Soul` ra `Xô`, `Seed` ra `Xi` — từ bị cụt giữa chừng.

Ánh xạ: âm tắc hữu thanh lấy âm vô thanh cùng vị trí, âm xát lấy âm tắc gần nhất.

| âm Anh | âm Việt | | âm Anh | âm Việt |
|---|---|---|---|---|
| D, DH, S, SH, T, TH, Z, ZH | **t** | | B, F, P, V | **p** |
| G, K | **c** | | CH, JH | **ch** |
| L, N | **n** | | M | **m** |
| NG | **ng** | | R | *bị lược* |

Đối chiếu với **289 phiên âm đã được chấp nhận** trong dự án: `s`→`t` 8 lần (so với 4 lần bị
bỏ), `l`→`n` 7 lần (so với 4), `th`→`t`, `c`→`c`. Luật khớp với thực tế đã dùng.

## Luật 2 — Cụm phụ âm cuối: giữ đúng một âm, và âm nào thì có luật

Theo phân tích Optimality-Theory về cách tiếng Việt hấp thụ cụm phụ âm
([Sejong J. Univ. Lang. 18-1](https://www.sejongjul.org/archive/view_article?pid=jul-18-1-69)):

| cụm | giữ | ví dụ trong bài |
|---|---|---|
| vang + tắc | **âm vang** | /valv/ → **van** |
| tắc + vang | **âm tắc** | /kabl/ → **cáp** |
| tắc + tắc | **âm thứ hai** | /kɔʁd/ → **cót** |

Vì thế `golf` → **Gan**, đúng như tiếng Việt thật gọi môn *golf* là **"gôn"**.

## Luật 3 — /r/ bị lược, không đọc

Tiếng Anh-Anh vốn **không phát âm /r/ cuối**: `card` là /kɑːd/, `guard` là /ɡɑːd/. Nên từ
đã mất /r/ trước khi tiếng Việt chạm vào. `Card` → **Cát**, `Guard` → **Gát**.

## Luật 4 — Cụm phụ âm đầu bị tách bằng nguyên âm chèn "ơ"

Tiếng Việt không có cụm phụ âm đầu, nên `bl`, `cr`, `str` không đọc được như viết. Nguồn
trên cho hai cách sửa: **chèn nguyên âm** (/slip/ → /silip/) hoặc **lược bỏ** (/blø/ → /lɤ/).

Chọn **chèn**, vì nó giữ được cả hai phụ âm — và đó cũng là hình dạng người nghe mô tả:
*incredible* đọc là **in-cờ-ri-đi-bồ**, chữ /k/ tách ra thành âm tiết riêng chứ không mất.

Nguyên âm chèn là **/ɤ/, viết "ơ"**. `Blade` → **Bơ-lất**, `Street` → **Xơ-trít**.

## Luật 5 — Sau i thì /k/ viết "ch", /ŋ/ viết "nh"

Đây là luật chính tả tiếng Việt, không phải lựa chọn: sau nguyên âm trước, /k/ và /ŋ/ có
biến thể ngạc hoá viết là ⟨ch⟩ và ⟨nh⟩. Nên `King` → **Kinh**, không phải "king" — vì
"king" **không phải âm tiết tiếng Việt**.

Chỉ áp dụng sau **i**, không áp dụng sau **e**: "éc" và "reng chuông" là tiếng Việt, còn
"ếc" và "rênh" thì không. Ban đầu tôi làm rộng cho cả /ɛ/ và /æ/, và nó biến `Deck` thành
"Đech", `Rank` thành "Renh".

## Luật 6 — Bán nguyên âm cuối nhường chỗ cho phụ âm cuối

Vần tiếng Việt là *nguyên âm + tối đa một phụ âm*. Một nguyên âm đã kết thúc bằng bán nguyên
âm thì không nhận thêm phụ âm được: **"ất" là vần, "ấyt" thì không**; "ót" là vần, "oít" thì
không.

Nguyên âm đôi tiếng Anh rơi đúng vào hình dạng đó, nên bán nguyên âm nhường chỗ:
`Gate` → **Gất**, `Void` → **Vót**.

Chỉ khi có phụ âm cuối. Không có thì nguyên âm đôi giữ nguyên: `Noah` → **Nô-a**.

## Luật 7 — Âm tiết đóng bằng âm tắc bắt buộc mang thanh sắc

Chính tả tiếng Việt: âm tiết kết thúc bằng **p, t, c, ch** chỉ mang được **sắc hoặc nặng**,
không bao giờ mang thanh ngang. Nên "xit", "cat", "đec" **không phải từ tiếng Việt**.

Chọn **sắc**. Dấu đặt lên nguyên âm đã mang dấu chất lượng nếu có ("ây" → "ấy"), nếu không
thì lên nguyên âm cuối của phần vần.

`Seed` → **Xít**, đúng như người nghe viết.

## Luật 8 — /w/ đầu từ là âm đệm, viết "o"/"u"

Tiếng Việt **không có phụ âm /w/**; [w] là âm đệm nằm giữa phụ âm đầu và vần, viết bằng
**o** hoặc **u** (`toán`, `huệ`). Từ mượn thật đi theo đúng đó: `Washington` là
**"Oa-sinh-tơn"**, `William` là **"Uy-li-am"**.

Viết âm đệm "u" ngay trước một nguyên âm cũng viết "u" thì ra "uu" — không phải nhân âm
tiếng Việt. Nên nguyên âm chuyển sang dạng đi sau âm đệm: `Wolf` → **Uôn**.

## Luật 9 — /l/ thành âm tiết thì hoá nguyên âm

Trong `incredible` hay `Michael`, âm /l/ cuối **tự nó gánh một âm tiết** mà không có nguyên
âm nào. Tiếng Việt không có phụ âm nào làm được thế, nên nó **trở thành nguyên âm**: đuôi
đọc là **"ồ"**.

Bằng chứng có sẵn ngay trong dự án: bảng ngoại lệ đã ghi `Michael` → **"Mai-cồ"**. Trước
đây luật này chỉ áp dụng khi phụ âm đầu là K — tức là một đặc cách cho đúng một cái tên.
Giờ nó là luật, và `Michael` **rơi ra từ luật** chứ không cần ngoại lệ nữa.

`Table` → Tây-bồ, `Little` → Li-tồ, `Cable` → Cây-bồ.

## Luật 10 — Schwa không đọc thành "a"

CMUdict viết **cả /ʌ/ lẫn /ə/ đều là AH**, chỉ phân biệt bằng chữ số trọng âm — và code cũ
**cắt bỏ chữ số đó**, nên hai âm khác hẳn nhau bị đọc giống nhau thành "a".

Schwa là nguyên âm **giữa-trung tâm**, và tiếng Việt có đúng một nguyên âm như thế: **"ơ"**.
Nên AH không trọng âm được đổi tên thành AX và đọc là "ơ".

`Incredible` → **In-cơ-re-đơ-bồ** (trước: "in-cơ-re-đa-bồ").

Việc đổi tên này **làm hỏng bảng ngoại lệ** vì bảng đó khoá trên "AH" — `Benjamin` tụt từ
"Ben-gia-min" xuống "Ben-giơ-mân". Tra ngoại lệ giờ gập schwa về AH trước khi tìm, nên các
cách đọc do người chọn không bị mất lặng lẽ.

## Kết quả

| từ | đọc | | từ | đọc |
|---|---|---|---|---|
| Seed | **Xít** | | King | **Kinh** |
| Card | Cát | | Guard | Gát |
| Deck | Đéc | | Epic | E-pích |
| Blade | Bơ-lất | | Street | Xơ-trít |
| Gate | Gất | | Void | Vót |
| Soul | Xôn | | Golf | Gan |
| Wolf | Uôn | | Noah | Nô-ơ |
| Table | Tây-bồ | | Little | Li-tồ |
| Michael | Mai-cồ | | Incredible | In-cơ-re-đơ-bồ |

Hai ví dụ người nghe đưa ra — `seed` → **"xít"** và `king` → **"kinh"** — **rơi ra từ
chính bộ luật**, không phải được nhét vào bảng tra. `Michael` → "Mai-cồ" trước đây phải
nằm trong bảng ngoại lệ thì giờ cũng tự rơi ra.

## Bảng nguyên âm: đã kiểm, không cần sửa

Nguồn thứ hai ([Sejong J. Univ. Lang. 22-2](https://www.sejongjul.org/archive/view_article?pid=jul-22-2-105))
cho thứ tự ưu tiên khi chọn nguyên âm gần nhất:

> IDENT-[±HIGH] >> IDENT-[±BACK] >> IDENT-[±ROUND]

tức **giữ độ cao lưỡi trước, rồi vị trí trước/sau, tròn môi bỏ sau cùng**.

Áp thứ tự đó vào bảng hiện tại thì thấy `AE → e` và `AH → a` "lệch". **Nhưng đó là lỗi của
tôi, không phải của bảng**: để tính được chi phí tôi phải tự gán đặc trưng cao/thấp cho
từng nguyên âm, và chính mấy giá trị tự gán đó sai.

Kiểm lại bằng bằng chứng — **31 từ một âm tiết** đã được chấp nhận trong dự án:

| âm Anh | dữ liệu | bảng đang dùng |
|---|---|---|
| AA | a ×6 | a ✓ |
| EY | ây ×4 | ây ✓ |
| AE | **e ×4** | e ✓ |
| AO | o ×3 | o ✓ |
| AY | ai ×3 | ai ✓ |
| OW | ô ×2 | ô ✓ |
| EH | e ×2 | e ✓ |

**Không một ánh xạ nào lệch.** Nếu tôi sửa bảng theo phép tính đặc trưng ở trên thì đã đổi
`AE` từ "e" sang "a" và làm hỏng bốn từ đang đúng.

Bài học: một khung lý thuyết đúng vẫn cho kết luận sai nếu dữ liệu nạp vào nó là do mình
tự nghĩ ra. Chỉ dùng nó khi có bảng đặc trưng từ nguồn, không phải từ trí nhớ.

## Còn hở

1. **Nguyên âm không nhấn vẫn lệch một chút với tai người nghe.** `incredible` ra
   "In-cơ-re-đơ-bồ", người nghe nói "in-cờ-ri-đi-bồ". Khung âm tiết và đuôi giống hệt; chỗ
   khác là hai nguyên âm không nhấn: tôi đọc theo **âm** (schwa → "ơ"), người nghe đọc theo
   **chữ viết** ("cre-di" → "ri-đi"). Cả hai đều có lý; chưa có cách phân xử ngoài tai.
2. **Thanh điệu ngoài âm tiết đóng.** Âm tiết mở đều mang thanh ngang. Tiếng Việt thật phân
   bố đa dạng hơn — người nghe viết "cờ" (huyền) chỗ tôi ra "cơ" (ngang) — nhưng chưa tìm
   được luật nào suy ra thanh từ âm tiếng Anh.
3. **Chưa có danh sách vần hợp lệ.** Bộ kiểm chỉ xét phụ âm đầu và ký tự cuối, nên một vần
   hiếm vẫn lọt. Luật 6 chặn được lớp lỗi lớn nhất ("ấyt", "oít") nhưng không phải tất cả.
4. **Nguyên âm đôi mất khi có phụ âm cuối.** `Light` ra "Lát", `House` ra "Hát" — luật 6 bỏ
   bán nguyên âm để giữ phụ âm cuối. Hướng ngược lại (giữ nguyên âm đôi, bỏ phụ âm cuối:
   "Lai", "Hao") cũng là cách người Việt hay đọc. Chưa có cơ sở để chọn bên nào.

---

# Tên riêng đi nhầm đường: 35/189 cách đọc đã khoá vi phạm chính luật của project

Ngày 2026-09-02. Phát hiện khi truy 9 segment fail của alpha.22, không phải khi đọc code.

## Triệu chứng

Bốn segment bị chặn vì ASR không khớp tên riêng, dù nội dung câu khớp 72–83%. Câu hỏi ban
đầu là "cổng ASR có quá nghiêm không". Câu trả lời hoá ra ngược lại: **tên bị đọc sai
thật**.

| tên | đang đọc | cụm phụ âm không tồn tại trong tiếng Việt |
|---|---|---|
| `Samael Kaizer Theosbane` | `Xa-men-cai-dên-thêô-xba-nê` | **xb** |
| `Juliana Vox Blade` | `Giu-lia-na-vốc-bla-đê` | **bl** |
| `Oldest Death` | `Ô-lđết-đít` | **lđ** |
| `Dawn's Scourge` | `Đau-ét-xcao-rgê` | **xc**, **rg** |

Đo trên toàn bộ DB của mọi phiên bản: **189 mục phiên âm khác mặt chữ, 35 mục (18,5%)
không qua nổi `_valid_vietnamese_spoken_form` — chính hàm kiểm tra của project.** Tất cả
đều `locked=1`, tức bất biến, tồn tại xuyên các run.

## Nguyên nhân gốc: CMUdict tra theo **từ**, project tra theo **cả cụm**

`_cmu_pronunciations()` nhận cả `"Eagle Eyes"` làm khoá. Từ điển không bao giờ có cụm, nên
**mọi tên nhiều từ đều trượt** khỏi đường âm vị và rơi xuống đường mặt chữ
(`_local_name_fallback`) — đường này làm việc từ **chữ viết**, nên:

- không biết 'e' câm: `Zone` → `Dô-nê`, `Safe` → `Xa-phê`
- không tách cụm phụ âm đầu: `Blade` → `Bla-đê`

Trong khi đường âm vị **đã có sẵn** toàn bộ máy móc cần thiết và cho kết quả trùng khít
ví dụ người nghe đưa: `Herald` → `He-rồ`, `Death` → `Đét`, `Seed` → `Xít`, `King` → `Kinh`.

## Bốn lỗi tìm được, mỗi lỗi một cơ chế riêng

### 1. `_local_name_fallback` khoá thẳng, không qua cổng kiểm tra

Đường LLM có kiểm `_valid_vietnamese_spoken_form` rồi mới khoá, và có bước sửa ranh giới
âm tiết nếu trượt. Đường fallback cục bộ **không có gì cả** — nó chỉ kiểm mẫu chính tả và
ký tự cuối, **không kiểm phụ âm đầu**. Toàn bộ 35 mục hỏng đi qua đây.

### 2. `VIETNAMESE_SYLLABLE_ONSETS` thiếu chữ "đ"

Bảng có "d" nhưng không có "đ". Hai hàm đọc bảng này theo hai cách khác nhau:

- `_valid_vietnamese_spoken_form` chuẩn hoá đ→d **trước** khi so → nó thấy "dr", từ chối đúng
- `_split_illegal_onset` so chuỗi thô → nó thấy "đr", không tìm được đầu hợp lệ để tách,
  **bỏ cuộc và trả về nguyên cụm**

Nên `Dragon` giữ nguyên "đr", rồi bị chính bộ kiểm tra từ chối — bộ tách từ chối sửa đúng
thứ mà bộ kiểm tra từ chối nhận.

### 3. R trước phụ âm bị coi là âm đầu

`_arpabet_syllables` chỉ đẩy phụ âm giữa hai nguyên âm xuống âm cuối nếu nó nằm trong
`ARPABET_CODAS`. R **không** nằm trong bảng đó (vì luật là bỏ R), nên R bị để lại làm âm
đầu của âm tiết sau, tạo cụm "rth", "rt", "rd". Bộ tách cụm khi đó chèn "ơ" và **đẻ ra một
âm tiết mà từ gốc không có**:

| từ | trước | sau |
|---|---|---|
| Arthur | `A-rơ-thơ` | `A-thơ` |
| Portals | `Po-rơ-tồ` | `Po-tồ` |
| Guardians | `Ga-rơ-đi-ân` | `Ga-đi-ân` |
| Supporter | `Xơ-po-rơ-tơ` | `Xơ-po-tơ` |
| Market | `Ma-rơ-cớt` | `Ma-cớt` |

Luật đúng hẹp: R **trước phụ âm** là âm cuối; R **trước nguyên âm** vẫn là âm đầu, nên
`Herald` giữ nguyên `He-rồ` đúng như người nghe đọc.

### 4. Luật "r + d cuối → -c" được viết trong comment nhưng không có code

Bảng `ARPABET_CODAS` có comment: *"After an r-coloured vowel a final d backs to -c: card is
read cạc, not cát."* Không hàm nào thực hiện. Kết quả `Card` → `Cát` — sai phụ âm cuối, và
người nghe đã nói rõ "card đọc là **cạc**". Bằng chứng ủng hộ luật rất chắc: hai từ mượn có
thật trong tiếng Việt đều đúng khuôn AA/AO + R + D — *card* → "cạc", *guard* → "gác".

Luật chỉ bắn khi R **thật sự nằm trong âm cuối**, nên `Bird`, `Third`, `Word` (dùng nguyên
âm ER, không có âm R riêng) không bị đụng.

## Kết quả đo

Tra theo từng từ + ba sửa lỗi trên: **22/28 tên hỏng được chữa dứt điểm**, tất cả hợp lệ.

| tên | trước | sau |
|---|---|---|
| Eagle Eyes | `I-glê-ếiêt` | `I-gồ Át` |
| Oldest Death | `Ô-lđết-đít` | `Ôn-đớt Đét` |
| Juliana Vox Blade | `Giu-lia-na-vốc-bla-đê` | `Giu-li-e-nơ Vát Bơ-lất` |
| Dawn's Scourge | `Đau-ét-xcao-rgê` | `Đon Xớch` |
| Western Safe-Zone | `Uê-xtên-xa-phê-dô-nê` | `Uét-tơn Xấp Dôn` |
| Crippling Hex | `Crip-pling-hêc` | `Cơ-ri-pơ-linh Hét` |

Định dạng theo đúng cách người nghe viết: **gạch nối giữa âm tiết, dấu cách giữa từ** —
`he-rồ ọp âu-đít đét`.

Sáu tên còn lại thiếu từ trong CMUdict: `Samael`, `Kaizer`, `Theosbane`, `Soulbound`,
`Elderwing`, `Godswill`. Bốn trong sáu là **từ ghép của các từ có trong từ điển**
(Soul+bound, Elder+wing, God+will, và `bane` → "Bên" đúng bằng mục tiêu `theo-bên`).

## Còn hở sau lần này

1. **35 mục đã khoá vẫn hỏng.** Sửa bộ sinh không sửa được dữ liệu đã khoá; cần một lượt
   sửa lại có đọc-lại kiểm chứng, giống `set_listener_pronunciation()`.
2. **Fallback vẫn đọc theo chữ viết, và luật 'e' câm đã thử — chưa dùng được.**
   Đo trước khi làm, và may là có đo. Bỏ 'e' cuối từ sau phụ âm cải thiện `Zone` → `Dôn`,
   `Safe` → `Xáp`, `Gate` → `Gát`, `Theosbane` → `Thêô-xơ-ban` (gần `theo-bên` hơn hẳn),
   nhưng **làm hỏng nặng** những từ khác vì nó làm lộ ra phụ âm cuối mà bảng âm cuối của
   đường mặt chữ không ánh xạ được, và phụ âm đó bị **ném đi im lặng**:

   | từ | chỉ vá onset | + bỏ 'e' câm |
   |---|---|---|
   | Blade | `Bơ-la-đê` | `Bơ-la` — mất /d/ |
   | Cable | `Ca-bơ-lê` | `Ca` — mất cả hai |
   | Eagle | `I-gơ-lê` | `Íc` |
   | Incredible | `In-cơ-rê-đi-bơ-lê` | `In-cơ-rê-đi` |

   Đây chính là lớp lỗi mà test `test_the_final_consonant_is_never_simply_lost` canh cho
   đường âm vị. Phải làm đầy `_latin_name_coda_reading` **trước**, rồi mới bỏ 'e' câm.
3. **Tách từ ghép chưa làm.** Chỉ nên tách khi có **đúng một** cách tách mà cả hai nửa đều
   có trong từ điển — `Godswill` có hai cách (god+swill, gods+will) nên phải để LLM lo.

---

# Kiểm định trên toàn corpus: 915 chương, 1.495 từ tiếng Anh

Trước lần này bộ luật chỉ được thử trên vài chục ví dụ chọn tay. Người nghe yêu cầu thử
trên chính văn bản sách. Kết quả đổi hai quyết định và huỷ một tính năng.

## Cách tách từ tiếng Anh ra khỏi văn bản tiếng Việt

Không thể chỉ dựa vào "có trong CMUdict" — `ra`, `cho`, `sao`, `tay`, `theo`, `tin`, `gian`
đều là từ tiếng Việt **và** có trong CMUdict. Phép thử đúng là ngược lại: **một token có
phải âm tiết tiếng Việt hợp lệ không**.

Viết bộ nhận dạng âm tiết tiếng Việt (âm đầu + vần + âm cuối, có luật -nh/-ch sau i/ê).
Kiểm trên 38 từ: **38/38 đúng**. Từ duy nhất từng lọt là `King` — vì tiếng Việt viết /ŋ/ sau
i là **-nh**, nên "king" không phải chính tả tiếng Việt hợp lệ, "kinh" mới là.

Kết quả trên 11 triệu ký tự: **1.495 từ tiếng Anh khác nhau, 80.663 lượt xuất hiện**;
882 từ có trong CMUdict, 613 không.

## Kết quả: 882/882 hợp lệ, 0 lỗi

Không một từ nào trong sách làm bộ chuyển đổi sinh ra âm tiết tiếng Việt không hợp lệ, và
không từ nào làm nó ném lỗi. Đường âm vị vững.

Nhưng danh sách "mất phụ âm cuối" lộ ra hai lỗi thật.

### Lỗi 1: luật /l/ tự thành âm tiết không phân biệt trọng âm

`Gulf` → `Gồ`, trong khi `Golf` — **cùng vần** — → `Gôn`.

Luật "âm /l/ tự thành âm tiết" (Michael → "Mai-cồ") kiểm `vowel in {"AH","AX"}`. Nhưng
`_arpabet_phones` chỉ đổi tên **AH không nhấn** thành AX; **AH có nhấn là /ʌ/ đầy đủ**, mang
một /l/ bình thường phía sau, không phải /l/ tự thành âm tiết. Gộp hai thứ làm một thì
**nuốt mất phụ âm cuối** của cả lớp từ:

| từ | trước | sau |
|---|---|---|
| Gulf | `Gồ` | `Gân` |
| Bulk | `Bồ` | `Ban` → `Bân` |
| Result | `Ri-dồ` | `Ri-dân` |
| Adult | `Ơ-đồ` | `Ơ-đân` |
| Hull | `Hồ` | `Hân` |

Nhóm đối chứng (schwa thật) không đổi: `Michael`→`Mai-cồ`, `Cable`→`Cây-bồ`,
`Incredible`→`In-cơ-re-đơ-bồ`, `Herald`→`He-rồ`.

### Lỗi 2: nguyên âm phản ứng với **âm vị**, đáng lẽ với **chữ được viết ra**

Có luật `AA + N → ô` (nên `John`→`Giôn`, `Dawn`→`Đon`). `Golf` trượt luật đó vì âm cuối của
nó là **L**; chỉ *sau này* L mới được viết thành "n" theo luật "âm vang thắng âm cản". Nên
`Golf` ra `Gan`, dù tài liệu và tiếng Việt đời thường đều đọc là **"gôn"**.

Sửa: xét **chữ cái thực sự sẽ được viết**, không xét âm vị nguồn. 10/882 từ đổi, tất cả tốt lên:

| từ | trước | sau |
|---|---|---|
| Golf | `Gan` | `Gôn` |
| Rudolf | `Ru-đan` | `Ru-đôn` |
| Waldo | `Uan-đô` | `Uôn-đô` |
| Sol | `Xan` | `Xôn` |
| Ulrich | `An-rích` | `Ân-rích` |

## Kết quả âm: tách từ ghép — đã làm, đã đo, đã gỡ

Ý tưởng: tên từ điển không có vẫn có thể là **hai từ nó có** — `Soulbound` = Soul+bound,
`Elderwing` = Elder+wing. Chạy thử: đúng đẹp trên 7/7 từ ghép thật (`Nightfall`→`Nát-phon`,
`Shadowbane`→`Se-đô-bân`, `Ironheart`→`Ai-ơn-hát`), và tự từ chối khi mơ hồ (`Godswill` tách
được hai kiểu).

**Nhưng corpus thật giết nó.** Sách đầy tên bịa kiểu Latinh, và chúng cũng có "đúng một cách
tách":

| tên | bị tách thành | ra |
|---|---|---|
| `Carina` | car + ina | `Ca-i-nơ` |
| `Alterna` | alter + na | `Ôn-ơ-nơ` |
| `Iristine` | iris + tine | `Ai-rớt-tan` |
| `Maltimus` | malt + imus | `Mon-ai-mớt` |
| `Florencia` | flor + encia | `Phơ-lo-rân-xi-ai-ây` |

Nâng ngưỡng độ dài mỗi nửa lên 4 giảm từ 144 xuống 35 ca bắn nhầm nhưng vẫn còn
`Iristine`, `Maltimus`; ngưỡng 5 thì giết luôn cả 7 từ ghép thật.

**Lợi 2 tên, hại 35 tên. Gỡ.** Không có tín hiệu nào phân biệt được từ ghép tiếng Anh thật
với tên bịa gốc Latinh, và fallback vốn đã cho kết quả hợp lệ cho tất cả chúng.

Đây chính là lý do phải thử trên corpus: bộ 7 ví dụ tự chọn nói tính năng này hoàn hảo.

## Hở mới tìm được, chưa sửa

1. **Số La Mã chỉ ngôi thứ.** `Benedict III` xuất hiện **164 lần**, `Henry VIII` cũng có.
   Project **không có xử lý số La Mã nào**. Phải đọc "Bê-nê-đích **Đệ Tam**", hiện tại rơi
   vào đường phiên âm tên tiếng Anh và ra `Iii`.
2. **Bộ quét tên nhận cả tiếng kêu.** `_is_proper_latin_name_surface("Uuuuu")` trả về True,
   trong khi `is_vocalization_only("Uuuuu")` trả về True — **bộ quét tên không hỏi bộ nhận
   diện tiếng kêu**. Cùng họ lỗi với "Argh" bị khoá thành phiên âm tên ở đường ASR.

---

# Kiểm định trên nguồn ngoài: 37.000 từ tải từ mạng

Người nghe yêu cầu thử với từ và tên tiếng Anh phổ biến lấy từ mạng, không chỉ từ trong sách.

| nguồn | số từ | hợp lệ | không hợp lệ | ném lỗi |
|---|---|---|---|---|
| 10.000 từ tiếng Anh thông dụng nhất | 10.000 | 9.096 | **0** | **0** |
| 4.945 tên riêng | 4.921 | 2.709 | **0** | **0** |
| 21.985 họ | 21.933 | 12.263 | **0** | **0** |
| 157 thuật ngữ LitRPG (`dungeon`, `mana`, `buff`…) | 157 | 157 | **0** | **0** |

**24.225 từ, không một cách đọc nào không hợp lệ, không một lần ném lỗi.** Phần còn lại là
từ CMUdict không có (12.039), rơi xuống đường mặt chữ — đường này sau khi vá cũng không còn
sinh ra kết quả không hợp lệ.

Vài cách đọc thuật ngữ: `dungeon`→`Đân-giân`, `dragon`→`Đơ-re-gân`, `zombie`→`Dam-bi`,
`vampire`→`Vem-pai`, `blade`→`Bơ-lất`, `gold`→`Gôn`, `portal`→`Po-tồ`.

## "Từ tiếng Anh nào đã có dạng một từ tiếng Việt rồi thì thôi"

Yêu cầu trực tiếp của người nghe, ví dụ họ đưa là **may**. Cơ chế cũ cho việc này là
`CMUDICT_CONTEXT_ONLY`, chứa **đúng một từ**: `"may"`. Cộng thêm `NAME_CANDIDATE_EXCLUSIONS`
viết tay thì phủ được **28 trong 366** từ như vậy trong 10.000 từ thông dụng nhất.

Thay bằng luật: **một token đã là âm tiết tiếng Việt hợp lệ thì không phải tên tiếng Anh.**

### Bộ nhận dạng âm tiết tiếng Việt

Âm đầu (dùng lại `VIETNAMESE_SYLLABLE_ONSETS`) + vần + âm cuối, cộng luật chính tả -nh/-ch.
Hai chi tiết quyết định độ chính xác, cả hai đều tìm ra bằng đo:

1. **Chỉ bỏ 5 dấu thanh, giữ 3 dấu chất lượng nguyên âm.** Bản đầu bỏ cả breve/circumflex/horn,
   nên `nhiên`→`nhien` và không còn giống âm tiết nào. Sai 4,14%.
2. **Luật -nh/-ch chỉ áp dụng sau i, ê ĐƠN.** Nguyên âm đôi `iê` giữ cách viết -ng/-c: vừa
   `kinh` vừa `tiếng` đều đúng, còn `king` thì không. Sai 1,18% → **0,40%**.

Kiểm trên **6.282 token có dấu** (chắc chắn là tiếng Việt, 2.064.345 lượt) trong sách:
**nhận đúng 99,6%**. 25 ca từ chối còn lại đều **không phải âm tiết đơn** (`urê`, `nitơ`) hoặc
mang dấu nước ngoài (`Dvořák`, `Schrödinger`) — từ chối đúng.

### Tác động: chỉ loại nhầm lẫn, không mất gì

Trên **129 tên từng được khoá** qua mọi phiên bản, luật mới loại **đúng 2** — và cả hai đều là
**tiếng Việt bị nhận nhầm thành tên tiếng Anh**: `'Con Hoang'` và `'SAU KHI'`.

## Câu hỏi chưa trả lời được: tên quốc tế không phải tên tiếng Anh

Chấm đường mặt chữ bằng đường âm vị làm đáp án trên 882 từ: **chỉ khớp 8,8%**. Nhìn kỹ thì
không phải đường nào cũng sai — chúng đúng cho **hai lớp từ khác nhau**:

| từ | đường âm vị (đang dùng) | đường mặt chữ |
|---|---|---|
| `Natasha` | `Nơ-ta-sơ` | `Na-ta-sa` |
| `Sophia` | `Xô-phi-ơ` | `Xô-phia` |
| `Katrina` | `Cớt-ri-nơ` | `Cát-ri-na` |
| `Fernando` | `Phơ-nen-đô` | `Phê-rơ-nan-đô` |
| `arcana` | `A-ce-nơ` | `A-rơ-ca-na` |

Đây **không phải từ tiếng Anh**. Tiếng Việt mượn tên quốc tế theo **mặt chữ Latinh**, không
qua phát âm tiếng Anh — "Na-ta-sa", "Xô-phi-a". CMUdict có chúng, nhưng nó ghi *người Anh đọc
thế nào*, không phải *người Việt viết thế nào*.

Ngược lại, với từ và tên **tiếng Anh thật** (`Herald`, `Death`, `Seed`, `King`, `Blade`),
đường âm vị đúng và khớp đúng ví dụ người nghe đưa.

Quy mô: trong 832 từ tiếng Anh của sách, **655 luôn viết hoa** (tên riêng, 57.536 lượt) và
177 có xuất hiện chữ thường (từ thường, 6.028 lượt). Chưa có cách tự động phân biệt "tên
tiếng Anh" với "tên quốc tế viết bằng chữ Latinh" — **cần tai người nghe quyết định.**

---

# Nguyên âm bám mặt chữ: từ 4/24 lên 10/24 trên chính cách đọc người nghe viết ra

Người nghe đưa 9 cách đọc mẫu mới, cộng với 15 mẫu trước đó thành **bộ đề 24 từ**. Chấm bộ
luật cũ trên đó: **4/24 đúng hoàn toàn, 5/24 đúng nếu bỏ thanh, 23/24 đúng số âm tiết.**

Cấu trúc âm tiết gần như luôn đúng. Cái sai là **nguyên âm**.

## Khuôn: chữ cái quyết định, phát âm chỉ chọn giá trị

| từ | luật cũ (theo âm vị) | người nghe viết | chữ trong mặt chữ |
|---|---|---|---|
| dragon | `Đơ-re-gân` | `đờ-ra-gon` | a, o |
| zombie | `Dam-bi` | `dom-bi` | o |
| vampire | `Vem-pai` | `vam-pai` | a |
| natasha | `Nơ-ta-sơ` | `na-ta-sa` | a, a, a |
| sophia | `Xô-phi-ơ` | `xô-phi-a` | o, i, a |
| katrina | `Cớt-ri-nơ` | `ca-tri-na` | a, i, a |
| benedict | `Be-nơ-đít` | `be-nơ-đích` | e, e, i |

Luật cũ đọc theo **âm vị**: schwa luôn ra "ơ", AE luôn ra "e", AA luôn ra "a". Người nghe
đọc theo **chữ**: schwa viết `a` thành "a", viết `e` thành "ơ"; AE viết `a` thành "a".

Điều này khớp đúng lời họ nói từ đầu: *"viết các phiên âm của nó như là một đứa trẻ tập đọc
tiếng anh viết ra"*. Một đứa trẻ đọc theo chữ.

## Ghép chữ ↔ âm vị

CMUdict không cho biết chữ nào ứng với âm vị nào. Nhưng với tên riêng, sau khi bỏ 'e' câm
thì gần như luôn là **một nhóm nguyên âm ứng một âm vị nguyên âm**.

Hai chi tiết cần thiết, cả hai đều tìm ra bằng đo:

1. **`-le` giữ 'e'**: /l/ tự thành âm tiết có âm vị riêng, nên `incredible` phải giữ.
2. **`-es` bỏ 'e'**: `James` viết 2 nguyên âm nhưng đọc 1; đếm 2 làm hỏng phép ghép và cách
   đọc rơi về bảng âm vị, ra `Giâm` thay vì `Giêm`.

Kết quả: **21/21 trên bộ đề, 95,8% trên 882 từ tiếng Anh của sách.** Từ nào không ghép được
thì rơi về bảng âm vị cũ — không từ chối đọc.

## Bảng

| chữ | AA | AE | AH/schwa | EY | ER | OW | UH | IY/IH | AY | UW |
|---|---|---|---|---|---|---|---|---|---|---|
| **a** | a | a | a | ê | | | | | | |
| **o** | o | | o | | | ô | ô | | | |
| **e** | | | ơ | | ơ | | | i | | |
| **i** | | | i | | | | | i | ai | |
| **u** | | | ă | | | | | | | u |

Cộng `ee`→i, `ea`→e, `ie`→i, `eo`→ơ.

## Thanh của âm tiết chèn: huyền

Mọi lần người nghe viết một âm tiết chèn, nó mang thanh **huyền**: `in-cờ-ri-đi-bồ`,
`đờ-ra-gon`, `bờ-lết`. Không có ngoại lệ nào. Đó là âm tiết yếu vốn không có trong từ.

## Hai chỗ ví dụ của người nghe tự mâu thuẫn — lấy đa số

- `e`+EH → "e" ở *death*, *benedict*, *herald* nhưng "i" ở *incredible* → chọn **"e"** (3–1)
- `e`+schwa → "ơ" ở *benedict* nhưng "i" ở *oldest* → chọn **"ơ"** (đúng bản chất schwa)

Người nghe đã nói: *"bạn tìm được bộ luật tốt nhất quán nhất thì là tốt nhất"*.

## Một luật đã thử rồi bỏ

`oldest` → `âu-đít` cho thấy OW nhấn nên ra "âu". Nhưng luật "bỏ bán nguyên âm khi có phụ âm
cuối" rút "âu" thành "â", nên `Ôn-đớt` biến thành `Ân-đớt` — **xấu đi**. Mẫu `âu-đít` thật ra
đòi **bỏ hẳn /l/ để giữ nguyên âm đôi**, tức lật một luật khác; chỉ có 1 ví dụ nên chưa lật.

## Kết quả

| | đúng hoàn toàn | đúng bỏ thanh | đúng số âm tiết |
|---|---|---|---|
| trước | 4/24 | 5/24 | 23/24 |
| sau | **10/24** | **12/24** | 23/24 |

Không cách đọc nào xấu đi. Kiểm định hợp lệ giữ nguyên: **0 không hợp lệ** trên 24.061 từ
nguồn ngoài và 879/879 từ tiếng Anh của sách.

Ba luật đổi kéo theo cách đọc tốt hơn ngoài bộ đề: `Noah` → `Nô-a` (trước `Nô-ơ`) đúng chính
tả tiếng Việt của tên đó; `game` → `Gêm`, `name` → `Nêm` đúng cách người Việt vẫn đọc.

## Kết quả âm: chữ cái đọc rời không làm lệch thước đo nhịp

Segment `'... như sau: C » B » A » S » SS » SSS.'` fail vì nhịp 9,36 ký tự/giây. Giả thuyết:
chữ cái đọc thành tên chữ ("xê", "bê", "ét-xì") tốn thời gian gấp mấy lần số ký tự của nó,
nên thước đo thiên vị.

Đo trên 3008 segment có audio: nhịp trung vị của segment **có** chữ cái đứng riêng là
**16,17**, của segment **không có** là **15,55** — cao hơn, không thấp hơn. Không có thiên
lệch hệ thống. Đây là ca cá biệt, không phải lớp lỗi; không xây bộ hiệu chỉnh cho nó.

---

# Bảy luật rút ra từ 92 cách đọc mẫu: 42 → 72/92

Người nghe đưa thêm 40 cách đọc và nói rõ: *"bạn phải tự tìm quy luật đáp ứng tất cả ví dụ
tôi đưa"*, và *"luật thiết kế theo bảng ipa tiếng anh"*. Mỗi chỗ tưởng là mâu thuẫn đều hoá
ra có điều kiện phân biệt.

Bộ đề: **92 từ**, gồm mọi cách đọc người nghe từng viết cộng những cách họ xác nhận là đúng.

## 1. Thanh sắc hay nặng: phụ âm cuối đã dịch chuyển bao xa

| | phụ âm cuối | viết thành | thanh |
|---|---|---|---|
| `card` /kɑːd/ | /d/ **kêu** | **-c** | **nặng** — cạc |
| `of` /ʌv/ | /v/ **kêu** | **-p** | **nặng** — ọp |
| `seed`, `blade` | /d/ kêu | -t, đúng vị trí của nó | sắc |
| `box`, `cat`, `death`, `desk`, `top` | điếc | bất kỳ | sắc |

Một phụ âm kêu phải viết thành -c hoặc -p là đã đi xa hơn một phụ âm kêu rơi đúng vào -t.
**Khớp cả 24 ví dụ có âm tiết đóng.** Kéo theo `guard`→`Gạc`, `mag`→`Mạc`, `bag`→`Bạc`.

## 2. Nguyên âm ngắn trước phụ âm điếc

`house`, `mouse` (trước /s/ điếc) → "h**au**", "m**au**"; `sound` (trước /nd/ kêu) → "s**ao**".

Đây là *pre-fortis clipping*, hiện tượng có thật của tiếng Anh, và tiếng Việt phân biệt đúng
cặp đó: "au" ngắn, "ao" dài.

## 3. Schwa trước âm mũi mở thành "e"

`carmen` ca-**men**, `elena` e-**le**-na (trước /m/, /n/) vs `benedict` be-**nơ**-đích (trước
/d/). Âm mũi giữ schwa mở.

## 4. /oʊ/ có trọng âm, âm tiết mở, âm tiết sau bắt đầu bằng phụ âm → "o"

| | | |
|---|---|---|
| `tony` | nhấn, mở, sau là /n/ | **to**-ni |
| `sophia` | **không** nhấn | x**ô**-phi-a |
| `oldest` | có phụ âm cuối | **ôn**-đít |
| `noah` | âm tiết sau bắt đầu bằng nguyên âm | n**ô**-a |

Khớp cả 4, mỗi ca rơi vào một nhánh khác nhau.

## 5. /ʌ/ trước âm mũi là "ă"

`month` m**ăn**, `dungeon` đ**ăng**-giừng. Còn `of` (trước /v/) giữ "**ọ**p".

## 6. /k/ cuối viết "ch", trừ khi có /s/ đứng ngay trước

| có /s/ trước /k/ → **-c** | không có → **-ch** |
|---|---|
| `mask` mác, `task` tác, `desk` đéc | `jack` dách, `action` ách-sừn, `text` tếch, `next` nếch |

Với `text`/`next` nguyên âm nâng theo: "-ech" không phải vần tiếng Việt, "-**ê**ch" thì phải.
Nguyên âm sau (o, u) không có vần -ch nên vẫn giữ -c: `box` bóc, `book` búc.

**Va chạm từ vựng:** luật này cho `Deck` → "**Đếch**", đúng luật nhưng là từ thô tục, và sách
viết "Bộ Thẻ (Deck)" **9 lần**. Đã đưa vào `ARPABET_PRONUNCIATION_OVERRIDES` với "Đéc". Đây
đúng là việc bảng ngoại lệ sinh ra để làm.

## 7. Nguyên âm đôi nhường chỗ cho âm tắc, không nhường cho âm xát

Người nghe nói thẳng: *"luật thiết kế theo bảng ipa tiếng anh"*.

| | phụ âm cuối | kết quả |
|---|---|---|
| `lake` /leɪk/ | /k/ **tắc** | l**ếch** — giữ phụ âm, nguyên âm đơn hoá |
| `blade` /bleɪd/ | /d/ **tắc** | bờ-l**ết** |
| `name` /neɪm/ | /m/ **mũi** | n**êm** |
| `space` /speɪs/ | /s/ **xát** | xờ-p**ây** — giữ nguyên âm đôi, bỏ phụ âm |

Và khi nguyên âm đôi **không có** nguyên âm đơn tiếng Việt cùng chất (ai, ao, oi) thì phụ âm
cuối luôn phải nhường: `light` **lai**, `house` **hau**, `sound` **sao**, `point` **poi**.

**Sai một lần rồi mới đúng:** bản đầu tôi viết "giữ phụ âm nếu là **âm tắc**", làm `name`→"Nây",
`game`→"Gây", `james`→"Giây" — vì /m/ là âm **mũi**, không phải âm tắc. Luật đúng phải phát
biểu theo cái **bị bỏ** (âm xát), không theo cái được giữ.

## 8. Hậu tố -est đọc "ít"

CMUdict ghi hậu tố so sánh nhất là `AH0 S T` cho **mọi** từ — biggest, fastest, largest,
oldest — nhưng IPA của nó là **/ɪst/**. Người nghe chỉ ra điều này ("oldest trong phiên âm ipa
thì là đít mà?"). Xử như hậu tố, giống -tion: `oldest`→`Ôn-đít`, `biggest`→`Bi-gít`. Từ chỉ
tình cờ kết thúc bằng những chữ đó thì không bị đụng: `west`→`Goét`, `best`→`Bét`.

## Kết quả

| | trước | sau |
|---|---|---|
| khớp hoàn toàn | 42/92 | **72/92** |
| khớp nếu bỏ thanh | 45/92 | **74/92** |
| đúng số âm tiết | 85/92 | **90/92** |

Kiểm định hợp lệ không đổi: **0 cách đọc không hợp lệ** trên 24.061 từ nguồn ngoài.

## Còn lại, và vì sao chưa sửa

- `william` guy-li-am, `water` goát-tờ, `charlie` chác-li, `fernando` phét-nan-đô — chia âm
  tiết khác, chưa tìm được điều kiện phân biệt.
- `world` **gua** bỏ hẳn /ld/ nhưng `win` **guyn** giữ /n/.
- `incredible` in-cờ-**ri**-đi-bồ — `e`+/ɛ/ ra "i", ngược với death/benedict/herald ra "e" (3–1).
- `sound` "**s**ao" và `sky` "xờ-**k**ai" — chỉ khác chính tả, "s"/"x" và "c"/"k" đọc như nhau.
- `samael`, `kaizer`, `theosbane` — không có trong CMUdict, đi đường mặt chữ, chưa động tới.

---

# Bộ đối chiếu thứ hai: từ mượn tiếng Việt đã có sẵn

Người nghe chỉ ra điều lẽ ra phải làm từ đầu: *"bạn thực sự biết cách người việt đọc các từ
tiếng anh? đó chính là mục tiêu của tôi, sao bạn không tự áp dụng mục tiêu đó cho thuật toán
mà cứ phải hỏi tôi cách đọc hả?"*

Đúng. Tiếng Việt đã mượn hàng loạt từ tiếng Anh và có cách đọc quen thuộc — `mác-két`,
`in-tơ-nét`, `láp-tóp`, `phây-búc`, `ten-nít`. Đó là bộ đối chiếu tự có, không cần hỏi ai.

Nằm ở `tests/data_vietnamese_loanwords.py`.

## Lọc mới là phần quan trọng

Rất nhiều "từ tiếng Anh" trong tiếng Việt thực ra vào qua **tiếng Pháp hoặc Latin khoa học**,
và chúng theo phát âm nguồn đó chứ không theo tiếng Anh. Để lẫn vào là kéo bộ luật đi sai:

`ga-ra` (garage) · `cà phê` (café) · `vắc-xin` (vaccin) · `xà phòng` (savon) · `sâm banh`
(champagne) · `cà vạt` (cravate) · `xăng` (essence) · `bơ` (beurre) · `ga` (gare) · `pin`
(pile) · `sếp` (chef) · `xì gà` (cigare) · `vi-ta-min` · `vi-rút` · `vi-đi-ô` · `sa-lát` ·
`me-nu` · `mo-đen` · `pi-da` (Ý) · `tua` (tour) · `ba` (bar)

Còn lại **41 từ vào thẳng từ tiếng Anh**.

Cũng cho **"s" và "x" là tương đương** khi chấm: giọng Bắc đọc hai chữ này như nhau, nên
chênh lệch đó không đổi âm thanh nào người nghe nghe được.

## Bộ này tự bắt được lỗi mà 138 ví dụ của người nghe không bắt được

`style` ra **`Xờ-taiu`**. "aiu" không phải vần tiếng Việt: luật /l/ tối hoá bán nguyên âm
đang áp lên một nguyên âm **đã có** bán nguyên âm. Và bộ kiểm tra vẫn cho qua — nó xét âm
đầu và ký tự cuối, **chưa bao giờ xét vần**. Đây là lỗ hổng đã ghi trong mục "còn hở" từ
trước, và phải có bộ đối chiếu mới lộ ra.

## Ba luật rút từ bộ này

1. **Âm tắc-xát cuối từ đọc -t**: `match`→mát, `research`→ri-xớt, `scourge`→xờ-cớt. Có R
   đứng trước thì giữ -ch, đúng bằng `george`→gióch.
2. **Từ viết kết thúc bằng "w" giữ trọn nguyên âm đôi**: `show`→sâu, `shadow`→sa-đâu. Kết
   thúc bằng "o" thì không: `antonio`→an-to-ni-ô. Lại là mặt chữ phân biệt.
3. **Schwa /ər/ có ba nhánh**, và chính từ mượn cho biết nhánh nào:
   - có trọng âm → đọc theo chữ: `server`→**xe**-vờ
   - không trọng âm, **giữa từ** → "ơ" ngang: `internet`→in-**tơ**-nét
   - không trọng âm, **cuối từ** → "ờ" huyền: `number`→năm-**bờ**

   Nhánh thứ ba là của người nghe, và họ giải thích bằng trọng âm: *"mon tờ có thanh huyền
   bởi vì trọng âm trong từ nữa"*. Hoá ra nó **cùng một luật** với thanh huyền của âm tiết
   chèn (`đờ-ra-gon`, `xờ-kiu`), không phải hai luật riêng.

## Kết quả âm: không nhân đôi phụ âm giữa hai nguyên âm

Từ mượn thật hay nhân đôi phụ âm: `mác-két`, `cóp-pi`, `ten-nít`, `tắc-xi` — phụ âm vừa
đóng âm tiết trước vừa mở âm tiết sau. Thử tìm luật cho nó (nguyên âm ngắn + âm tiết mở +
phụ âm đơn phía sau), nhưng **chính ví dụ của người nghe bác bỏ**: `natasha`→"na-ta-sa" và
`business`→"bi-xì-nít" đều rơi đúng vào khuôn đó mà không nhân đôi. Không làm.

## Một chỗ hai nguồn nói ngược nhau, và đã chọn

Từ mượn có sẵn dùng thanh **ngang** cho đuôi -er cuối từ (`pốt-tơ`), người nghe viết
**huyền** (`năm-bờ`, `mon-tờ`, `com-piu-tờ`, `cai-dờ`, `goa-ri-ờ`, `pích-trờ`, `đóc-tờ`,
`goa-tờ`, `bờ-ro-dờ` — chín từ). Theo người nghe: họ là người nghe cuốn sách này. Họ cũng
nói `pốt-tơ` "cũng đúng và hay hơn", nên đây là biến thể chấp nhận được chứ không phải lỗi.

| | trước vòng này | sau |
|---|---|---|
| khớp 138 cách đọc của người nghe | 73 | **84** |
| khớp 41 từ mượn có sẵn | 23 | **28** |
| cách đọc không hợp lệ | 0 | **0** |

## Năm lỗi ASR còn lại của alpha.25 không phải lỗi chuyển tự (điều tra 2026-09-03)

Tồn đọng ghi "bốn lỗi `ASR_LOCKED_NAME_ANCHOR_MISMATCH`, đều là câu có thuật ngữ tiếng Anh
trong ngoặc". Thực tế là **năm** segment, và nguyên nhân không phải chỗ người ta tưởng.

| giọng đọc | Whisper nghe ra |
|---|---|
| Xờ-pi-rít E-xen Du-nít | `S.P.Z.E.S.N.U.N.I.T.` |
| Ten Đe-mon Pờ-rin | tên **Demon Perrin** |
| Xa-ma-eo Cai-dơ Thê-ô-xờ-ben | Samenkai giờ theo Oserban |
| Ju-li-a-na Vóc Bờ-lết | Juliana **Vogtberlitz** |
| Đon Xờ-cớt | đon sờ cướp |

**Bản đọc đều đúng.** Đã kiểm tra bảng `pronunciations` thật của alpha.25: cả năm cụm đều
đã được đăng ký và chuyển tự chuẩn - `Skill Card → Xờ-kiu Cạc`,
`Spirit Essence Units → Xờ-pi-rít E-xen Du-nít`, `Tenth Demon Prince → Ten Đe-mon Pờ-rin`,
`Dawn's Scourge → Đon Xờ-cớt`. Bộ quét ứng viên tìm ra cả bốn cụm trong ngoặc; máy chuyển
tự đọc được cả bốn. Không có khâu nào của đường tiếng Anh → tiếng Việt hỏng ở đây.

Cái hỏng là **Whisper**, và nó hỏng theo hai kiểu:
- đánh vần thành chữ cái (`S.P.Z.E.S...`);
- **viết lại bằng chính tả tiếng Anh gốc** ("Demon Perrin", "Vogtberlitz") - tức là model
  đa ngữ nghe ra tiếng Anh trong giọng đọc tiếng Việt.

Kiểu thứ hai thoạt nhìn tưởng sửa được: nếu chấp nhận cả chính tả gốc thì ba ca sẽ qua.
Nhưng `_locked_name_anchor_forms` **đã** chấp nhận `source_spelling` từ trước rồi; Whisper
chỉ không ghi ra đủ sạch để khớp - "tên Demon Perrin" không phải "tenth demon prince".

Nới lỏng thành khớp mờ chính là thứ hàm này nói rõ nó từ chối làm: *"Require exact
locked-name forms in an ASR transcript without fuzzy aliases."* Sự nghiêm ngặt ấy tồn tại
để một cái tên đọc sai không lọt qua nhờ giống mang máng một cái tên khác. Đánh đổi nó để
lấy năm segment trên 948 (0,5%) là bán đúng thứ đang bảo vệ chín trăm segment còn lại.

**Kết luận: không sửa.** Đây là cái giá đã thiết kế của việc kiểm tra tên nghiêm ngặt, chứ
không phải khiếm khuyết. Ai định mở lại chuyện này thì phải trả lời được: làm sao phân biệt
"Whisper nghe đúng nhưng viết khác" với "giọng đọc sai" khi cả hai đều cho một bản ghi lệch?

Một khiếm khuyết thật thì bảng đó có lộ ra: `Debuff Card → Debuff Card`, không hề chuyển.
Đã sửa từ trước trong phiên này (quy tắc `must_convert`); code hiện tại cho `Đê-búp Cạc`.

## Vì sao chương hỏng: đã điều tra, và bộ phân xử neo tên **đúng** (alpha.32, 2026-09-03)

Cả hai chương hỏng đầu tiên của alpha.32 đều hỏng vì `ASR_LOCKED_NAME_ANCHOR_MISMATCH` trên
câu có ngoặc tiếng Anh, trong khi năm câu **cùng dạng** khác chỉ bị `..._REVIEW` (được phép
xuất bản). Trông như luật hạ cấp tuỳ tiện, nhất là vì:

| segment | trạng thái | similarity tổng | neo |
|---|---|---|---|
| `c00003_s0000029` | **hỏng** | **0,913** | 0/1 |
| `c00003_s0000030` | cảnh báo | 0,875 | 0/1 |

Bằng chứng *tốt hơn* mà kết cục *xấu hơn*. Cả hai đều cạn 5 vòng sửa, 12 lượt giải mã, neo
khớp 0%.

**Nhưng số `similarity` tổng thể là số sai để nhìn.** Luật hạ cấp không dùng nó: nó dùng chỉ
số *canonical* — tính trên phần nội dung **đã bỏ neo ra**, và chỉ hạ cấp khi phần ấy vẫn đạt
ngưỡng. Nói cách khác: *"cả câu đọc đúng, chỉ cái tên không xác minh được"* thì hạ cấp;
*"phần còn lại cũng sai"* thì không.

| segment | trạng thái | canonical CER |
|---|---|---|
| `c00003_s0000029` | **hỏng** | **0,333** |
| `c00002_s0000062` | **hỏng** | **0,235** |
| `c00003_s0000030` | cảnh báo | 0,208 |
| `c00003_s0000032` | cảnh báo | 0,184 |

Thứ tự sạch. Hai câu hỏng có phần nội dung ngoài tên bị nghe sai nhiều hơn hẳn. **Bộ phân
xử nhất quán và có nguyên tắc; không sửa gì cả.**

### Và đây là lý do `accept` **chưa** mở rộng sang segment `failed`

`accept` cho phép người nghe chấp nhận một cảnh báo `PERCEPTUAL_NATURALNESS_REVIEW`, vì ở
đó **chữ đọc đúng, chỉ chất lượng âm thanh bị nghi ngờ** - đúng thứ tai người phân xử được.

Một segment `failed` vì neo tên thì khác: bằng chứng ở trên nói phần nội dung ngoài tên
**cũng** bị nghe sai. Cho phép chấp nhận nó là để người nghe gánh trách nhiệm về những chữ
mà máy không xác minh được - một loại quyết định khác hẳn. Ranh giới ấy là cố ý.

Đường đi đúng cho lớp này không phải nới lỏng mà là **nghe tốt hơn**: so faster-whisper với
openai-whisper trên đúng các bản thu này (`scripts/compare_asr_engines.py`). Nếu nó phiên âm
những câu này chuẩn hơn thì cả lớp tự khỏi mà không phải hạ một cái chốt nào.

## Âm cuối "-er": giữ "ờ", không đổi sang "ơ" (chủ sách quyết, 05/09/2026)

Chủ sách từng viết "phải là u-ni-vơ chứ?" khi thấy `Universe` đọc thành `U-ni-vờt`. Phần
"vờt" là lỗi thật và đã sửa (coda `-rs` sau `ER` bị bỏ), còn phần thanh điệu thì **không**.

Đo trước khi hỏi, và con số làm thay đổi câu hỏi:

- `universe` và `use`/`user` đứng riêng **không xuất hiện lần nào** trong 948 segment. Đó là
  ví dụ để dạy luật, không phải từ trong sách — sửa cũng không đổi được gì cho bản thu này.
- Luật ấy đổi **7 tên** đang kết thúc bằng schwa: `A-thờ` (Arthur), `cai-dờ` (Kaizer),
  `Le-xờ`, `Mai-nờ`, `Hăn-tờ`, `Tây-mờ`, `O-vờ` — trong đó Arthur và Kaizer là tên nhân vật
  chính mà chủ sách **đã nghe qua nhiều phiên bản và chưa từng phàn nàn**.
- 25 tên khác cũng chứa "ờ" nhưng là để **tách cụm phụ âm đầu** (`Bờ-lết`, `Cờ-ri-pơ-linh`)
  — luật khác hẳn, không dính dáng.

Đưa đúng bảy tên ấy ra hỏi, chủ sách chọn **giữ nguyên "ờ"**. Vậy nên đừng "sửa" nó nữa.

> Vẫn còn một điểm bất nhất chưa được xử: `Supporter` đọc là `Xơ-po-tờ` — dùng "ơ" cho chỗ
> tách cụm nhưng "ờ" cho âm cuối, trong cùng một từ. Nếu có ai nghe thấy gợn, đó là chỗ để
> nhìn lại; nhưng phải hỏi trước, không tự đổi.

## Cái giá phía sau: cổng anchor báo động giả trên chính những tên này

Đọc tên tiếng Anh theo âm Việt là điều chủ sách muốn. Hệ quả là **Whisper không ánh xạ ngược
được** từ âm Việt về chính tả tiếng Anh, nên cổng kiểm tra anchor kêu — trên chính những
segment mà giọng đọc đúng.

Đo trên alpha.46 (05–06/09/2026), **19 segment** mang cảnh báo `ASR_LOCKED_NAME_ANCHOR_*`:

| loại | số | ví dụ máy nghe |
|---|---|---|
| thuật ngữ Anh trong ngoặc | 10 | `Beast Form` → "bitform"; `Soul Arsenal` → "Solarseno"; `Defiled Ones` → "Defi, Lê Tôn" |
| tên riêng Anh inline | 9 | `Samael Kaizer Theosbane` → "Samen Kai giờ theo Âu Bên"; `Juliana Vox Blade` → "Juliana Vogtberlitz" |

**19/19 cùng một nguyên nhân duy nhất.** Không có cái nào là lỗi đọc.

Đối chiếu với phán quyết của tai người: hôm 04/09/2026 chủ sách nghe 6 segment mang cảnh báo
anchor và kết luận **6/6 đọc đúng** — báo động giả toàn phần. Chính ông nói ra nguyên nhân:
*"những từ được convert từ tiếng anh sang âm tiếng việt thì tool nghe của bạn nghe không tốt"*.

Nên cổng này hiện tính phí bằng **tai người**: 19 lần nghe cho một lớp lỗi đã biết là giả.
Nhưng nới nó là một quyết định chất lượng, không phải một bản vá — nới ra thì một lần đọc sai
tên thật cũng lọt. Cần hỏi chủ sách kèm số liệu, đừng tự đổi.

> Ghi chú cho lần hỏi: câu hỏi đúng không phải "có bỏ cổng anchor không" mà là "khi đoạn văn
> có tên tiếng Anh **đã được khoá cách đọc**, và ASR trượt đúng ở tên đó chứ không ở phần
> tiếng Việt quanh nó, thì đó có còn là bằng chứng gì không". Phần tiếng Việt trong cả 19
> segment đều được nghe lại chính xác.
