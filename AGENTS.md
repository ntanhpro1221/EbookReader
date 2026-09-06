
## Đọc `QUALITY_IMPLEMENTATION_FILES` từ code, đừng tin bản chép tay

Danh sách file bị khoá **không** phải 14 file như các bản tóm tắt vẫn chép. Đọc thẳng:

```bash
_internal/runtime/.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'_internal'); from ebook_reader.quality_policy import QUALITY_IMPLEMENTATION_FILES; print(*QUALITY_IMPLEMENTATION_FILES, sep='\n')"
```

Ngày 2026-09-06 nó trả về **22** mục. Những cái hay bị bỏ sót khỏi bản chép tay:
`recovery.py`, `expression.py`, `quality_policy.py`, và cả bốn file `*_contract.py`
(`asr_contract.py`, `tts_contract.py`, `perceptual_contract.py`, `audio_transform_contract.py`,
`runtime_contract.py`).

Tôi đã sửa `recovery.py` ngay trong production vì bản chép tay không có nó, tưởng là an toàn.
Nó **không** an toàn: hash đổi từ `b63e95be` sang `365ad7ee`, và nếu để nguyên thì lần
`resume` sau của alpha.48 bị từ chối — tức mất sạch bằng chứng QA audio của cả quyển.

**Cách kiểm chắc chắn, trước mọi commit đụng vào `_internal/ebook_reader/`:**

```bash
_internal/runtime/.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'_internal'); from ebook_reader.quality_policy import quality_implementation_hash; print(quality_implementation_hash())"
```

Chạy trước và sau khi sửa. Hash đổi thì bản sửa ấy **phải** nằm ở nhánh dev và chờ hết run,
bất kể file đó có trong danh sách bạn nhớ hay không. Hàm đọc file từ đĩa mỗi lần gọi, nên
phép thử này luôn nói sự thật còn trí nhớ thì không.

## Đừng `stop` giữa pha phân tích — đó là đổi quyển sách, không phải tạm nghỉ

Đã chứng minh bằng thí nghiệm có đối chứng (2026-09-07, xem `VERSIONS.md`). Cùng code, cùng
nguồn, cùng cách đọc gieo sẵn; biến duy nhất là một lần `stop`/`resume` ở 620/948:

| | nhân vật | đoạn khác người nói |
|---|---|---|
| chạy liền mạch | **23** | — |
| dừng rồi resume | **19** | 18, toàn bộ **sau** mốc bị ngắt |

Chuỗi hệ quả: người nói khác → sổ nhân vật khác → casting khác → **seed khác → audio khác** →
mọi phán quyết của chủ sách trên những đoạn ấy **hết hiệu lực**.

**Quy tắc:**

- **Trong pha phân tích:** đừng dừng. Nếu buộc phải dừng (máy cần tắt, sửa lỗi chặn đường),
  hãy coi như **mất toàn bộ pha phân tích** và tạo project mới, đừng resume rồi tin rằng nó
  là cùng một quyển sách.
- **Sau pha phân tích:** dừng thoải mái. Tổng hợp resume trung thành — chương 1–4 của
  alpha.51 trùng khít alpha.48 từng byte.
- **Muốn biết đang ở pha nào:** `SELECT COUNT(*) FROM segments WHERE status='pending'`. Khác 0
  nghĩa là phân tích chưa xong.

Điều này áp cả cho crash: alpha.50 chết vì `PermissionError` giữa pha phân tích, resume, và
ra một quyển sách khác — 6/10 chương thay vì 8/10 như alpha.51.
