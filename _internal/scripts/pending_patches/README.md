# Bản vá đã kiểm, chờ máy rảnh mới ghi vào file bị khoá

Năm script trong thư mục này sửa **file nằm trong `QUALITY_IMPLEMENTATION_FILES`**. Ghi vào
chúng lúc đang có lượt chạy sẽ đổi `quality_implementation_hash()` và lượt `resume` kế tiếp bị
từ chối — nên chúng được viết và **kiểm xong trong một bản sao cách ly**, chờ áp.

Cách áp, khi và chỉ khi không có lượt chạy nào đang bay:

```
python scripts/pending_patches/patch_quote_recovery.py  "D:/Novels/Ebook Reader/_internal"
python scripts/pending_patches/patch_quote_tests.py     "D:/Novels/Ebook Reader/_internal"
python scripts/pending_patches/patch_test2.py           "D:/Novels/Ebook Reader/_internal"
python scripts/pending_patches/patch_short_anchor.py    "D:/Novels/Ebook Reader/_internal"
python scripts/pending_patches/patch_laugh.py           "D:/Novels/Ebook Reader/_internal"
```

Thứ tự có ý nghĩa: `patch_quote_tests.py` viết một test mà `patch_test2.py` viết đè lại (bản
đầu escape sai). Mỗi script `assert` chuỗi gốc trước khi thay, nên áp nhầm thứ tự hay áp hai
lần thì nó dừng chứ không làm hỏng.

## Cái gì và vì sao

| script | file | đổi gì |
|---|---|---|
| `patch_quote_recovery.py` | `text_processing.py` | Ngoặc kép mở mà không đóng **không còn ném lỗi**. Bộ chia đoạn đóng nó ở cuối đúng đoạn gây lỗi rồi chia lại. |
| `patch_quote_tests.py` + `patch_test2.py` | `tests/` | Thay test khẳng định hành vi cũ bằng 5 test của hành vi phục hồi. |
| `patch_short_anchor.py` | `pipeline.py` | Neo tên trên đoạn **dưới 10 ký tự** không còn chặn chương. |
| `patch_laugh.py` | `text_processing.py` | `Ahaha` được nhận là tiếng cười. |

## Đã kiểm những gì

- **478/478 chương** chia đoạn được **mà không sửa một chữ nào trong nguồn**, 58.258 segment.
  Đúng 8 chương phải phục hồi, và trên chương 019 thuật toán khoanh đúng đoạn 170 (dòng 339) —
  đoạn tôi đã tìm ra bằng tay — chứ không đụng vào lời thề sáu dòng ở đoạn 155–160.
- **99 test xanh** trong bản sao: `test_text_processing_safety.py`, `test_pain_cry_vocalisation.py`,
  `test_spoken_symbols.py`, cộng cả nhóm 11 file có dính bộ chia đoạn (exit 0).
- `normalize_vocalizations_for_tts` **không đổi**: `"Hahaha!"` vẫn ra `"Ha ha ha!"`, `"Ahaha!"`
  vẫn giữ nguyên. Pattern mới chỉ dùng cho phép kiểm, vì chỗ viết lại đếm số lần lặp bằng độ
  dài chuỗi và một nguyên âm đứng đầu sẽ làm nó đếm dư.

## Cái gì CHƯA xong

Việc "không cần tai người" mới xong một phần. Trong 6 đoạn chặn 4 chương của alpha.55:

| đoạn | dài | mã | sau khi vá |
|---|---|---|---|
| `"Juli!"` | 0,56s | `ASR_LOCKED_NAME_ANCHOR_MISMATCH` | **hết chặn** |
| `"Juli,"` | 0,56s | `ASR_LOCKED_NAME_ANCHOR_MISMATCH` | **hết chặn** |
| `"...Ha! Ahaha! Á á! Haha!"` | 3,68s | `ASR_MISMATCH_UNRESOLVED` | **hết chặn** (là tiếng cười) |
| `"Rồi, rồi,"` | 1,92s | `ASR_MISMATCH_UNRESOLVED` | chưa rõ — cần xem `_segment_has_non_asr_failure_evidence` |
| `"...Thằng ranh xấc xược!"` | 1,52s | `ASR_MISMATCH_UNRESOLVED` | **vẫn chặn** |
| `Hỏa Cầu (Fireball) … \|\| Sương Giá` | 19,96s | `ASR_LOCKED_NAME_ANCHOR_MISMATCH` | **vẫn chặn — đúng.** Chủ sách xác nhận đoạn này đọc sai. |

Đoạn cuối *phải* vẫn chặn: đó là bằng chứng bản vá không hạ chuẩn ở chỗ phép kiểm còn nhìn được.
