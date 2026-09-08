# Nguồn có thuỷ ấn ẩn, và nó không hại chất lượng — nó hại tính tái lập

Tìm ra 2026-09-08 khi quét toàn bộ 478 file nguồn tìm ký tự ngoài Latin, để xem có gì làm
`_local_name_fallback` ném lỗi giữa một lượt chạy 128 giờ hay không. Không có chữ Ả Rập, CJK
hay Cyrillic nào — nhưng có thứ này.

## Nó là gì

**53 ký tự vô hình** — `ZERO WIDTH JOINER` (U+200D) và `ZERO WIDTH NON-JOINER` (U+200C) xen kẽ
nhau — chèn vào **một** vị trí trong mỗi file, ở **15 file**:

```
015  026  038  086  092  097  114  127  140  164  176  188  229  256  278
```

Mỗi file đúng 53 hoặc 54 ký tự, tổng 800. Chuỗi ZWJ/ZWNJ xen kẽ là một dãy **nhị phân**: đây
là thuỷ ấn của trang nguồn, không phải lỗi gõ. Trong 015.txt nó nằm ngay sau *"Juliana đã"*.

Mắt người không thấy được. Mở file bằng bất kỳ trình soạn thảo nào cũng chỉ thấy một câu bình
thường. Không phép kiểm nào của dự án nhìn nó, vì không phép kiểm nào được viết để nhìn.

## Nó có hại chất lượng không — không, và đây là bằng chứng

Chương 015 đã chạy thật ở alpha.56. Đoạn mang thuỷ ấn:

```
c00006_s0000013_81fb26ac2675   status=verified   8,08s
văn bản : 'Vì tôi đã bất tỉnh gần hai ngày, Juliana đã<53 ký tự vô hình> đưa ra một quyết định…'
nghe ra : 'Vì tôi đã bất tỉnh gần hai ngày, Juliana đã đưa ra một quyết định khôn ngoan là…'
sim 0,966   wer 0,111   không cảnh báo
```

VieNeu đọc lướt qua chúng như không có, Whisper nghe ra đúng câu, và đoạn qua thoải mái. Cũng
hợp lý: `spoken_speakable_chars` đếm `isalnum()`, mà ZWJ không alnum, nên nhịp đọc cũng không
bị lệch.

**Một ca đo được, không phải mười lăm.** Mười bốn chương còn lại chưa chạy tính tới 2026-09-08.

## Cái thật sự nguy hiểm: `stable_id` bám vào từng byte

`stable_id` của một segment là `c{chương}_s{seq}_{sha256(text)[:12]}`, và **hạt giống sinh audio
lấy từ `stable_id`**. Nên nếu thuỷ ấn đổi — trang nguồn cấp lại một dãy nhị phân khác, chuyện
bình thường với thuỷ ấn, đó là mục đích của chúng — thì với **cùng một câu chữ hệt nhau**:

- `text_sha256` đổi ⇒ `stable_id` đổi;
- hạt giống đổi ⇒ **audio đổi**;
- checksum audio đổi ⇒ **mọi phán quyết của người nghe cho đoạn ấy mất hiệu lực**;
- so hash giữa hai lượt chạy vô nghĩa, mà đó là cách alpha.50–54 so được với nhau.

Tức là: **đừng tải lại nguồn**. `D:/Novels/Tools/Text` phải được giữ nguyên như một tài sản,
không phải một bản sao có thể lấy lại. Câu cảnh báo trong [VERSIONS.md](VERSIONS.md) về việc
alpha.46 tạo nhầm từ `Text_Tmp` nói cùng một điều vì một lý do khác; đây là lý do thứ hai, và
nó tinh vi hơn nhiều vì hai file trông **giống hệt nhau** trên màn hình.

## Hướng sửa, và vì sao chưa làm

Lọc bỏ ký tự zero-width lúc nạp nguồn là đúng: sau đó thuỷ ấn đổi bao nhiêu lần cũng không
động tới `text_sha256`, và dự án miễn nhiễm với việc tải lại nguồn.

Chưa làm vì hai lý do, và lý do thứ hai mới là lý do thật:

1. `text_processing.py` nằm trong `QUALITY_IMPLEMENTATION_FILES`, và lúc phát hiện thì
   **alpha.62 đang chạy**. Không sửa file thực thi khi có lượt đang bay.
2. Sửa nó **đổi `text_sha256` của đúng 15 đoạn ấy một lần**, tức là chính cái tác hại mô tả ở
   trên, chỉ là do mình tự gây ra có kiểm soát. Đáng làm — nhưng phải làm **giữa hai lô**, chứ
   không phải giữa chừng, và phải ghi lại là lượt nào bắt đầu dùng.

Thời điểm tự nhiên: ngay trước lô 1 của [PRODUCTION_PLAN.md](PRODUCTION_PLAN.md), vì lô ấy chạy
đè lên chương 000–029 nên chúng sẽ được sinh lại toàn bộ dù sao đi nữa.

## Ba thứ nữa phép quét tìm ra — nghi cả ba, sai cả ba

Ghi lại cả phần **không** hỏng, vì ba nghi ngờ này nghe rất hợp lý và người sau sẽ nghi lại
đúng như thế. Chúng có chung một gốc, và đó mới là điều đáng nhớ: **sách này dùng `«»`, `『』`
và `•` làm dấu hiệu kiểu chữ cho văn bản hệ thống game, không phải để trích lời hay nhấn
mạnh.** Áp cách hiểu thông thường của ba ký hiệu ấy vào đây là làm hỏng, không phải sửa.

### `«…»` bị xếp là narration chứ không phải dialogue

Nghi ngờ nặng nhất, vì bộ chia đoạn **biết** `«»` mà vẫn không gán là thoại — 219 lần trong
008.txt và 011.txt, tức khoảng trăm câu bị người dẫn chuyện đọc thay vì giọng nhân vật.

Đo trên audio đã sinh (alpha.55, alpha.56): 14 segment mang `«»`, tất cả `kind=narration`,
`speaker=NARRATOR`. Và nhìn nội dung thì hiểu ngay:

```
«Thẩm Định»
Nghiến chặt hàm, tôi thu hồi «Thẩm Định» và triệu gọi hai Thẻ Vật phẩm của mình.
```

Đó là **tên kỹ năng**, không phải lời ai nói. Gán chúng cho một nhân vật sẽ khiến giọng đổi
giữa câu mỗi lần nhắc tới một chiêu thức. Hành vi hiện tại đúng.

**`『』` không được bộ chia đoạn coi là ngoặc kép** — đúng, `text_processing.py` biết `«»`,
`‹›`, `""`, `''` nhưng không biết corner bracket. Nghi ngờ là lời thoại bị gán nhầm cho người
dẫn chuyện. Đo: **6 lần trong 3 file** (011, 367, 406), và không lần nào là lời thoại — chúng
là chú thích trong bảng trạng thái kiểu game:

```
Cấp Linh Hồn: C 『Hấp thụ 300 Tinh Hoa Linh Hồn để thăng cấp』
```

Coi chúng là ngoặc kép mới **sai**. Hành vi hiện tại đúng, và không thêm rủi ro ngoặc treo vì
chúng cân đối và bị bỏ qua.

**772 dấu `•` đi thẳng vào văn bản TTS đọc** — đúng, bộ chia đoạn không lọc. Nghi ngờ là TTS
đọc chúng thành tiếng. Đo trên mọi project đã lưu: **240 segment** chứa dấu bullet, trong đó
175 `verified` và 2 `failed`. Whisper nghe ra câu **không có** bullet với sim tới 1,00:

```
văn bản : '• Hệ thống Sức mạnh'
nghe ra : 'hệ thống sức mạnh.'          sim 1,00  wer 0,00
```

Model đọc lướt qua nó như với ký tự vô hình.

### Bảng khép kín: mọi ký tự lạ trong nguồn, và số phận của nó

| ký tự | số lần | xử lý | bằng chứng |
|---|---|---|---|
| `—` `–` `…` | 3.262 | dấu câu thường | — |
| ZWJ/ZWNJ | 800 | **chưa lọc** — xem trên | `verified`, sim 0,966 |
| `•` | 772 | đọc lướt | 240 segment, 175 `verified`, sim tới 1,00 |
| `»` `«` `›` `‹` | 219 | trong `SPOKEN_SEPARATORS` | 14 segment, tất cả `verified` |
| `"` `'` | 321 | ngoặc kép, có nhận | — |
| `°` | 75 | đọc lướt | cùng họ, chưa có ca riêng |
| `⟨` `⟩` | 18 | đọc lướt | cùng họ, chưa có ca riêng |
| `↓` `↑` | 6 | **đọc thành chữ**: "giảm" / "tăng" | 150 segment, 107 `verified`, sim 1,00 |
| `『` `』` | 6 | đọc lướt | 2 segment, `verified`, sim 1,00 wer 0,00 |

`↓` là chỗ dễ tưởng là lỗi nhất và lại là chỗ làm cẩn thận nhất: `text_processing.py` ánh xạ nó
thành **"giảm"** với lý do ghi ngay tại chỗ — *"ký tự MANG NGHĨA phải thành CHỮ"*. Trong
`↓ 1.000 Đơn vị Tinh hoa Linh hồn` thì bỏ mũi tên đi là mất nghĩa "giảm", còn đọc nó thành
tiếng thì vô nghĩa. Whisper nghe ra `"giảm 1.000 đơn vị tinh hoa linh hồn"`, sim 1,00.

Tức là **cả phép quét tìm ra đúng một thứ chưa được xử lý**: thuỷ ấn. Và nó không hại chất
lượng, chỉ hại tính tái lập.
