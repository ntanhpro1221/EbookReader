# Lỗi "source-spelling pronunciation anchors drifted from locked anchors"

## Triệu chứng

Run dừng hẳn với `RuntimeError: source-spelling pronunciation anchors drifted from locked
anchors`, ném từ `_segment_candidate_pronunciation_delivery` khi cấp ứng viên cho vòng
repair clarity. Chương đang xử lý **không bao giờ publish được**.

Trong `VERSIONS.md` lỗi này đã được ghi là **blocker số 1** với 7,5% segment fail và
"với 915 chapter thì không chapter nào từng được publish".

## Nguyên nhân: một cặp tự mâu thuẫn ship cùng một commit

Commit `f5c8dd2` (2026-08-24, *"harden analysis and ASR repair provenance"*) thêm **cả hai**
thứ sau, và chúng loại trừ nhau:

**1. Điều kiện tạo anchor bất đối xứng** (`tts.py`, trong `spoken_text_with_anchors`):

```
not replacement_anchor_tags
and locked_english_pronunciation
and (canonical_replacement != matched_text
     or pronunciation_delivery_variant == PRONUNCIATION_DELIVERY_SOURCE)
```

Vế `or ... == SOURCE` khiến biến thể **source** tạo anchor **luôn luôn**, còn biến thể
**locked** chỉ tạo khi cách đọc khác chữ viết.

**2. Phép kiểm đòi hai biến thể có cùng tập anchor** (`pipeline.py`,
`_segment_candidate_pronunciation_delivery`): `source_identity != locked_identity` ⇒ ném lỗi.

Nên với bất kỳ mục phát âm nào có `spoken_form == surface` — tức cách đọc **chính là** chữ
viết — locked sinh **0 anchor**, source sinh **1 anchor**, identity lệch, và phép kiểm ném
lỗi. Tất định, không phải điều kiện đua.

## Vì sao nó phổ biến đến thế

Bảng phát âm của một sách game-LitRPG đầy thuật ngữ tiếng Anh được giữ nguyên cách đọc:

| surface | spoken_form |
|---|---|
| `Skill Card` | `Skill Card` |
| `Shadow Step` | `Shadow Step` |
| `Spell Card` | `Spell Card` |
| `Item Card` | `Item Card` |
| `Debuff` | `Debuff` |

Đo trên project thật: **18/43 mục** phát âm có `spoken_form == surface`, và
**17/79 segment (21,5%)** rơi vào tình trạng ném lỗi.

## Cách tái hiện mà không cần sinh audio

Điểm quan trọng cho người sau: điều kiện lỗi **hoàn toàn tĩnh**. Nó chỉ phụ thuộc văn bản
segment và bảng phát âm, không phụ thuộc audio, seed, hay bất cứ thứ gì ở giai đoạn TTS.

```python
_, locked = coordinator.spoken_text_with_anchors(row, pronunciation_delivery_variant=LOCKED)
_, source = coordinator.spoken_text_with_anchors(row, pronunciation_delivery_variant=SOURCE)
# identity = (pronunciation_id, occurrence, source_start, source_end, surface,
#             normalized_surface, matched_surface, source, canonical_spoken_form)
```

Nhờ vậy có thể quét cả sách trong vài giây để biết chương nào sẽ chết, thay vì chạy TTS
hàng chục phút rồi mới gặp.

## Bẫy khi chẩn đoán: chọn nhầm segment sẽ kết luận ngược

Segment đầu tiên tôi thử (seq 23) **PASS** phép kiểm, vì nó tình cờ chỉ chứa `Epic` và
`Legendary` — hai mục có cách đọc **khác** chữ viết, nên cả hai biến thể đều tạo anchor và
identity khớp. Suýt nữa kết luận là chẩn đoán sai.

Bài học: khi một điều kiện chỉ kích hoạt với **một lớp con** của dữ liệu, một mẫu thử không
chứng minh được gì theo chiều phủ định. Phải quét toàn bộ rồi mới nói.

## Hướng sửa

Bỏ vế `or pronunciation_delivery_variant == PRONUNCIATION_DELIVERY_SOURCE`, để hai biến thể
tạo anchor theo cùng một điều kiện.

Lý do chọn hướng này thay vì nới lỏng phép kiểm: khi `canonical_replacement == matched_text`
thì hai biến thể **cho ra văn bản đọc y hệt nhau**. Một anchor ghi lại "ở đây ta cố ý đọc
theo chữ viết" không mang thông tin gì, vì đọc theo cách đã khóa cũng ra đúng như thế. Không
có gì để phân biệt, nên không có gì để ghi.

Phép kiểm là thứ đúng và cần giữ: nó bảo vệ bất biến *"cùng một tên không đổi cách đọc"*.
Cái sai là dữ liệu đưa vào nó.

## Giọng trôi vì ghim bị rớt, và va chạm sinh ra từ đó

Đo 2026-09-08. `port_casting.py` mang casting sang lô sau bằng câu hỏi *"ai đã nói trong lô
này?"* — join `characters` với `segments` và `voice_profiles`. Câu hỏi ấy **bỏ sót nhân vật đã
ghim giọng mà im lặng ở lô đó**.

alpha.56: 38 nhân vật có `locked_voice_key`, **18** thực sự nói. 20 bị rớt — 14 là NPC cục bộ
theo chương (đúng phải rớt) nhưng **5 là nhân vật có tên**, trong đó có `THEOSBANE`, chính cái
tên chủ sách tự tay chọn cách đọc, và nó có mặt ở **156/478 chương**.

### Hậu quả đo được: một va chạm giọng

| | số ghim | giọng bị dùng chung |
|---|---|---|
| alpha.55 | 23 | **0** |
| alpha.56 | 38 | **1** — `THEOSBANE` và `SAMAEL` cùng `preset_thanh_binh_f093_p-04` |

Chuỗi nhân quả: `THEOSBANE` im lặng suốt chương 010–018 ⇒ ghim của nó bị rớt khi gieo alpha.56
⇒ bộ cấp phát không biết giọng ấy đã có chủ ⇒ giao cho `SAMAEL`.

### Đã sửa: hợp hai câu hỏi, và từ chối va chạm

Một câu hỏi thôi thì mất người, theo hai chiều ngược nhau:

| hỏi gì | mất ai |
|---|---|
| *ai đã nói ở lô này* | 20 nhân vật đã ghim mà im lặng (alpha.56) |
| *ai đang được ghim* | 15 nhân vật vừa được cấp giọng mà chưa ghim, gồm `ARTHUR` (alpha.55) — vì **bộ cấp phát không ghi `locked_voice_key`**, chỉ script này và lệnh `cast` mới ghi |

Nên hỏi cả hai, bản đã nói thắng khi bất đồng — ghim nói *đã quyết gì*, segment nói *đã nghe
gì*, và cái đã nghe mới là cái người nghe chấp nhận.

Và khi hai nhân vật cùng một giọng thì **không mang giọng ấy đi đâu cả**, để bộ cấp phát chia
lại. Đây đúng là luật script này vốn đã áp cho ca ngược (một nhân vật hai giọng): chọn bên
thắng nghĩa là quyết định ai đổi giọng mà không có bằng chứng nào.

### CHƯA sửa: lỗi sâu hơn

Bản vá trên chặn va chạm **lan sang lô sau**, nhưng không chặn va chạm **mới sinh ra**. Gốc rễ
là bộ cấp phát chỉ `reserve()` giọng của nhân vật **có trong danh sách casting của lô này**.
Một nhân vật đã ghim mà im lặng thì không nằm trong danh sách ấy, nên giọng của nó vẫn được coi
là còn trống.

Sửa đúng là ở `character_registry.py`: reserve **mọi** `locked_voice_key` trong bảng
`characters`, kể cả của nhân vật không nói câu nào ở lô này. Chưa làm vì file ấy bị khoá và
alpha.57 đang chạy.
