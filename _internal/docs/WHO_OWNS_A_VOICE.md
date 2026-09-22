# Ai sở hữu một giọng — và vì sao câu ấy phải trả lời ở quy mô CUỐN SÁCH

`TWO_CHARACTERS_ONE_VOICE.md` nói về trục **trong một chương**: hai người không được trùng giọng
khi cùng xuất hiện. Tài liệu này nói về trục còn lại, trục **giữa các lô**: một người phải giữ
đúng một giọng suốt cuốn sách, kể cả khi anh ta im lặng suốt bốn mươi chương rồi mới nói lại.

Hai trục xung đột nhau ở đúng một chỗ, và dự án đã chọn xong: *"hai người một giọng trong cùng
chương"* **nặng hơn** *"một người đổi giọng giữa các chương"* — người nghe tưởng là cùng một người,
ngay trong một cảnh. Nên khi phải chọn, nhất quán nhường đúng.

## Cái gì quyết định, theo đúng thứ tự một lượt phóng lô

```
before_a_batch.py            cổng: cây sạch, hàng chờ rỗng, bộ test đã xanh
cli create                   project mới (tên = nội-dung-địa-chỉ theo tiêu đề + nguồn)
seed_chain.py --chain-all    CHUỖI project để cộng dồn  ── xem "sổ cộng dồn" dưới đây
backfill_exposure.py CHAIN   ghi sổ `character_exposure` vào chain[-1] = project GIEO
port_pronunciations.py       sổ cách đọc
port_casting.py  PREV -> mới MANG quyết định giọng của chuỗi gieo sang
seed_listener_acceptances.py
pin_the_book_cast.py --apply LẤP chỗ chuỗi gieo bỏ quên, nguồn là CUỐN SÁCH ĐÃ GHÉP
resync_spoken_text.py --apply
cli run                      registry + allocator quyết phần còn lại
```

Chỉ **hai** chỗ trong cả cây ghi `characters.locked_voice_key`: `port_casting.py` và
`pin_the_book_cast.py` (cộng `cli cast` khi có người tự tay chọn). Allocator **không** ghi pin.

## Sổ cộng dồn: con số quyết định ai giữ một giọng dùng chung

Kho giọng của cuốn 2 đã cấp hết — **nam 14/14**, nữ 15/27 — nên mỗi pin mới đều **dùng chung** một
giọng với người đã ghim. Khi hai người tranh một `voice_key`, `port_casting` xếp hạng theo:

```
1. số câu cộng dồn cả chuỗi   (`character_exposure.dialogue_lines`)
2. số câu trong lô nguồn
3. có đang giữ pin hay không
```

Thứ tự ấy **đúng** — nó cân "người nghe đã nghe ai nhiều hơn" — và nó chỉ đúng khi **nấc thứ nhất
đúng**. Ngày 16-09 nấc ấy sai và cái giá hiện ra ngay:

```
lo03 (15-09 19:23)  NATASHA 382 cau / 3 lo      <- so day du
lo04 (16-09 06:37)  NATASHA   8 cau / 1 lo      <- bi GHI DE
                    CHELY     9 cau / 1 lo
```

`launch_repair.sh 1` (bước 4b của ranh giới, vá các chương của **lô 1**) dựng chuỗi bằng
`chain(1)` — chỉ lô 1 — rồi `backfill_exposure` **ghi đè** sổ đầy đủ. Lô 1 là chương 000..049,
nơi NATASHA im. Nên **8 < 9**, `CHELY` (một chương) thắng giọng của NATASHA (42 chương), NATASHA
mất pin, và chương 090 đúc lại xong thì **lên sách bằng giọng thiểu số** của bà ấy.

Đã chữa: `seed_chain.py --chain-all` phủ **mọi** lô đang có, dùng ở cả hai launcher; bài
`tests/test_the_exposure_chain_covers_every_batch.py` từ chối dạng `<lô> --chain`. Chứng minh
đầu-cuối: dựng lại sổ với `--chain-all` (25 project) cho `NATASHA 389/10`, và `port_casting` đổi
phán quyết thành *"BỎ QUA CHELY (được nhắc 9 lần): NATASHA (được nhắc 389 lần) giữ
ngoc_linh_f093"*.

**Luật rút ra:** một phép đo *cộng dồn* không bao giờ được dựng lại từ một tập con rồi ghi đè bản
đầy đủ. Nếu phải ghi đè, chuỗi phải phủ mọi thứ đã có.

## Bốn lớp khuyết tật đã đo (16-09), và cái nào đã chữa

| lớp | con số | chữa ở đâu |
|---|---|---|
| sổ cộng dồn bị thu nhỏ → sai chủ | 1 chương lên sách sai giọng (090) | **đã chữa**: `--chain-all` |
| người mang hai giọng vì giọng bị tranh | **23/24** người mang hai giọng là người bị tranh | chưa: cần đúc lại từng chương đã lên sách |
| nhãn **không có trong nguồn** giữ pin | ~5–6 chỗ kho giọng (`SELNE`, `SAMAELE`, `NATHASA`, `NATHANAS`, `ALICE DRACEN`) | **đã chữa**: `pin_the_book_cast` bỏ pin ấy |
| một NGƯỜI nhiều NHÃN | `SELENE` 4 nhãn / 3 giọng | một nửa (nhãn không có trong nguồn); nửa "tên riêng vs tên đầy đủ" còn mở |
| **ghim của người nghe làm giọng TRÔI mỗi lô** (22-09) | 3/3 người bị ghim: giọng đa số trên sách CHÍNH LÀ giọng sai; CAMIL `quynh_anh_f108` lô 11 rồi `ngoc_huyen_f100` lô 12 | **đã chữa**: `pin_the_book_cast` tính đa số chỉ trên giọng hợp với ghim - xem mục dưới |

## Ghim của người nghe từng khiến giọng trôi, và cách nó được chữa (22-09)

Kiểm phân vai lô 13 thấy đúng ba lần `Bỏ giọng ghim` của lô 12 lặp lại nguyên văn - CAMIL, CHRISTOPHER,
KAELYN. Lặp lại tức là mỗi lô nhận lại cùng một giọng sai rồi bỏ nó. Truy ngược:

1. Người nghe ghim CAMIL là nữ ở lô 10 (`cli cast --gender female`), vì 36 câu của cô bị đọc giọng nam.
2. `pin_the_book_cast.py` chạy ở mỗi lần phóng lô và ghim mỗi người vào **giọng đa số trên cả sách**.
   Phần lớn chương của một người được thu TRƯỚC lúc người nghe ghim, nên đa số chính là giọng sai:

       CAMIL        ghim nữ        thai_son_f093 (NAM) 12 chương | ngoc_huyen_f100 5, quynh_anh_f108 1
       CHRISTOPHER  ghim nam/già   ngoc_linh_f107 (NỮ) 11 chương | thanh_binh_f090 5, thai_son_f104 4
       KAELYN       ghim nữ/lớn    ngoc_linh_f109 (TRẺ CON) 4    | ngoc_linh_f093 1

3. Phân vai (`_drop_pins_that_contradict_a_person`) bỏ đúng giọng ấy - đúng - rồi để kho giọng cấp một
   giọng khác, **tuỳ lúc ấy kho còn gì**. Giọng mới không được ghi vào sổ (allocator không viết pin),
   nên lô sau lặp lại từ bước 2.

Người nghe nghe thấy: CAMIL đúng phái từ lô 11, nhưng **hai giọng nữ khác nhau ở hai lô liền nhau**.
Hai tầng mỗi tầng tự đúng, ghép lại thành sai - cùng hình dạng với sự cố CHRISTOPHER chương 114 ở trên.

**Chữa**, trong `pin_the_book_cast.py` (script, không bị khoá): giọng đa số chỉ tính trên các hàng mà
giọng KHÔNG trái với ghim giới tính/tuổi của chính người ấy (`rows_the_listener_would_accept`, dùng đúng
hai luật của phân vai qua `voice_contradicts_a_person`), và một pin đang trái ghim thì LUÔN được thay bằng
giọng hợp lệ tốt nhất - bỏ qua `min_chapters`, vì để nguyên thì phân vai chắc chắn bỏ nó và rút thăm lại.
Phép kiểm va chạm vẫn dùng sự có mặt ĐẦY ĐỦ: người bị đọc sai giọng ở một chương vẫn có mặt ở chương ấy.

Kiểm trên bản sao sổ lô 13: bản cũ không sửa gì; bản mới bỏ 28 hàng trái ghim khỏi phép tính đa số và
sửa đúng 3 pin (CAMIL -> `ngoc_huyen_f100`, CHRISTOPHER -> `thanh_binh_f090_p-04`, KAELYN ->
`ngoc_linh_f093`); diff toàn văn hai lượt chỉ gồm đúng 5 dòng thêm - 7 pin mới còn lại y hệt. Có hiệu
lực từ lô 14. Chương ĐÃ lên sách không đúc lại (lệnh "đang phát triển, không phải sản xuất").

Phép đo tương ứng, chạy lại được bất cứ lúc nào:

```
scripts/one_person_one_voice.py              mot TEN hai giong (bao cao hang ngay)
scripts/measure_who_contends_for_a_voice.py  ai tranh giong cua ai
scripts/measure_did_the_recast_help.py       mot luot duc lai: tot hon hay xau hon
scripts/measure_a_name_that_is_not_in_the_source.py   nhan khong ton tai
scripts/measure_one_person_many_labels.py    mot nguoi nhieu nhan (hai lop)
scripts/measure_would_a_name_fold_be_safe.py luat gop ten: DA BI BAC BO, giu de doi chung
```

## Hai ý tưởng đã bị phép đo bác bỏ — đừng đi lại

**1. Gộp tên theo khoảng cách ký tự ở tầng phân tích.** Luật: *nhãn vắng mặt trong văn bản của
project + đúng một tên trong văn bản cách ≤ 2 phép sửa ⇒ một người.* Đo trên mọi project: **47 cặp
ở cuốn 2, 31 ở cuốn 1, phần lớn SAI** — `JOEL`(17 chương)→`JOHN`, `AARON`→`SHARON` (nam→nữ),
`ATHY`→`TAY` (một phantom), `CATHY`↔`ATHY` và `RAY`↔`SAM` vòng tròn. Nguyên nhân: văn bản một
project **một chương** là mẫu quá nhỏ, và tên ngắn (RAY, SAM, NAR, TAY) sinh láng giềng giả. Tầng
phân tích **không có đủ bằng chứng** cho việc này.

**2. Ghim tất cả mọi người.** `pin_the_book_cast --min-chapters 2` có lý do: ngưỡng 1 đề nghị 68
người trong đó 35 người chỉ nói **một** chương — ghim họ không cứu ai (không có chương thứ hai để
so) mà mỗi pin là một lần chia giọng, tức một khả năng va chạm cùng chương ở 800 chương còn lại.

## Thứ duy nhất đáng tin khi hỏi "nhãn này có phải người không"

Một chuỗi **không hề xuất hiện trong nguồn** thì không thể là tên — nhị phân, không đoán. Ba điều
kiện bắt buộc, cả ba đều đã từng sai khi viết:

1. **Bỏ dấu cả hai bên.** `NGUOI TRA LOI` (160 lần nhắc, có pin) là bản rơi dấu của `NGƯỜI TRẢ
   LỜI` trong nguồn; so nguyên dấu thì nó bị gắn cờ oan.
2. **Loại tên dành riêng.** `NARRATOR` đương nhiên không có trong nguồn. Bản đầu của phép kiểm in
   ra `BỎ PIN NARRATOR: narrator` — một lượt `--apply` như thế **đúc lại giọng kể của cả cuốn**.
3. **Khớp cả từ.** `ALI` không được coi là "có trong nguồn" chỉ vì `Alice` chứa nó.

Bài `tests/test_a_name_not_in_the_source_is_not_a_person.py` ghim cả ba.

## Cách đọc một sự cố về giọng

1. `scripts/one_person_one_voice.py` — có va chạm **cùng chương** không? (phải là 0)
2. `scripts/measure_did_the_recast_help.py <chương...>` — lượt đúc lại vừa rồi làm tốt hơn hay xấu
   hơn, so với **đa số của chính người ấy trên cả cuốn**?
3. `characters.locked_voice_key` trong **từng project của chuỗi**, xếp theo `book.created_at` — pin
   đổi chủ ở đâu thì lỗi ở đấy.
4. `character_exposure` của project **gieo** — nấc thứ nhất của phép xếp hạng có đúng không?
5. `runtime_events` của project: `_drop_pins_that_share_a_chapter` **ghi sổ** khi nó bỏ một pin;
   không có dòng nào thì nó không phải thủ phạm.
6. Đầu ra của `port_casting` và `pin_the_book_cast` nằm trong log ranh giới — từ 16-09 chúng không
   còn bị đổ vào `/dev/null` nữa, vì một quyết định dàn giọng không ai đọc được là một quyết định
   không kiểm được.
