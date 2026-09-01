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
| Noah | Nô-a | | Juli | Giu-li |
| Incredible | In-cơ-re-đa-ben | | Sound | Xan |

**Không từ nào cần ngoại lệ.** Hai ví dụ người nghe đưa ra — `seed` → "xít" và `king` →
"kinh" — **rơi ra từ chính bộ luật**, không phải được nhét vào bảng tra.

## Còn hở

1. **Phụ âm đầu /w/**: `Wolf` ra "Uun" vì /w/ ánh xạ thành "u". Người nghe gợi ý "gốp" —
   tức /w/ → "g". Chưa sửa vì chưa tìm được nguồn cho luật này.
2. **Nguyên âm chưa khớp hoàn toàn**: `incredible` ra "In-cơ-re-đa-ben" chứ không phải
   "in-cờ-ri-đi-bồ". Khung âm tiết đúng, nhưng bảng nguyên âm và /əl/ cuối chưa chuẩn — /əl/
   nên thành "ồ" (như `Michael` → "Mai-cồ" đã có sẵn trong bảng ngoại lệ).
3. **Thanh điệu ngoài âm tiết đóng**: các âm tiết mở đều mang thanh ngang. Tiếng Việt thật
   phân bố đa dạng hơn, nhưng chưa có luật nào để suy ra.
4. **Vần vẫn có thể lạ**: bộ kiểm chỉ xét phụ âm đầu và ký tự cuối, chưa có danh sách vần
   hợp lệ, nên một vần hiếm vẫn lọt được.
