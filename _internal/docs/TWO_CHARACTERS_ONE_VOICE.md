# Hai nhân vật một giọng — và kho giọng **không** phải thủ phạm

Lô 1 có ba cặp nhân vật có tên dùng chung đúng một `voice_key`:

```
preset_thanh_binh_f104_p-04   CHA     + SỐ BA     không cùng chương
preset_thai_son_f116_p+00     NOAH    + SỐ BẢY    không cùng chương
preset_thai_son_f093_p+00     SỐ BỐN  + SỐ NĂM    CÙNG CHƯƠNG 023
```

Chỉ cặp thứ ba là hỏng thật: người nghe nghe từng chương một, nên hai người không bao giờ gặp
nhau mà trùng giọng thì không ai phân biệt được và cũng không ai cần phân biệt. Trong chương
023, SỐ BỐN và SỐ NĂM nói bằng cùng một giọng, tổng ba câu.

## Kết luận đầu tiên của tôi sai, và cái sai đáng giữ lại

Tôi đo được "14 nhân vật nam có tên, đúng 14 chỗ có thể cấp" và đặt tên tài liệu này là *"Kho
giọng nam đã đầy"*. Số học thì đúng:

```
14 preset trong catalog
 −1  Xuân Vĩnh          EXCLUDED_PRESETS — một người nghe Việt phán, không bàn lại
 −2  giọng miền Trung   CASTING_REGIONS — sai thanh điệu trên từ thường:
                        "khốn kiếp" → "khôn kiêp", và thanh điệu mang nghĩa
 −…  giọng tin tức      style != STYLE_NATURAL/STORY
 =   nam 3 preset, nữ 4
 −1  Phạm Tuyên         nhân vật không bao giờ dùng chung preset với người dẫn chuyện
 =   nam 2 × 7 bậc formant = 14 giọng   |   nữ 4 preset = 27 giọng
```

Nhưng **"đầy" là kết luận sai từ số đúng**, vì nó so tổng cast với tổng kho, trong khi ràng
buộc thật là theo chương.

## Con số thật sự quyết định

```
nhân vật nam có tên, cả lô 1          : 17
chương đông nhất có bao nhiêu người nam:  7   (chương 023)
NPC_LOCAL nhiều nhất trong một chương  :  1 nam, 2 nữ
```

Dựng đồ thị đồng hiện — mỗi nhân vật một đỉnh, nối hai người nếu họ cùng nói trong một chương —
rồi tô màu tham lam:

```
nam :  17 người, chương đông nhất 7  ->  cần  7 màu   (kho 14)
nữ  :   8 người, chương đông nhất 3  ->  cần  3 màu   (kho 27)
```

Bảy cũng là **cận dưới**: chương 023 có 7 người nam cùng nói, tức một clique bảy đỉnh, nên
không cách tô nào dùng ít hơn bảy. Tham lam chạm đúng tối ưu.

**Kho gấp đôi cái cần dùng.** Cả ba va chạm của lô 1 đều tránh được, không cần thêm một preset
nào, không cần nới một biên nào.

## Vậy hỏng ở đâu — hai chỗ, và chỗ thứ hai là bug

Đếm người trên từng preset của lô 1:

```
preset            người   bậc có sẵn   giọng đã dùng
  Thái Sơn           9         7            7      <- quay vòng 2 lần
  Thanh Bình         7         7            6      <- vừa đủ mà vẫn thiếu một
  Đoan Trang         3         7            3
  Trúc Ly            3         7            3
  Ngọc Linh          2         6            2
  Phạm Tuyên         1         7            1      (người dẫn chuyện)
```

### Chỗ thứ nhất: thang biến thể là một vòng modulo

```python
variants = formant_variants_for_preset(name)
formant_ratio = variants[self.variant_usage[name] % len(variants)]
self.variant_usage[name] += 1
```

Người thứ tám trên một preset bảy bậc **quay về bậc một**, và không có gì kiểm tra xem bậc ấy
đã có chủ chưa. Thái Sơn nhận 9 người nên quay hai lần — hai va chạm.

Chín người trên bảy bậc thì hai lần dùng lại là **không tránh được**, nên phần này của vấn đề
không phải lỗi mà là hết chỗ trên preset ấy.

### Chỗ thứ hai: `reserve()` đánh dấu nhầm ô

Thanh Bình nhận đúng 7 người và có đúng 7 bậc, nhưng chỉ **6** giọng ra đời — một bậc (`0,898`)
không bao giờ được cấp cho ai, trong khi `f104` được phát cho hai người (CHA và SỐ BA).

Vì `reserve()` chỉ nhận **tên preset**:

```python
def reserve(self, preset_name: str) -> None:
    for pool in self.pool_usage.values():
        pool[name] += 1
    self.variant_usage[name] += 1        # tăng bộ đếm, không đánh dấu bậc nào
```

Một giọng đã ghim làm bộ đếm nhích lên một, tức **nhảy qua một bậc bất kỳ** — không phải bậc
mà nó thật sự đang giữ. Bậc bị nhảy qua thành bỏ phí, còn bậc nó đang giữ vẫn nằm trong vòng
quay và được phát lại.

Thông tin cần thiết **có sẵn ở chỗ gọi** và bị vứt đi: `_reserve_pinned_voices` cầm cả dòng
`voice_profiles` — có `formant_ratio`, có `voice_key` — rồi gọi
`allocator.reserve(str(row["preset_name"]))`.

Đây là một va chạm **tránh được hoàn toàn**, không cần thêm giọng nào.

### Và chỗ thứ ba, chỉ lộ ra sau khi vá hai chỗ trên

Kể cả cấp phát hoàn hảo, 16 người đòi 14 chỗ vẫn còn **hai** lần phải dùng chung. Lúc ấy câu
hỏi đúng không còn là "có dùng chung không" mà là "**ai** dùng chung với ai" — và bộ cấp phát
không có dòng nào biết chương nào có ai. Lô 1 được 2 trên 3 cặp "không cùng chương" là **may**,
không phải thiết kế.

## Hai hướng nới đã bị đo bác bỏ — đừng đi lại

**Pitch.** `CHARACTER_PITCH_VARIANTS = (0,−1,1,−2,2)` có sẵn và gần như không được dùng làm trục
đa dạng. Một người nghe so cùng một câu từ −6 đến +6 nửa cung, F0 từ 106 Hz đến 206 Hz, và
**nghe ra cùng một người suốt**.

**Nới biên formant.** Bậc thật bị kẹp bởi `PRESET_VOCAL_TRACT_CM` đo bằng Praat trên chính clip
preview của từng preset. Nới biên chung là kéo giọng ra ngoài dải người.

**Trả giọng miền Trung lại cho NPC.** Tôi định đề xuất chính điều này rồi tự bác: NPC cũng có
lời để người nghe nghe, nên đổi một va chạm giọng lấy một lỗi thanh điệu là đổi lỗ.

Ba hướng ấy đều nhắm vào "kho nhỏ quá". Kho không nhỏ.

## Đã sửa một nửa: khi buộc phải chia lại, đừng đổi giọng cả hai người

Luật cũ trong `port_casting.py`: hai nhân vật dùng chung một giọng thì **bỏ pin của cả hai**, vì
*"picking a winner has no evidence"*. Nửa đầu của lý lẽ ấy vẫn đúng — mang cả hai sang là làm va
chạm thành vĩnh viễn. Nửa sau thì không: bỏ cả hai là **đổi hai giọng để chữa một va chạm**.

Đo tại ranh giới lô 1 → lô 2: ba cặp va chạm làm **sáu** nhân vật mất giọng, trong đó CHA và
NOAH đều là nhân vật chính. Luật mới giữ người được nghe nhiều hơn, nên chỉ ba người bị đúc lại
và cả ba là người ít lời hơn trong cặp của mình:

```
GIỮ   CHA (4 câu) thắng preset_thanh_binh_f104_p-04; đúc lại SỐ BA
GIỮ   NOAH (8 câu) thắng preset_thai_son_f116_p+00; đúc lại SỐ BẢY
GIỮ   SỐ BỐN (đã ghim) thắng preset_thai_son_f093_p+00; đúc lại SỐ NĂM
```

**Thứ hạng mất hai lần thử mới đúng, và cả hai lần sai đều đáng giữ lại.**

Lần đầu chỉ so **số câu trong lô này**. Ca alpha.56 bác ngay: THEOSBANE im lặng ở lô ấy nên 0
câu, thua SAMAEL 1 câu — đúng lỗ hổng mà một bài test khác tồn tại để chặn.

Lần hai xếp **"có pin" lên trên số câu**. Chạy thử trên dữ liệu thật thì `SỐ BA` (phụ, 2 câu)
thắng `CHA` (chính, 4 câu), chỉ vì SỐ BA tình cờ giữ pin từ lần chuyển trước. Không có cột nào
phân biệt pin của **người** với pin của **script**: `locked=1` đánh dấu *giới tính* do người
chọn, không phải giọng.

Thứ đáng cân là *người nghe đã quen giọng ấy tới mức nào*. Bản đầu của mục này viết rằng số đo
ấy là `mention_count` "vì nó cộng dồn qua các lô". **Sai.** `upsert_character` ghi đè nó bằng số
câu của lô hiện tại — đo 2026-09-10: SAMAEL 10 → 99 → 19, THỦ LÃNH 178 → 111 → 32. Luật chạy
đúng ở ranh giới lô 2 → 3 nhờ may; ở lô 3 → 4 thì KANG (19 câu, mới) **hoà** SAMAEL (19 theo sổ
sai, 128 theo sự thật) và chỉ nấc phá hoà cuối cùng cứu nhân vật chính khỏi đổi giọng.

Số đo đúng là **tổng câu thoại qua mọi lô**, giữ trong sổ `character_exposure` do
`scripts/backfill_exposure.py` dựng lại từ cả chuỗi lô ở mỗi ranh giới (bảng nằm ngoài SCHEMA
nên phân tích không ghi đè được). Với sổ ấy SAMAEL là 109 chứ không phải 19, và THỦ LÃNH là 303
đã gộp cả bản rơi dấu. Không có sổ thì `port_casting` lùi về `mention_count` **và nói ra là đang
lùi**. Hoà tuyệt đối thì quay về luật cũ: bỏ cả, vì lúc ấy đúng là không có bằng chứng.

Luật này **chỉ an toàn nhờ bản vá `reserve()`**: người thắng giữ giọng, và `reserve()` giờ đánh
dấu đúng bậc formant ấy, nên người thua chắc chắn được cấp bậc khác thay vì có thể quay vòng về
đúng bậc vừa bị giữ.

## Hướng còn lại: cho bộ cấp phát biết ai cùng chương

Khi phải cho hai nhân vật dùng chung một giọng, chọn cặp **không cùng chương**. Đây là tô màu
đồ thị đồng hiện, và dữ liệu đồng hiện đã có sẵn trong `segments` trước lúc đúc giọng, vì phân
tích chạy xong cả sách rồi mới tới `build_registry_and_cast`.

Chưa vá. `voice_catalog.py` và `character_registry.py` đều nằm trong
`QUALITY_IMPLEMENTATION_FILES`, nên phải đợi ranh giới lô.

**Cái sẽ bó trước, và cái đáng canh:** không phải tổng số nhân vật mà là **chương đông nhất**.
Hôm nay là 7 trên 14. Nếu về sau có chương nào 15 người nam cùng nói thì lúc ấy kho mới thật sự
hết, và lúc ấy ba hướng nới ở trên mới đáng bàn lại.

## Cách đo lại

```bash
python scripts/voice_pool_pressure.py <project>
```

## Đo lại ở quy mô cuốn sách (2026-09-12, 03:45)

Tài liệu này viết khi mới có lô 1 (17 nhân vật nam). Sách giờ 118 chương, 61 cái tên — và **con số
quyết định vẫn là con số này nói**, không phải tổng kho:

    nhân vật trên preset nam, cả sách     : 39      (kho 14 slot)
    nhân vật trên preset nữ               : 23      (kho 27 slot)
    chương đông nhất, người nam           :  7      chương 023
    chương đông nhất, người nữ            :  5      chương 065 và 078

Tổng vượt kho gần ba lần, nhưng ràng buộc theo chương vẫn còn chỗ gấp đôi. Đúng như tài liệu này
kết luận từ đầu: *"đầy" là kết luận sai từ số đúng*.

Kiểm lại việc dùng chung trên toàn sách, bằng phép giao ĐÚNG (chương mà mỗi người dùng **chính
giọng ấy**, không phải chương mà họ có mặt — bản đo đầu của tôi sai đúng chỗ này và báo sáu cặp giả):

    92  cặp hai người dùng chung một giọng qua cả sách
     1  cặp cùng chương: SỐ BỐN + SỐ NĂM, chương 023 — vẫn đúng cặp tài liệu này chỉ ra ở lô 1

**Sửa lại 10:00 ngày 12-09: là 2, không phải 1.** Phép đo trên chỉ đếm 61 cái *tên* và bỏ NPC theo
chương. Quét lại 118 chương đang ghép bằng chính `voice_pool_pressure` trên 38 project thắng, chỉ giữ
chương mà project ấy là bản thắng: **2** va chạm cùng chương — 023 (SỐ BỐN + SỐ NĂM) và **071 (KANG +
NPC THẰNG ĐIÊN, cùng `thanh_binh_f100_p-04`, mỗi người một câu)**. Bản 071 đúc lại 22:52 ngày 10-09,
trước bản vá 'một bậc nhớ mọi người giữ nó', và KANG không có pin nên bị rút thăm trúng đúng bậc của
NPC. 023 đang được đúc lại đêm nay; 071 vào danh sách ranh giới 6 → 7. Bài học: người nghe không phân
biệt tên với NPC — đếm va chạm thì phải đếm cả hai, và công cụ của dự án đã làm đúng từ đầu.

Cặp ấy chưa từng được đúc lại vì ranh giới lô 1 → 2 chưa có `--recast auto`. Đã thêm `1:023` vào
ranh giới lô 5 → 6 (2026-09-12 02:56), nên sau đêm ấy cuốn sách không còn va chạm cùng chương nào
mà ta biết mà vẫn để đó.
