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
