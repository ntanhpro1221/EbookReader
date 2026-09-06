
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
