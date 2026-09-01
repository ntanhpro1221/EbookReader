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
