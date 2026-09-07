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

## Hướng sửa (chưa làm — `asr.py` là file khoá)

`asr.py` nằm trong `QUALITY_IMPLEMENTATION_FILES`; sửa nó là đổi
`quality_implementation_hash()` và alpha.51 sẽ từ chối resume. Nên fix thuộc về bản sau.

Ba hướng, theo thứ tự tôi tin cậy:

1. **Cho neo nhận cả dạng chính tả gốc rời từng chữ.** Neo hiện có `source_spelling` là cả
   cụm `["samael","kaizer","theosbane"]` — đòi khớp cả ba. Whisper gõ `Samen Kaiser theo
   bên`: trộn phiên âm với chính tả gốc. Cho phép **khớp trộn từng chữ một** thì vòng 0 đỗ.
2. **Bỏ điều kiện `ordinary >= anchor` của van cứu.** Điều kiện này tắt van đúng lúc cần
   nhất. Ngưỡng tương đồng đã có sẵn để làm việc của nó rồi.
3. **So bằng âm, không bằng chữ.** Đúng nhất, đắt nhất: chuyển cả hai vế về một dạng biểu
   diễn âm rồi mới so. Sửa được tận gốc mọi biến thể chính tả Whisper có thể nghĩ ra.

Sửa xong phải kiểm lại đúng ba đoạn trên: vòng 0 và vòng 2 của `c00005_s0000013` **phải đỗ**,
còn bản `Sam Min` **phải trượt**. Nếu bản `Sam Min` cũng đỗ theo thì đã nới quá tay.

## Bài học chung

Phép kiểm này **có** tín hiệu thật — nó tìm ra đúng một đoạn hỏng trong 18 đoạn, và chủ sách
xác nhận độc lập. Ngược hẳn với phép kiểm cảm thụ (xem `PERCEPTUAL_QA_COST.md`, ngang đồng
xu). Chỗ hỏng không nằm ở chuyện nó nghe, mà ở chuyện nó **so sánh**: đem chính tả của
Whisper đọ với chữ phiên âm rồi gọi chênh lệch chính tả là lỗi phát âm.

Một phép kiểm biết phát hiện lỗi nhưng không biết phân biệt bản đúng với bản sai thì tệ hơn
là không có: nó bắt đúng chỗ đau, rồi vứt luôn thuốc.
