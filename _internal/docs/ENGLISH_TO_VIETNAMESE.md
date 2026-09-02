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
