# Một cái tên đọc nhiều kiểu — và hai câu hỏi bị trộn làm một

Lô 3 sinh ra **147** đoạn mang `ASR_LOCKED_NAME_ANCHOR_REVIEW` và **23** đoạn mang
`ASR_LOCKED_NAME_ANCHOR_MISMATCH`. Cả hai mã đều **không chặn chương**: mã đầu nằm trong danh
sách được phép im lặng, mã sau được máy chấp nhận có ghi sổ. Nghĩa là 170 đoạn mỗi lô đi qua mà
không ai nhìn — và câu hỏi đúng để hỏi không phải "sao chúng bị gắn cờ" mà **"trong số ấy, cái
nào người nghe thật sự nghe thấy?"**

Đo ngày 2026-09-10 trên `lo03_bda8cd8c58`: 3.923 phép kiểm neo tên, 60 cặp (tên, dạng đọc đã
ghim) có ≥20 lần neo. Công cụ: `scripts/name_is_read_the_same_way.py`.

## Hai câu hỏi khác nhau

| cột | hỏi gì | ai sai nếu số xấu |
|---|---|---|
| `khớp%` | bản thu có **thoả cổng neo tên** không | chưa biết — cổng hay bản thu |
| `đỉnh%` | trong các lần không khớp, Whisper viết **một dạng** hay **nhiều dạng** | `đỉnh%` cao → cổng sai; thấp → dạng đọc đã ghim sai |

`đỉnh%` là phần của dạng hay gặp nhất trong những lần **không khớp**. Một cái tên đọc ổn định mà
cổng không nhận sẽ cho `khớp%` thấp và `đỉnh%` cao: cổng đang đo chính tả của Whisper, không đo
giọng đọc. Một cái tên mỗi lần một kiểu cho **cả hai** đều thấp, và đó là lúc người nghe nghe
hai người khác nhau.

Vì `đỉnh%` chỉ tính trên phần dư, một tên khớp gần hết vẫn có `đỉnh%` thấp mà vô hại — Michael
khớp 85% thì mẫu còn lại là 27 lần lẻ. Đọc hai cột cùng nhau.

## Cái thật sự hỏng: `Jake`

```
Jake    Giếch    752 neo    khớp   0%    89 dạng    đỉnh 13%   'giết'×89, 'giếc'×79, 'kha'×75
Jake    Jake     291 neo    khớp   1%    40 dạng    đỉnh 44%   'jack'×117, 'rách'×18, 'check'×10
```

**Tám mươi chín dạng** trên 752 lần, dạng hay gặp nhất chỉ 13%. Cùng một câu, hai lần sinh khác
nhau, hai âm khác nhau:

```
"Cậu muốn gì, Jake?"   ->  Whisper: "Cậu muốn gì? Giật."
"Cậu muốn gì, Jake?"   ->  Whisper: "Cậu muốn gì? Dịch."
```

`Giật` và `Dịch` không phải hai cách viết một âm — chúng là hai âm. Bạn thân của nhân vật chính
đang được gọi bằng một cái tên khác nhau gần như mỗi lần xuất hiện, 752 lần trong 32 chương, và
không cổng nào chặn vì mã chỉ là `REVIEW`.

Dạng đọc `Giếch` là thứ hỏng, không phải giọng: cùng giọng ấy đọc `Mai-cồ` (Michael) khớp 85% và
`Xa-men` (Samael) khớp 69%. Và có một mốc so sánh sẵn trong chính dữ liệu — những lần đường ống
đọc **thẳng chữ viết** `Jake` thay vì dạng ghim cho `đỉnh` 44%, gấp hơn ba lần; xem mục dưới.

## `Jake` hỏng ở **cả ba lô**, và đang tệ dần

```
        neo   khớp%   dạng   đỉnh%
lô 1    213     0%     29     33%
lô 2    862     0%     91     15%
lô 3    752     0%     89     13%
```

Một nghìn tám trăm hai bảy lần neo, **0% khớp ở cả ba lô**, và `đỉnh%` đi xuống — 33 → 15 → 13.
Không phải một lô xui: dạng đọc `Giếch` chưa từng làm việc, kể từ chương đầu tiên của cuốn sách.

Số lần neo lớn hơn số đoạn nhiều lần, vì mỗi đoạn qua nhiều lượt kiểm ASR (vòng sửa, ứng viên).
Số đoạn thật:

```
lô 1    24 đoạn / 2 chương
lô 2    89 đoạn / 12 chương
lô 3    69 đoạn / 4 chương
tổng   182 đoạn / 18 chương  (trên 92 chương đã sản xuất)
```

**Giá của việc sửa: đọc lại 18 chương** — khoảng 60% khối lượng một lô, vài giờ GPU. Đó là một
con số phải nói ra trước khi ai quyết định, không phải sau. Và nó chỉ đáng trả nếu bước 2 ở trên
tìm được một dạng đọc **đo được là ổn định**; sửa mù rồi đọc lại 18 chương là trả giá hai lần.

## Cái chỉ là cổng quá chặt: `Awakened`, `Willem`

```
Awakened  Awakened   68 neo   khớp  0%    1 dạng   đỉnh 100%   'awaken'×66
Willem    Guy-lem   512 neo   khớp  1%   33 dạng   đỉnh  58%   'lem'×297
Willem    Willem    222 neo   khớp  9%    5 dạng   đỉnh  77%   'william'×154
Samael    Samael    107 neo   khớp  2%   15 dạng   đỉnh  76%   'samuel'×80
```

`Awakened` đọc **giống nhau 66 trên 66 lần** và vẫn trượt cổng 68 lần: Whisper viết `awaken`,
cổng chờ `awakened`, và một chữ `-ed` cuối là thứ không ai nghe được trong một từ tiếng Anh đọc
bằng giọng Việt. Không có gì để sửa ở audio; có một cổng đang đếm chính tả.

`Willem → Guy-lem` cũng vậy theo cách khác: `'lem'` chiếm 297 trong 512 lần, tức bộ ghép chỉ gán
**âm tiết cuối** cho một neo hai âm tiết, rồi so `guy-lem` với `lem` và trượt. Đây là lỗi **cửa
sổ ghép**, không phải lỗi đọc — thấy được ở `alignment_operation: substitute_anchor` với
`aligned_tokens` dài một token cho một neo ba token.

Ba trong bốn dòng trên là cổng, không phải giọng. Đó là lý do không được đọc 170 cờ mỗi lô thành
170 lỗi — và cũng là lý do không được bỏ qua cả 170.

## Không phải hai dòng trong sổ — hai **biến thể giao** của cùng một dòng

Bản đầu của mục này viết "bảy cái tên có hai dạng đọc cùng lúc trong sổ" và **sai**. Sổ có
đúng **một** dòng cho mỗi tên (`Jake → Giếch`, id 132, `locked=1`). Cái tôi đếm thành dòng thứ
hai là `pronunciation_delivery_variant`: đường ống sinh ứng viên theo **hai** biến thể — đọc
theo dạng đã ghim (`locked_spoken_v1`) và đọc **thẳng chữ viết gốc**
(`source_spelling_v1`) — và cả hai đều bị ASR chấm. Cơ chế ấy đã có tài liệu riêng:
[PRONUNCIATION_VARIANT_DRIFT.md](PRONUNCIATION_VARIANT_DRIFT.md).

Tách theo biến thể thì con số nói một điều sắc hơn:

```
Jake     locked  'Giếch'    752 neo   khớp  0%   đỉnh 13%   'giết'×89, 'giếc'×79
Jake     source  'Jake'     291 neo   khớp  1%   đỉnh 44%   'jack'×117, 'rách'×18
Samael   locked  'Xa-men'   213 neo   khớp 69%   đỉnh 42%   'simon'×26
Samael   source  'Samael'   107 neo   khớp  2%   đỉnh 76%   'samuel'×80
Willem   locked  'Guy-lem'  512 neo   khớp  1%   đỉnh 58%   'lem'×297
Willem   source  'Willem'   222 neo   khớp  9%   đỉnh 77%   'william'×154
```

Với `Samael`, dạng đã ghim **thắng**: `Xa-men` khớp 69% còn đọc thẳng chữ viết chỉ 2%. Đó là
dạng ghim làm đúng việc của nó.

Với `Jake` thì ngược: dạng đã ghim `Giếch` cho `đỉnh` **13%**, còn đọc thẳng chữ `Jake` cho
**44%**. Nghĩa là cái transliteration đang làm cho giọng đọc **kém ổn định hơn cả khi không có
nó** — một dòng trong sổ đang gây hại, không phải giúp.

Hệ quả cho hướng sửa, và nó khác hẳn điều tôi viết lúc đầu: không có "dòng tệ hơn để bỏ". Việc
phải làm là **đổi `spoken_form` của `Jake`**, và dữ liệu đã cho sẵn một ứng viên đo được — chính
chữ viết gốc, thứ hiện tại ổn định hơn gấp ba lần dạng đang ghim.

## Một giả thuyết của tôi bị dữ liệu bác

Nhìn danh sách, tôi thấy các dạng xấu đều chèm một âm `ờ` để phá cụm phụ âm —
`I-xờ-hờ-ta-ra`, `Đờ-ra-kên`, `Xờ-pi-rít`, `va-lờ-cờ-rin`, `Cờ-le-vơ-li` — và đoán rằng chèm
`ờ` làm giọng đọc mất ổn định. Đếm:

```
                 số tên   neo    khớp TB   đỉnh TB   số dạng TB
CÓ âm chèm "ờ"      16     703      2,4%     50,0%       8,4
không chèm          44    3999     27,4%     51,9%       9,0
```

`khớp%` khác hẳn (2,4 so với 27,4) nhưng **`đỉnh%` thì không** — 50,0 so với 51,9. Nghĩa là các
dạng chèm `ờ` đọc **ổn định ngang** các dạng khác; chúng chỉ không bao giờ thoả cổng. Giả thuyết
sai, và sai theo hướng đáng ghi: nó gán cho giọng đọc một lỗi thuộc về cổng.

Ca xấu nhất cũng bác nó: `Giếch` **không** có âm chèm nào.

Một phép đếm nữa, đúng nhưng không giải thích được nhiều: neo có `r`/`gi`/`d` đầu âm tiết trượt
96,1% so với 71,4% — phù hợp với chỗ giọng miền Bắc nhập `r`, `gi`, `d` thành một âm /z/, nhưng
nền trượt đã 71,4% nên nó không phải nguyên nhân chính của gì cả.

## Hướng đi — cần thí nghiệm, không phải đoán

Chưa làm gì tối 2026-09-10, vì GPU đang chạy lô 4 và vì **một dạng đọc mới là một phỏng đoán
cho tới khi nghe thử**. Thứ tự đề nghị:

1. **Đổi `spoken_form` của `Jake`** (dòng id 132, `Giếch`). Ứng viên đầu tiên không cần đoán:
   chữ viết gốc `Jake` đã được đo trên chính cuốn sách này và ổn định gấp ba (`đỉnh` 44% so với
   13%). Đây là thay đổi một dòng dữ liệu, không phải một dòng mã.
2. **Nếu 44% vẫn chưa đủ thì mới thí nghiệm** — công cụ đã có:
   `python scripts/try_a_pronunciation.py Jake Giếch Giếc Giết "Giây-cơ" Jake --takes 10`.
   Nó **từ chối chạy khi có lô đang bay** (sinh audio thật thì lấy GPU của lô), dựng một project
   một chương cho mỗi ứng viên rồi chạy qua đúng đường ống thật, và in `đỉnh%` cho từng dạng.
   Nói cách khác: sinh cùng một câu với 4–6 dạng ứng viên
   (`Giếch`, `Giêch`, `Giây-cơ`, `Jếch`, `Jake`...), mỗi dạng 10 seed, rồi đo `đỉnh%` bằng chính
   ASR. Chọn theo số, không theo tai tôi. Chỉ tên nào có `đỉnh%` thấp mới cần bước này —
   `Samael` và `Michael` thì đừng chạm.
3. **Cổng neo tên**: cửa sổ ghép một-token cho neo nhiều-token là lỗi thấy rõ; `awakened` so với
   `awaken` là chặt vô ích. Cả hai nằm trong `asr.py` (file khoá) nên đợi ranh giới lô, và đợi
   bước 1–2 trước, vì sửa cổng khi dạng đọc còn tệ là làm mất chính cái cảnh báo đang đúng.

Đừng làm bước 3 trước bước 1. `Jake` là ca mà cổng nói **thật**.

## Nửa số đoạn được sửa trong sách đọc tên theo CHỮ VIẾT, không theo cách đọc đã ghim (2026-09-11, 16:45)

Đo trên chính cuốn sách đã ghép (92 chương, theo `manifest.json`):

```
ứng viên được đề cử (đoạn đã qua sửa):   716
  đọc theo cách đọc ghim  (locked_spoken_v1)   368
  đọc theo CHỮ VIẾT       (source_spelling_v1) 348   = 48%
tên bị đổi cách đọc nhiều nhất:  Jake 79 · Michael 35 · Spirit 31 · Will 20 · Apex 19 · Willem 16 · Alice 13
```

Cơ chế, đọc từ chương 084 đúc lại: bản thu đầu đọc `I-xờ-hờ-ta-ra` (cách đọc ghim), **qua** cổng
nhịp (12,47 kt/s — dưới sàn chữ, 4,99 âm tiết/giây — bản vá âm tiết cứu đúng như dự đoán), rồi
chết ở cổng **neo tên** trên cả hai đường phiên; vòng sửa "rõ tiếng" sinh một ứng viên đọc theo
chữ viết `Ishtara`, Whisper nghe được, và ứng viên ấy được đề cử. Chương lên sách với thành phố
đọc khác mọi chương kia.

Đây là *cùng một* hiện tượng với 89 dạng nghe của `Jake` hôm qua, nhìn từ phía đề cử: cổng neo
tên là một bài **chính tả** mà cách đọc chuyển tự không bao giờ đậu
([LOCKED_NAME_ANCHOR_IS_A_SPELLING_TEST.md](LOCKED_NAME_ANCHOR_IS_A_SPELLING_TEST.md)), nên
vòng sửa đổi cách đọc để đậu — và làm thế ở **gần một nửa** số đoạn nó chạm tới. Người nghe nghe
`Giếch` ở đoạn này và `Jake` ở đoạn kế, tuỳ Whisper trượt ở đâu.

Trong 348 đoạn ấy, **41** có bản anh em đọc-theo-ghim chỉ hỏng vì neo tên và **còn nguyên file
WAV** — đổi lại đề cử được ngay, không cần GPU. 307 đoạn còn lại: xem mục kế, đang đếm lý do.

### Đếm xong: cả 348 bản đọc-theo-ghim chỉ hỏng vì neo tên, và còn nguyên file (17:00)

```
348 bản đọc-theo-ghim thua bản đọc-theo-chữ-viết trong sách
  → 696 phép kiểm ASR (beam + greedy), verdict = fail, mã duy nhất: ASR_LOCKED_NAME_ANCHOR_MISMATCH
  → 348 / 348 chỉ hỏng vì neo tên; nhịp qua, phiên bản khớp phần còn lại
  → 348 / 348 còn file WAV (307 bị "invalid: incumbent checksum changed" khi bản kia được đề cử,
     41 còn "dual_failed")
```

Nghĩa là cách đọc ghim **đúng và dùng được ở mọi trường hợp**; nó thua một bài chính tả mà
Whisper không bao giờ chấm đậu cho chuyển tự, rồi vòng sửa đổi cách đọc để đậu. Học thuyết của
dự án đã nói `ASR_LOCKED_NAME_ANCHOR_MISMATCH` là mã máy được chấp nhận có ghi sổ *ở tầng đoạn* —
nhưng ở tầng ứng viên, vòng sửa "rõ tiếng" chạy **trước** và thay cách đọc, nên đường chấp nhận
không bao giờ tới lượt.

**Hướng sửa (bản vá cho ranh giới kế, file khoá):** khi ứng viên đọc-theo-ghim chỉ hỏng vì họ neo
tên, **đề cử nó kèm phán quyết máy** thay vì sinh ứng viên đọc-theo-chữ-viết. Neo tên không nói
bản thu hỏng; đổi cách đọc thì làm người nghe mất tên nhân vật. Và một lượt **đề cử lại** cho 348
đoạn đã lên sách — không cần GPU, cả hai đường phiên đã có sẵn — rồi ghép lại các chương chạm
tới. `promote_segment_candidate` hiện chỉ nhận `dual_passed`/`promoted`, nên cần một đường mới ở
tầng database, kiểm bốn điều kiện từ chính dữ liệu như `patch_finished_take_beats_a_cut_off_one`.

## Một cái tên VIẾT nhiều kiểu - phía trước micro (2026-09-20)

Phần trên là ASR: cùng một chữ, Whisper nghe ra nhiều kiểu. Có một lỗi song sinh sớm hơn hẳn trong
mạch chạy: **model phân tích tự viết sai tên**, và mỗi cách viết sai thành một NHÂN VẬT RIÊNG có
giọng riêng, rồi sổ nhân vật mang nó qua mọi lô sau.

`fold_to_source_spelling` đã chặn phần lớn: nhãn nào **vắng mặt hẳn** trong cả cuốn sách thì trỏ về
cách viết CÓ trong sách, nếu lệch đúng một ký tự. Đo trên lô 8, 9, 10 - 187 nhãn người nói, 18 vắng
mặt hẳn, luật cũ gom 5 (`ANICK`/`ANNIK` -> `ANNICK`, `ARTEIL`/`ARTEL` -> `Artil`, `BEAUTE` ->
`Beate`). Hai nhãn lệch **hai** ký tự thì sống sót:

| nhãn | câu | trong sách | thật |
|---|---|---|---|
| `ARTELI` | 1 | 0 lần ("Artil" 88 lần) | Artil - và `ARTEL`, `ARTEIL` đã gom về đấy rồi |
| `JOCLEYN` | 2 | 0 lần ("Jocelyn" có) | Jocelyn |

Nới lên hai ký tự (`patch_a_name_two_letters_off_still_belongs_to_its_owner.py`, ghim ranh giới 10)
gom đúng hai nhãn ấy, không kéo theo gì khác: 13 nhãn vắng mặt còn lại không có đích nào ở khoảng
cách 2 (`PLANTAGENET_ULRICH`, `GRAND ARCANIEST`, `PROFESSOR`, `BIG CHIEF`, `EMMA`, `HENSION`...).

Hai chốt giữ nó khỏi đoán bừa: đích phải **duy nhất** sau khi bỏ dấu và hạ chữ (một nhãn cách 2 với
hai cái tên khác nhau thì không gom), và nhãn phải dài từ 5 ký tự. Điều kiện gốc không đổi: **nhãn
thua phải vắng mặt hẳn trong cả cuốn sách** - tác giả chưa từng viết nó thì nó không phải nhân vật,
nên đây không bao giờ là chuyện gộp hai nhân vật thật.
