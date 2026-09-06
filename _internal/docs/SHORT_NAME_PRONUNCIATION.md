# Một tên ngắn chặn cả cuốn sách: ba cánh cửa đóng cùng lúc

## Triệu chứng

Run 10 chương dừng hẳn ở pha phát âm:

```
High-quality pronunciation QA could not resolve: Deck
```

56/57 thuật ngữ khác đã phiên âm xong (`Dragon's Protection` → `Đra-gôn-ét-prô-têc-tiôn`,
`Legendary` → `Le-giân-đe-ri`). **Đúng một từ bốn chữ cái chặn toàn bộ.**

## Nguyên nhân: đáp án đúng đã được tính ra rồi bị vứt đi

CMUdict **có** `deck` → `D EH1 K`. Bộ chuyển `_cmu_pronunciation_to_vietnamese` cho ra
**`'Đec'`**, và `_valid_vietnamese_spoken_form('Deck', 'Đec')` trả về **True**.

Nhưng ba cánh cửa đóng cùng lúc:

| cửa | lý do đóng |
|---|---|
| Đường CMU (`analysis.py`, vòng `cmu_count`) | bỏ qua vì `requires_contextual_review=True` — tên ngắn cần xét ngữ cảnh |
| Đường Qwen | cả batch hỏng, vì các thuật ngữ tiếng Anh khác trả về dạng không hợp lệ tiếng Việt |
| Fallback cục bộ (`_short_name_local_fallback_is_safe`) | từ chối **vì nó CÓ `cmu_pronunciation`** |

Cửa thứ nhất đóng vì "tên ngắn cần xét ngữ cảnh", cửa thứ ba đóng vì "đã có đường CMU lo
rồi". Hai lý do **loại trừ nhau**, và giữa chúng là một đáp án hợp lệ không ai dùng.

## Vì sao KHÔNG sửa bằng cách mở cửa thứ ba

Đã thử: cho `_short_name_cmu_reading()` làm lối thoát cuối trước khi từ chối. Nó giải được
`Deck` → `Đec` và vẫn loại đúng `May` (nằm trong `CMUDICT_CONTEXT_ONLY`).

**Bốn test hỏng**, hai trong đó cố ý mã hoá chính sách:
`test_uncertain_short_names_are_left_verbatim_when_reconciliation_fails` và
`test_high_quality_blocks_unresolved_short_name_pronunciation`. Test dùng `Wolf` — CMUdict
có, nên bản vá tự quyết cách đọc và cổng chặn không còn chặn.

Chính sách đó **đúng và có chủ đích**: với tên nhân vật ngắn chưa chắc chắn, đọc sai lặp đi
lặp lại suốt cuốn sách tệ hơn để TTS đọc nguyên chữ Latin. Đây không phải sơ suất để "sửa".

Và bộ chuyển CMU cũng yếu ở đúng lớp từ này: `Card` → `'Ca'`, mất hẳn phụ âm cuối. Mở cửa
thứ ba là để thứ đó lọt vào sách.

## Cách xử lý: một cái van cho người nghe

```bash
ebook-reader-headless pronounce <project> --surface Deck --spoken Deck
```

Ghi một mục `locked=1`, `confidence=1.0`, `source='listener_choice'`. Khoá nên các pha sau
không hỏi lại; nguồn riêng nên **quyết định của người không bao giờ bị nhầm với phiên âm do
máy sinh** (`english_name_transliteration`).

Nó cũng cho phép đúng thứ bộ kiểm tự động cấm: **đọc y như viết**. Với thuật ngữ game tiếng
Anh đó thường là đáp án đúng, và là đáp án người nghe đã chọn cho `Deck`.

## Vì sao cho người một cái van thay vì nới lỏng máy

Nếu mở cửa thứ ba, mọi tên ngắn có trong CMUdict sẽ được máy tự quyết — kể cả tên nhân vật,
thứ người nghe sẽ nghe hàng trăm lần. Và bộ chuyển CMU yếu ở đúng lớp đó (`Card` → `'Ca'`).

Cho người một cái van thì: máy giữ nguyên sự thận trọng, người chỉ phải trả lời khi máy
thực sự bí, và mỗi câu trả lời được ghi lại là của người.

## Điều đã kiểm chứng: sẽ còn vấp tiếp

Ngay sau khi chốt `Deck`, run vấp tiếp **`Epic`, `Juli`, `Lily`** — trong đó hai cái là tên
nhân vật. Đây không phải sự cố một lần; nó là hình dạng thường trực của một cuốn sách nhiều
tên riêng nước ngoài, và là lý do cái van phải tồn tại chứ không phải một bản vá tạm.

## Một tên hai cách đọc, qua cánh cửa không ai canh (alpha.47, 06/09/2026)

alpha.47 khoá đồng thời hai cách đọc cho cùng một nhân vật:

| surface | spoken_form | conf |
|---|---|---|
| `Arthur Kaizer Theosbane` | `A-thờ cai-dờ theo-bên` | 0,88 |
| `Samael Kaizer Theosbane` | `Xa-men cai-dờ theo-bên` | 0,88 |
| **`Theosbane`** | **`Thê-ô-ban`** | 0,85 |

Docstring của `_local_name_fallback` nói rằng cả đường đọc-theo-chính-tả tồn tại là để chặn
"hai cách đọc của một tên trong một quyển sách". Nó chặn được đường ấy — nhưng defect đi vào
bằng cửa khác: **cách đọc được đề xuất theo từng surface và kiểm tra theo từng surface**,
nên không có gì so `Theosbane` với chữ `Theosbane` nằm trong `Samael Kaizer Theosbane`.

Code cho ra `Theo-bên` cho tên đơn; bản ghi `Thê-ô-ban` đến từ model, không phải từ fallback.

### `name_component_corrections()` — có hàm, **chưa nối vào**

Đối chiếu chéo: với mỗi tên nhiều từ, nếu số nhóm âm tiết (tách theo khoảng trắng) bằng số
từ thì thành phần tương ứng đọc được trực tiếp; tên đơn nào lệch thì báo. Khác hoa/thường
không tính là hai cách đọc.

Trường hợp không căn được (3 từ, 2 nhóm) thì **bỏ qua chứ không đoán**.

### Cái bẫy trong việc nối nó vào, và vì sao chưa nối

Đường duy nhất ghi đè được hàng đã khoá là `set_listener_pronunciation`, mà docstring của nó
nói rõ:

> khoá là thứ bảo vệ một quyết định của con người khỏi bị một phép phiên âm ghi đè. Nó sai
> khi chính con người là bên yêu cầu.

Dùng nó cho một phép đối chiếu **tự động** là làm đúng điều nó cảnh báo: nếu chủ sách đã tự
ghim `Theosbane` bằng lệnh `pronounce`, phép đối chiếu sẽ lấy tên dài ghi đè lên và **xoá
quyết định của ông**.

Nên khi nối, luật bắt buộc là: **không bao giờ ghi đè hàng có `source = listener_choice`.**
Chiều đúng phải ngược lại — một tên người đã ghim nên kéo theo tên dài chứa nó.

Trong alpha.47 việc này đã xử tay bằng `pronounce Theosbane "theo-bên"` (11 chỗ dùng tên đơn
đều chưa được thu lúc ghim, nên cả quyển nhất quán).

## Cái mà anchor thật sự đang đo (đo 2026-09-06, alpha.43 → alpha.48)

Trong năm lần chạy, **12 segment** bị chặn vì `ASR_LOCKED_NAME_ANCHOR_MISMATCH` sau khi đã
hết mọi vòng sửa. Đọc từng cái một thì lộ ra một khuôn hình:

| tên | ta cho đọc | Whisper viết ra |
|---|---|---|
| Scourge | Xờ-cớt | "sờ cướp" |
| Apex | Ây-pếch | "APEC" |
| Kaizer | cai-dờ | "Kaiser" |
| Samael | Xa-men | "Sam Min", "Samen" |
| Vox | Vóc | "Vogtberlitz" |
| Spirit | Xờ-pi-rít | "S&P ZIT" |

Không cái nào trong số này là bằng chứng TTS đọc sai. "sờ cướp" và "Xờ-cớt" gần như trùng
âm; "APEC" là một từ Whisper biết rõ nên mô hình ngôn ngữ của nó bám vào; "Kaiser" chính là
cách viết gốc của phần tên ấy — tức Whisper *nghe đúng* rồi viết về chính tả tiếng Anh.

**Anchor đang đo lựa chọn chính tả của Whisper, không phải cách phát âm của TTS.** Danh sách
dạng được chấp nhận có `spoken_form`, `source_spelling`, bản bỏ dấu, và `vietnamese_phoneme_exact`
— nhưng tất cả đều **khớp tuyệt đối**, và đều áp cho **cả cụm tên một lúc**.

Hai lỗ hổng, đo riêng:

1. **Không cho trộn hai cách.** "Samael Kaizer Theosbane" đọc "Xa-men cai-dờ theo-bên" bị
   nghe thành "Sam Min **Kaiser** **theo bên**" — một phần theo chính tả Anh, phần kia theo
   phiên âm của ta. Không dạng nào phủ được hỗn hợp. Trên 12 segment bị chặn, cho phép trộn
   cứu được **3** (đều là cùng một segment lặp qua các bản).
2. **Phoneme so tuyệt đối.** 9 segment còn lại mỗi cái kẹt ở **đúng một** thành phần, và
   phần lớn chỉ lệch một phụ âm cuối. Một phép so khoảng cách phoneme có dung sai nhỏ sẽ bắt
   được hầu hết — nhưng nới một cổng *đúng-sai* thì phải có tai người xác nhận trước.

**Chưa sửa gì.** Cả hai đều là nới lỏng một cổng tồn tại để bắt tên đọc sai, và bằng chứng
hiện có là gián tiếp: suy ra từ chính tả Whisper, không phải từ việc nghe. Việc cần làm
trước là đưa đúng 9 bản thu này cho chủ sách nghe với câu hỏi "tên đọc có đúng không?".
Nếu phần lớn là đúng, con số đó biện minh cho bản sửa và cũng đo được nó cứu bao nhiêu.

Cách đo lại: `scratchpad/blocking_anchor_mixture.py`.
