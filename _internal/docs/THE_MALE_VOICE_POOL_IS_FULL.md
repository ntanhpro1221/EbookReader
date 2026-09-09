# Kho giọng nam đã đầy ở lô 1 trên 16

Đo ngày 2026-09-09 trên `lo01b` (chương 000..029, 26/30 chương đã xuất bản):

```
nhân vật có tên thực sự nói :  20   (nam 14, nữ 6)
chỗ có thể cấp cho nhân vật :  nam 14, nữ 27
```

**Mười bốn nhân vật nam có tên, mười bốn chỗ.** Ở chương 029 của một cuốn 478 chương.

## Vì sao chỉ có 14 chứ không phải 98

Catalog có 14 preset, nhưng phần lớn không tới được tay nhân vật:

```
14 preset trong catalog
 −1  Xuân Vĩnh          EXCLUDED_PRESETS
 −2  giọng miền Trung   CASTING_REGIONS chỉ nhận Bắc và Nam
 −…  giọng tin tức      style != STYLE_NEWS
 =   nam 3, nữ 4  được phép đúc
 −1  Phạm Tuyên         "A character never shares the narrator's preset"
                        (character_registry.py:406)
 =   nam 2 preset  ×  7 bậc formant  =  14 giọng nam cho nhân vật
     nữ  4 preset  ×  ~7 bậc         =  27 giọng nữ
```

Bậc formant không phải lúc nào cũng đủ bảy: `formant_variants_for_preset` kẹp thang vào giới
hạn giải phẫu của chính preset ấy, nên Ngọc Linh chỉ có 6, và bậc 0,87 của Thanh Bình bị kẹp
thành 0,898 (thanh quản 16,9 cm — dài nhất trong các preset nam, gần như hết chỗ đi trầm hơn).

## Đồng nhất thức, không phải ước lượng

```
người nói bằng giọng nam nhân vật : 16   (14 có tên + 2 NPC theo chương)
giọng nam thực sự được tạo        : 13
thiếu                             :  3
va chạm đo được                   :  3   ← khớp đúng
```

Ba cặp dùng chung một `voice_key` y hệt nhau:

```
preset_thanh_binh_f104_p-04   CHA     + SỐ BA
preset_thai_son_f116_p+00     NOAH    + SỐ BẢY
preset_thai_son_f093_p+00     SỐ BỐN  + SỐ NĂM
```

## Thiệt hại thật của lô 1 thì nhỏ — nói cho đúng

Người nghe nghe từng chương một, nên hai nhân vật không bao giờ xuất hiện cùng chương mà trùng
giọng thì gần như vô hại:

```
CHA  ch 012   |  SỐ BA   ch 023   ->  không cùng chương
NOAH ch 003,011 | SỐ BẢY ch 023   ->  không cùng chương
SỐ BỐN ch 023 |  SỐ NĂM ch 023    ->  CÙNG CHƯƠNG 023
```

Nên hỏng thật chỉ có **một chỗ**: trong chương 023, SỐ BỐN và SỐ NĂM nói bằng cùng một giọng,
tổng cộng ba câu, cả hai đều là nhân vật phụ. Đó không phải một tai hoạ và tôi suýt viết nó
thành tai hoạ.

Cái đáng lo không phải lô 1 mà là **tốc độ**: kho đã đầy 14/14 sau lô đầu tiên trong mười sáu.
Từ lô 2 trở đi mọi nhân vật nam mới đều rơi vào chỗ đã có người, và xác suất hai người cùng
chương trùng giọng tăng theo từng lô. Nữ còn rộng (6/27), nên đây là chuyện riêng của giọng nam.

## Một chỗ trống chưa được dùng — nhưng nó chỉ gỡ được 1 trong 3

`Thanh Bình` có bảy bậc formant, lô 1 chỉ dùng sáu; bậc `0,898` chưa bao giờ được cấp cho ai.
Bộ cấp phát bỏ sót một chỗ trống trong khi ba cặp phải dùng chung.

Nhưng đừng phóng đại: 16 người đòi 14 chỗ thì **ít nhất hai va chạm là không tránh được**, kể
cả khi bộ cấp phát hoàn hảo. Chỗ trống ấy giải thích được nhiều nhất một phần ba vấn đề.

(`preset_thanh_binh_f100_p-07` trông như một biến thể pitch dùng để phân biệt người, nhưng
không phải: −4 là register hiệu chỉnh của preset, −3 nữa là `age_pitch` của một người già. Nó
là một nhân vật khác, không phải một nấc đa dạng hoá.)

## Hai hướng nới đã bị đo bác bỏ — đừng đi lại

**Pitch.** `CHARACTER_PITCH_VARIANTS = (0,−1,1,−2,2)` có sẵn và gần như không được dùng làm
trục đa dạng. Lý do đã đo: một người nghe so cùng một câu từ −6 đến +6 nửa cung, F0 từ 106 Hz
đến 206 Hz, và **nghe ra cùng một người suốt**. Dịch F0 đọc thành "cùng người, khác trạng
thái", không thành người khác. Nới pitch chỉ làm dài bảng chứ không thêm người.

**Nới biên formant.** `FORMANT_RATIO_MIN/MAX` là 0,80–1,20, nhưng bậc thật bị kẹp bởi
`PRESET_VOCAL_TRACT_CM` đo bằng Praat trên chính clip preview của từng preset. Nới biên chung
là kéo giọng nam ra ngoài dải người, và ghi chú của người trước nói thẳng cái giá: "a voice
that sounds like a different person" đổi thành "one that sounds like no person at all".

## Hướng còn lại: NPC theo chương đang tranh chỗ với nhân vật có tên

Hai trong mười sáu người đòi chỗ là `NPC_LOCAL` — `NGƯỜI CAO KỀU` (chương 019) và
`NGƯỜI TRONG ĐÁM ĐÔNG` (chương 013). Mỗi NPC ấy sống đúng một chương rồi biến mất, nhưng nó
chiếm một chỗ trong kho 14 y như một nhân vật đi suốt cuốn sách.

(Con số trong `NPC_LOCAL::C00020::…` là **id** của chương chứ không phải số chương; đọc thẳng
nó ra là lệch một. `voice_pool_pressure.py` join sang `chapters.title` nên nó đúng.)

Người trước **đã từng** cho NPC một kho rộng hơn (thêm giọng miền Trung) rồi bỏ đi, với lý do
ghi lại nguyên văn: *"NPCs used to reach a wider pool that added the Central presets; that pool
is gone with them, so the distinction would now only be a parameter that never changes
anything."*

Câu ấy **đúng lúc nó được viết** — khi kho nhân vật có tên còn chỗ, cho NPC đi đâu cũng không
đổi gì. Bây giờ kho đầy, nên nó đổi. Đây là một quyết định đúng bị hoàn cảnh làm cho sai, chứ
không phải một lỗi; và nó chỉ lộ ra vì lô 1 đã chạy thật.

Chưa vá. Xếp vào [OPTIMISATION_QUEUE.md](OPTIMISATION_QUEUE.md); `voice_catalog.py` và
`character_registry.py` đều nằm trong `QUALITY_IMPLEMENTATION_FILES`, nên phải đợi ranh giới lô.

## Cách đo lại

```bash
python scripts/voice_pool_pressure.py <project>
```
