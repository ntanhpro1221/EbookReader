# ĐÃ ÁP HẾT 2026-09-08 01:12 — thư mục này giờ là hồ sơ, không phải hàng chờ

Tám bản vá dưới đây **đã được ghi vào cây thật** sau khi alpha.56 chạy xong 9/9 và bộ canh xác
nhận không còn lượt nào đang bay. `quality_implementation_hash()` đổi thành `7deaf44c644f36ee`.

Kiểm ngay sau khi áp: `check_sources.py` báo **478/478 chương chia đoạn được, 58.258 segment** —
trước đó là 470/478. Không sửa một chữ nào trong nguồn.

Các script vẫn nằm đây làm hồ sơ. Chúng `assert` chuỗi gốc trước khi thay nên chạy lại sẽ dừng
chứ không làm hỏng gì. Đọc tiếp bên dưới để biết mỗi cái đổi gì và vì sao.

---

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

## RÚT LẠI 2026-09-08 — "bản thu tốt bị vứt" là chẩn đoán sai của tôi

Tôi đã cất ở đây hai bản vá nới lỏng `generation_endpoint_active`, kèm lập luận rằng nó bắt
nhầm ngữ điệu thay vì bắt bản thu bị cắt. **Sai, và sai theo hướng nguy hiểm** — vá vào là cho
audio bị cắt thật lọt qua. Đã xoá cả hai.

Xem [WHY_A_GOOD_TAKE_GETS_THROWN_AWAY.md](../../docs/WHY_A_GOOD_TAKE_GETS_THROWN_AWAY.md) cho
chẩn đoán đúng: trần khung sinh (`generation_frame_cap`) mới là chỗ hỏng, và nó cần GPU để
kiểm nên chưa vá.

---

## Sau khi áp: chạy alpha.57 trên chương 019–027

Không tuỳ tiện chọn dải này. Ba lý do:

1. **Nó buộc phải chạy được sau bản vá, và không chạy được trước.** Chương `019` là một trong
   tám chương ngoặc kép treo — `segment_chapter_text` ném lỗi ngay ở chương đầu tiên của dải.
   Nên lượt này kiểm bản vá phục hồi trên dữ liệu thật, không phải trên ca dựng sẵn.
2. **Cùng cỡ với alpha.55 nên so được.** 9 chương, 1.357 segment (alpha.55: 9 chương, 1.083
   segment), ~2,9 giờ máy so với 2,34.
3. **Chương mới, chưa ai nghe.** Đây là điều kiện bắt buộc để kiểm chẩn đoán neo tên và tiếng
   cười: ba chương từng chặn của alpha.55 (013/014/016) **không kiểm được gì**, vì năm trong sáu
   đoạn chặn của chúng đã có phán quyết mang sang và đi qua nhờ phán quyết chứ không nhờ máy.

### Con số để so, ghi trước khi chạy

| | alpha.55 (010–018) | alpha.57 (019–027) dự đoán |
|---|---|---|
| chương chặn | **4/9** | **1–2/9** |
| đoạn chặn | 6 | 2–3 |
| chương phải phục hồi ngoặc | 0 | **1** (`019`) |

Dự đoán ấy dựa trên: ba trong sáu đoạn chặn của alpha.55 thuộc đúng hai lớp mà bản vá nhắm vào
(đoạn chỉ gồm một tên ngắn; tiếng cười viết `Ahaha`). Nếu tỉ lệ chặn **không** giảm, chẩn đoán
sai và phải đo lại chứ đừng vá thêm.

**Điều sẽ khiến tôi nghi ngờ dù kết quả đẹp:** nếu chương `019` xuất bản mà `warnings` của bộ
chia đoạn **rỗng**, nghĩa là nó không hề phải phục hồi — tức nguồn đã bị ai sửa, hoặc bản vá
không chạy, và con số 9/9 chẳng nói lên điều gì.
