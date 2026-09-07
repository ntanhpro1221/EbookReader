# Neo tên khoá đang chấm chính tả, không chấm cách đọc

*Phát hiện 2026-09-07, trên alpha.51. Đây là lỗi làm hỏng chất lượng sách, không phải lỗi
làm chậm máy — nó đã **loại hai bản thu đọc đúng và giữ lại bản đọc sai**.*

## Chuyện xảy ra

Chủ sách nghe đoạn `c00005_s0000013` — "Tên tôi là Samael Kaizer Theosbane." — và nhận xét:

> âm thứ 2 của chữ samael đọc nghe như bị ngắt giữa chừng, còn lại thì đều đúng

Rồi khi tôi đoán sai rằng cách phiên âm bị thiếu âm, chủ sách sửa lại:

> phiên âm ra xa-men là đúng rồi, nhưng tôi nghe đọc như là xa-min ấy

Cả hai nhận xét đều khớp với bằng chứng máy đã lưu sẵn — nếu chịu đọc nó.

## Bằng chứng

Cho Whisper đọc lại chính các bản thu đã có, ở cả 18 đoạn có tên "Samael" trong sách:

| chương | Whisper gõ ra |
|---|---|
| 2, 6, 7, 8, 9, 10 | `Samen` / `Xamen` / `sa men` / `Sa-men` — **đúng** |
| 5 (bản được giữ) | `Sam Min` — **sai**, đúng cái chủ sách nghe |

Vậy từ điển phiên âm không sai, 17/18 chỗ đọc đúng, và phép kiểm neo-tên đã chỉ đúng vào
đoạn duy nhất hỏng. **Một true positive sạch.**

Nhưng nhìn sổ ứng viên của chính đoạn đó thì câu chuyện lật ngược:

| vòng sửa | Whisper gõ ra | phán quyết |
|---|---|---|
| **0** | `Tên tôi là Samen Kaiser theo bên.` | **loại** |
| 1 | `Tên tôi là Samuel Kaiser The Oxbane.` | loại |
| **2** | `Tên tôi là Samen Kaiser theo bên.` | **loại** |
| 3 | `Tên tôi là Samuel Kaiser The Osbay.` | loại |
| 4 | `Tên tôi là Samen Kai rửa theo binh.` | loại |
| *(bản gốc giữ lại)* | `Tên tôi là Sam Min Kaiser theo bên.` | **giữ** |

Vòng 0 và vòng 2 **đọc đúng tên**. Cả hai bị loại. Bản duy nhất đọc sai thì được giữ và gửi
đến tai chủ sách.

## Vì sao

Bằng chứng lưu trong `locked_name_anchor_metrics` của vòng 0:

```
anchors: [{"comparison_mode": "normalized_exact",
           "kind": "spoken_form",     "tokens": ["xa","men","cai","dờ","theo","bên"]},
          {"comparison_mode": "normalized_exact",
           "kind": "source_spelling", "tokens": ["samael","kaizer","theosbane"]}]
matched_occurrence_count: 0 / 1
ordinary_exact_match_count: 3   (trên 3 chữ thường — khớp trọn vẹn)
raw_similarity: 0.818           (canonical_min_similarity: 0.78 — ĐỦ ĐIỀU KIỆN)
canonical_waiver_available: false
```

Hai điều, và điều thứ hai mới là điều chí mạng.

**1. Neo so bằng chính tả (`normalized_exact`).** Whisper viết tên tiếng Anh bằng chính tả
tiếng Anh: `Kaiser`, `Arthur`, `Samuel`. Neo đòi chữ phiên âm tiếng Việt: `cai dờ`, `A-thờ`,
`xa men`. **Hai thứ phát âm y hệt nhau và không bao giờ khớp được bằng phép so chính tả.**
Ba chữ thường "tên tôi là" khớp trọn vẹn 3/3 — chỗ duy nhất trượt là cái tên, và trượt vì
cách viết.

**2. Van cứu bị tắt đúng lúc cần nhất.** Có đường cứu bằng độ tương đồng, nhưng:

```python
canonical_waiver_available = (
    ordinary_expected_tokens >= CANONICAL_ANCHOR_WAIVER_MIN_ORDINARY_TOKENS
    and ordinary_expected_tokens >= anchor_expected_tokens
)
```

Câu "Tên tôi là Samael Kaizer Theosbane." có 3 chữ thường và 6 token tên. `3 >= 6` là sai,
nên van tắt. **Van an toàn tắt đúng ở loại câu nguy hiểm nhất: câu gần như chỉ có mỗi cái
tên** — mà đó chính là câu nhân vật tự giới thiệu, câu sẽ lặp lại suốt cả bộ truyện.

Và `raw_similarity` là 0,818, trên ngưỡng 0,78. **Bản thu đúng đã đủ điều kiện đỗ, chỉ là
không có đường nào hỏi đến nó.**

## Bán kính ảnh hưởng

Không riêng "Samael". Cùng một dạng lỗi ở `c00010_s0000017`:

| | |
|---|---|
| lời | "Ông ta chính là cha tôi, Arthur Kaizer Theosbane." |
| neo đòi | `A-thờ cai-dờ theo-bên` |
| Whisper gõ | `Ông ta chính là cha tôi, Arthur Kaiser theo bên.` |
| chủ sách nghe | **"đúng rồi"** |
| máy | loại |

Mọi câu chứa tên tiếng Anh đã khoá đều nằm trong vùng rủi ro, và rủi ro **cao nhất** ở câu
ngắn — nơi tên chiếm phần lớn số chữ và van cứu tự tắt.

## Hướng sửa (`asr.py` là file khoá — làm ở nhánh `fix/anchor-and-acceptance`)

`asr.py` nằm trong `QUALITY_IMPLEMENTATION_FILES`; sửa nó là đổi
`quality_implementation_hash()` và alpha.51 sẽ từ chối resume. Nên fix thuộc về bản sau.

**Đã đo, nên bỏ được hai hướng sai.** Trước khi sửa, tôi đo độ tương đồng của bản đọc đúng
và bản đọc sai:

| bản thu | Whisper gõ | `raw_similarity` |
|---|---|---|
| vòng 0 — **đọc đúng** | `Samen Kaiser theo bên` | **0,818** |
| bản giữ — **đọc sai** | `Sam Min Kaiser theo bên` | **0,816** |

Cách nhau **0,002**. Nên hướng "nới van cứu bằng độ tương đồng" — hướng tôi đề xuất trong bản
đầu của tài liệu này — **là sai**: nó thả bản hỏng qua đúng bằng bản đúng. Phép đo tương đồng
**cả câu** không phân biệt được, vì lỗi phát âm một âm tiết bị hoà tan vào khoảng cách chính
tả của cả cụm tên. Đây cũng là lý do phải cẩn thận với chính con số 0,818 mà tài liệu này
từng khoe là "đủ điều kiện đỗ": nó đủ điều kiện, nhưng bản hỏng cũng vậy.

**Và hướng thứ hai cũng sai, dù nó trông rất đúng.** Chấm tương đồng ký tự nhưng thu hẹp
về riêng thành phần tên thì tách được hai bản kia (0,800 so với 0,667) — nhưng không đặt được
ngưỡng nào cả:

| cặp | tương đồng | phải ra sao |
|---|---|---|
| `samen` với `xamen` (đúng) | 0,800 | **đỗ** |
| `lucian` với `lucien` (tên khác) | **0,833** | **trượt** |

Tên khác lại giống hơn bản đọc đúng. Mọi ngưỡng nhận bản đúng đều nhận luôn một tên khác. Các
test neo cũ ghim đúng điều này, và chúng có lý — dựng thử hướng đó thì **18 test đỏ**.

**Hướng đúng: so âm, không so chữ.** Trong tiếng Việt "x" và "s" là một âm còn "e" và "i" thì
không — đúng cái tai người nghe ra. Mã đã có sẵn `_vietnamese_phonemes`, chỉ là chưa ai dùng
nó ở mức thành phần:

| | |
|---|---|
| kỳ vọng `xa`+`men` | `sˈaː mˈɛn` |
| đúng `sa`+`men` | `sˈaː mˈɛn` — **khớp chính xác** |
| sai `sam`+`min` | `sˈaːm mˈɪn` — khác |
| `kaizer` với `kaiser` | `kˈaɪzɚ` cả hai — **khớp** |
| `lucien` với `lucian` | khác |

**Không có ngưỡng nào cả** — âm khớp hoặc không. Đó là ưu điểm lớn nhất của hướng này so với
hai hướng trước.

Cách ghép thành phần nằm sẵn trong dữ liệu, không cần tra bảng: cách đọc dùng **gạch nối bên
trong một thành phần và dấu cách giữa các thành phần**, nên `"Xa-men cai-dờ theo-bên"` tách
theo dấu cách ra đúng ba phần của `Samael Kaizer Theosbane`, rồi mỗi phần tách theo gạch nối
ra các âm tiết cần đọc. Khi hai bên không tách ra cùng số phần thì **từ chối luôn** thay vì
đoán — ghép sai còn tệ hơn không ghép.

### Bốn ràng buộc, mỗi cái do một test cũ bắt được

Dựng xong bản đầu thì nó đúng cả bốn ca thật nhưng phá 18 test khác. Mỗi lần sửa lộ ra một
ràng buộc mà tôi không nghĩ tới:

1. **Không được dài hơn cách viết dài nhất mà neo chấp nhận.** Máy phiên âm đọc `enne` và
   `en` như nhau, nên "Lucien" nuốt luôn "Lusienne" — hai nhân vật khác nhau.
2. **Không được dùng token mà một lần xuất hiện khác đã chiếm.** Không có nó thì một cái tên
   đòi ba lần được thoả bằng **một** lần đọc: phép căn chỉnh khớp lần 2 và 3, để lần 1 tự do
   đi tìm lại cái tên ngay trong đoạn của lần 2.
3. **Phải đi một chiều.** Không có nó thì "Iven gặp Lucien" thoả được danh sách neo viết theo
   thứ tự Lucien rồi Iven.
4. **Không được dùng token mà chữ thường đã khớp.** Với "Mây may áo" đọc thành "Lucy may áo",
   cái tên đọc sai, nhưng chữ "may" thường ở ngay sau lại là đồng tự của nó sau khi bỏ dấu.
   Được tự do quét thì nó vớ đúng chữ đó và cho đỗ một bản đọc sai tên.

Một cách chữa nghe rất hợp lý mà **sai**: ghim cứu hộ vào đúng vị trí phép căn chỉnh gán cho
neo. Khi neo không khớp được, phép căn chỉnh đặt nó vào chỗ **rẻ nhất về chi phí sửa** chứ
không phải chỗ cái tên nằm — với ca Samael, nó đặt vào token cuối câu ("bên"). Ghim vào đó
thì cứu hộ chết đúng ở ca nó sinh ra để cứu. Ràng buộc (4) mới là cách chữa đúng.

Sửa xong phải kiểm lại đúng ba đoạn trên: vòng 0 và vòng 2 của `c00005_s0000013` **phải đỗ**,
còn bản `Sam Min` **phải trượt**. Nếu bản `Sam Min` cũng đỗ theo thì đã nới quá tay.

## Fix này KHÔNG làm gì (và đó là điểm mạnh của nó)

Chương 10 có **hai** đoạn bị chặn, và fix chỉ gỡ một:

| đoạn | neo đòi | Whisper gõ | sau fix |
|---|---|---|---|
| `c00010_s0000017` | `A-thờ cai-dờ theo-bên` | `Arthur Kaiser theo bên` | **đỗ** |
| `c00010_s0000016` | `Đon Xờ-cớt` | `đon sờ **cướp**` | **vẫn trượt** |

Đoạn thứ hai trượt ở đúng thành phần thứ hai: `[True, False]`. `sờ` khớp `Xờ` (s với x cùng
âm), nhưng `cướp` không phải `cớt` — giọng đọc sai thật. Chủ sách đã nghe và chấp nhận nó từ
trước, nên chương vẫn xuất được, nhưng bằng **lời chấp nhận** chứ không phải bằng fix này.

Đây là phép thử quan trọng nhất của cả thay đổi. Một fix chỉ biết cho đỗ nhiều hơn thì không
phân biệt được gì cả — nó chỉ dời chỗ hỏng từ "chặn oan" sang "thả oan". Fix này cho đỗ đúng
những bản lệch **chính tả** và vẫn chặn những bản lệch **âm**, và cả hai vế đều có bản thu
thật làm bằng chứng.

## Bài học chung

Phép kiểm này **có** tín hiệu thật — nó tìm ra đúng một đoạn hỏng trong 18 đoạn, và chủ sách
xác nhận độc lập. Ngược hẳn với phép kiểm cảm thụ (xem `PERCEPTUAL_QA_COST.md`, ngang đồng
xu). Chỗ hỏng không nằm ở chuyện nó nghe, mà ở chuyện nó **so sánh**: đem chính tả của
Whisper đọ với chữ phiên âm rồi gọi chênh lệch chính tả là lỗi phát âm.

Một phép kiểm biết phát hiện lỗi nhưng không biết phân biệt bản đúng với bản sai thì tệ hơn
là không có: nó bắt đúng chỗ đau, rồi vứt luôn thuốc.

## Ranh giới của fix, đo trên ca thật đầu tiên nó không cứu được

alpha.52 chương 3, `c00003_s0000029`:

| | |
|---|---|
| lời | "Hắn là Hoàng Tử Quỷ Thứ Mười (Tenth Demon Prince)." |
| neo | `Tenth Demon Prince` → `Ten Đe-mon Pờ-rin` |
| Whisper gõ | "Hắn là hoàng tử quỷ thứ 10, tên **Demon Perrin**." |
| khớp âm từng phần | `[Tenth ✓, Demon ✓, Prince ✗]` |

Hai thành phần đầu được cứu. `Prince` thì không, và lý do rất hẹp:

```
kỳ vọng  pờ | rin  ->  pˈɔ    ɹˈin
tách     per| rin  ->  pɜː    ɹˈin      <- âm tiết SAU khớp chính xác
```

Lệch đúng **một nguyên âm**: `pɜː` (tiếng Anh "per") so với `pˈɔ` (tiếng Việt "pờ"). Tai người
nghe là một âm; máy phiên âm coi là hai.

**Không nới, và đây là lý do.** Nới nguyên âm ở mức này là mở lại đúng cánh cửa đã đóng:
`Lucian` với `Lucien` cũng lệch nguyên âm, và test cũ ghim rằng chúng **phải** khác nhau — hai
nhân vật khác nhau. Chưa có cách nào tôi đo được để phân biệt "lệch nguyên âm vì phiên âm Việt
hoá" với "lệch nguyên âm vì tên khác". Nới bừa là đổi lỗi chặn oan lấy lỗi thả oan, mà thả oan
thì ghim khiếm khuyết vào sách.

**Và hệ thống vẫn xử đúng ca này.** Khi máy không quyết được, phán quyết của người quyết —
`c00003_s0000029` đã có phán quyết từ 2026-09-04, và nó đã nằm trong alpha.52. Fix này làm
**giảm** số đoạn cần tai người, không phải xoá bỏ chúng. Đừng đọc nó thành "phép kiểm neo tên
giờ đã đúng cho mọi tên".

## Lỗ hổng dễ dãi tự tìm ra, và cái giá của việc bịt nó: bằng không

Sau khi viết phần gấp tên khỏi số đo câu, tôi soát lại chính nó thay vì chờ nó cắn. Phép khớp
thành phần cho phép các phần của tên khớp **cách quãng**:

```
"samen đã giết rất nhiều người kaiser theo bên"
 └────────── span phủ 9 token cho một cái tên 4 token ──────────┘
```

Riêng chuyện đó chỉ là lỏng. Cộng với việc **gấp span ra khỏi số đo câu** — thứ làm cho cứu hộ
có tác dụng — thì nó xoá luôn cả mệnh đề ở giữa khỏi phép so, và mọi lỗi phiên âm nằm trong đó
biến mất khỏi điểm số.

**Và nó sẽ vô hình**: `anchor.status` đẹp hơn, chương xuất được nhiều hơn. Đúng dạng hỏng khó
phát hiện nhất — thứ chỉ lộ ra khi có người nghe và thấy sách sai.

Đã buộc các phần sau phải liền kề phần trước, đúng cách một cái tên được nói ra.

**Cái giá, đo trên dữ liệu thật:** chạy lại toàn bộ 51 ca mà alpha.52 đã cứu, với mã đã siết:

| | |
|---|---|
| vẫn cứu được | **57** (nhiều hơn, nhờ bản vá gạch nối) |
| mất đi | **0** |

Không một ca hợp lệ nào phải trả giá. Đó là hình dạng của một ràng buộc đúng: nó chỉ chặn thứ
mà nó sinh ra để chặn.

**Bài học về cách nghiệm thu:** cả ngày hôm nay tôi lặp lại một câu — "một phép kiểm chỉ biết
cho đỗ nhiều hơn thì chưa phân biệt được gì". Lần này chính tôi suýt viết ra một cái. Cách bắt
được nó không phải chạy thêm test, mà là **hỏi ngược lại: fix này làm gì dễ dãi hơn, và chỗ dễ
dãi ấy có nhìn thấy được không?**
