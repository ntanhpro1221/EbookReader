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

---

## Bổ sung 2026-09-07 23:50 — chia lô làm hỏng phân tích, và cách chặn

Chủ sách dặn: *"phân lô thế nào cũng được, đừng để phân tích bị sai do phân lô có vấn đề"*.
Tôi đi kiểm và **có vấn đề thật**.

Prompt phân tích mang một mục:

```
Nhân vật đã biết từ các phần trước:
- JULIANA; số lần đã gặp=55; gender đã biết=female
...
```

Mục ấy dựng từ `db.list_segments(...)` của **chính project đó** ([analysis.py:6557]). Một lô mới
là một project mới, chưa phân tích gì, nên mục ấy rỗng: `(Chưa có nhân vật đã biết)`. Mô hình
phải đoán lại giới tính và tên của một dàn nhân vật mà lô trước đã dựng xong.

### Lớn cỡ nào

Đo trên chính văn bản cuốn này — tên riêng Latin xuất hiện ≥5 lần, so theo 16 lô của
`plan_batches --hours 8`:

| lô | tên trong lô | đã thấy ở lô trước | % đã biết |
|---|---|---|---|
| 2 | 91 | 50 | 55% |
| 5 | 119 | 103 | 87% |
| 9 | 81 | 77 | **95%** |
| 15 | 145 | 128 | 88% |

**Từ lô 2 trở đi: 1.234/1.538 = 80% tên trong mỗi lô đã từng xuất hiện ở lô trước.**

> Một phép đo trước đó của tôi nói 6%, và nó **sai vì chọn nhầm cửa sổ**: nó so nhãn người
> nói giữa chương 000–009 và 010–018, tức đúng khúc mở đầu, nơi sách giới thiệu rồi bỏ nhân
> vật nhanh hơn bất cứ đâu. Lấy cả cuốn thì ra 80%.

### Ngữ cảnh câu trước/sau thì KHÔNG sao

Đã kiểm: `previous_text`/`next_text` chỉ lấy khi cùng `chapter_id`
([analysis.py:4944]). Cắt lô tại ranh giới chương không mất gì mà ranh giới chương chưa mất.
Nhóm segment cũng không vượt chương. Vậy chỉ có đúng một lỗ, là danh sách nhân vật.

### Vá

| script | file | đổi gì |
|---|---|---|
| — (đã áp) | `scripts/port_casting.py` | Mang thêm **tên, giới tính, số lần gặp**, không chỉ giọng. Lọc bỏ `NARRATOR`/`UNKNOWN`, `ANONYMOUS_*`, và NPC cục bộ theo chương — cái cuối vô nghĩa ở lô sau. |
| `patch_known_carry.py` | `analysis.py` | Danh sách "nhân vật đã biết" đọc cả bảng `characters`. Segment thắng nếu có cả hai: số đếm tự đo hơn số đếm được kể, và cộng vào là đếm trùng. |
| `patch_fakedb.py` | `tests/` | `FakeDB` có `list_characters`; 3 test mới. |

Mang sang **không khoá** (`locked=0`): `locked` nghĩa là *người* đã quyết và đè vĩnh viễn lên
mô hình. Đây là một cái máy kể cho cái máy sau nghe, mô hình vẫn phải được quyền sửa nếu sách
nói khác.

Đã kiểm: **613 test xanh** trong bản sao. Một test ghim rằng lô đầu tiên (và mọi lượt chạy một
mạch) có prompt **y hệt như trước** — thay đổi này không được đụng tới chúng.

---

## Bổ sung 2026-09-08 00:00 — bản thu tốt bị vứt vì ngữ điệu chưa hạ giọng

Chi tiết đầy đủ ở [WHY_A_GOOD_TAKE_GETS_THROWN_AWAY.md](../../docs/WHY_A_GOOD_TAKE_GETS_THROWN_AWAY.md).

Tóm tắt: `generation_endpoint_active` bật khi âm còn to ở cuối file, để bắt bản thu bị cắt
giữa chừng. Đo trên 956 bản thu bị loại: nó bật **14 lần, toàn bộ là câu kết thúc bằng dấu
phẩy hoặc dấu hỏi** — 0 lần trên dấu chấm (662 ca), dấu chấm than (202), hay chữ cái (35).
Nó đang bắt **ngữ điệu chưa hạ giọng**, thứ mà dấu phẩy và dấu hỏi bắt buộc phải có.

Trong 14 lần đó, 2 lần cả hai bộ giải mã đều đã qua. `"Rồi, rồi,"` của alpha.55 có hai bản thu
vòng 3 và 4 đạt similarity 1,0 / WER 0 trên cả beam lẫn greedy — **cả hai bị vứt**, segment giữ
bản 0,43, dán nhãn `ASR_MISMATCH_UNRESOLVED`, và chặn chương 016.

| script | file | đổi gì |
|---|---|---|
| `patch_endpoint.py` | `database.py` | `generation_endpoint_active` thôi chặn **khi và chỉ khi** cả hai lần giải mã đều qua. |
| `patch_endpoint_tests.py` | `tests/` | Bỏ nó khỏi danh sách parametrize "chặn dù ASR qua", thêm 2 test cho luật mới. |

Thu hẹp chứ không bỏ: giải mã trượt thì nó vẫn chặn, và `pace_outlier`,
`pitch_variant_skipped`, `pitch_variant_mixed` không đụng tới.
`_validated_dual_failed_candidate_conn` **cố ý giữ cách nhìn cũ** — nó kiểm tra lịch sử ghi
dưới luật cũ, thu hẹp cả chỗ đó thì mọi project cũ sẽ ném lỗi khi resume.
