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
