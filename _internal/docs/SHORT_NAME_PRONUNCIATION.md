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

## Cách xử lý đã dùng

Người nghe chọn: **đọc nguyên văn**. Chốt bằng một dòng khoá cứng:

```sql
INSERT INTO pronunciations
  (surface, normalized_surface, spoken_form, confidence, source, locked, created_at, updated_at)
VALUES ('Deck', 'deck', 'Deck', 1.0, 'listener_choice', 1, ...);
```

`locked=1` nên các pha sau không hỏi lại, và `source='listener_choice'` phân biệt rõ với
`english_name_transliteration` do máy sinh.

## Việc còn mở

Chưa có **đường chính thức để người nghe chốt cách đọc**. Lần này phải ghi thẳng vào SQLite,
mà đó là thứ tôi vốn tránh. Một lệnh CLI kiểu
`ebook-reader-headless pronounce <project> --surface Deck --spoken Deck` sẽ:

- biến việc chặn-cả-sách-vì-một-từ thành một thao tác một dòng
- ghi lại rằng lựa chọn đến từ người, không phải từ model
- tránh việc mở rộng chính sách đoán tự động, thứ mà bộ test đang cố ý ngăn

Đó là hướng đúng: giữ nguyên sự thận trọng của máy, và cho người một cái van.
