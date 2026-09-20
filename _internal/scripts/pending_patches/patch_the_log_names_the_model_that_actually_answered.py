"""Vá analysis.py: hai dòng log về cách đọc tên phải gọi ĐÚNG tên model đã trả lời, không phải "Qwen" cứng.

Chạy: python patch_the_log_names_the_model_that_actually_answered.py <root>

## Vì sao (21-09 04:2x)

Đọc log lượt đo `gemma4:e2b-it-qat` chương 378 thì thấy:

    Qwen không tạo được cách đọc hợp lệ ở batch 1 cho ['Vlad']: invalid Vietnamese spoken form for 'Vlad': 'Vla-đ'
    Tên ngắn dùng cách đọc suy từ từ điển CMU vì Qwen thất bại: {'Vlad': 'Vờ-lát'}. Nên nghe lại.

Không có Qwen nào trong chương ấy. Bước cách-đọc-tên gọi `self.model` - cùng model với bước phân tích - nên
thứ thất bại là gemma4, còn chữ "Qwen" là nhãn cứng từ thời dự án chỉ chạy một model duy nhất.

Nhãn ấy vô hại khi chỉ có một model, và bắt đầu nói sai đúng lúc nó quan trọng nhất: khi ta so nhiều model
và phải đọc log để biết model nào hỏng ở đâu. Cùng họ với hai cái bẫy đọc đã ghi trong sổ - dòng
`Đã dừng Ollama ẩn...` mà tôi từng đọc thành nguyên nhân (`docs/WHAT_BLOCKS_A_CHAPTER.md`), và
`ollama show --template` in `{{ .Prompt }}` (`docs/LLM_EVAL.md`). Cả ba cùng một bài học: **chữ trong đầu ra
của công cụ không phải sự thật về hành vi.** Chỗ này thì sửa được, vì sự thật có ngay trong tay: `self.model`.

Chỉ đổi hai chuỗi log. Không đụng luồng, không đụng mã lỗi (`NAME_PRONUNCIATION_LOCAL_FALLBACK`,
`NAME_PRONUNCIATION_FROM_DICTIONARY` giữ nguyên để mọi bộ đếm cũ còn khớp).
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])


def patch(path: Path, old: str, new: str) -> None:
    source = io.open(path, encoding="utf-8").read()
    assert source.count(old) == 1, f"khong khop mot lan duy nhat trong {path.name}: {old.splitlines()[0]!r}"
    io.open(path, "w", encoding="utf-8").write(source.replace(old, new, 1))
    print(f"da va {path}")


patch(
    root / "ebook_reader" / "analysis.py",
    '''                        "Tên ngắn dùng cách đọc suy từ từ điển CMU vì Qwen thất bại: "''',
    '''                        # `self.model`, KHÔNG phải "Qwen" cứng: bước này dùng cùng model với bước phân
                        # tích, nên khi so nhiều model thì nhãn cứng nói sai đúng lúc log quan trọng nhất.
                        f"Tên ngắn dùng cách đọc suy từ từ điển CMU vì {self.model} thất bại: "''',
)

patch(
    root / "ebook_reader" / "analysis.py",
    '''                        f"Qwen không tạo được cách đọc hợp lệ ở batch {batch_index} cho {remaining}: "''',
    '''                        f"{self.model} không tạo được cách đọc hợp lệ ở batch {batch_index} cho {remaining}: "''',
)

test = root / "tests" / "test_the_log_names_the_model_that_actually_answered.py"
test.write_text('''"""Hai dòng log về cách đọc tên phải mang tên model thật, không phải nhãn "Qwen" cứng.

Ca thật: log lượt đo `gemma4:e2b-it-qat` chương 378 (21-09) nói "Qwen không tạo được cách đọc hợp lệ" trong
khi không có Qwen nào trong chương - bước cách-đọc-tên dùng `self.model`. Nhãn cứng vô hại khi chỉ có một
model, và nói sai đúng lúc ta so nhiều model.

Kiểm bằng soi mã nguồn vì hai dòng ấy nằm sau một lượt gọi LLM thất bại ba lần.
"""
from __future__ import annotations

import inspect

from ebook_reader.analysis import OllamaBookAnalyzer


def _source() -> str:
    return inspect.getsource(OllamaBookAnalyzer)


def test_no_hard_coded_model_name_in_the_pronunciation_warnings() -> None:
    source = _source()
    assert "vì Qwen thất bại" not in source
    assert "Qwen không tạo được cách đọc hợp lệ" not in source


def test_both_lines_name_the_model_in_hand() -> None:
    source = _source()
    assert "vì {self.model} thất bại" in source
    assert "{self.model} không tạo được cách đọc hợp lệ" in source


def test_the_event_codes_are_untouched() -> None:
    """Mã lỗi giữ nguyên để mọi bộ đếm và truy vấn cũ còn khớp."""
    source = _source()
    assert "NAME_PRONUNCIATION_LOCAL_FALLBACK" in source
    assert "NAME_PRONUNCIATION_FROM_DICTIONARY" in source
''', encoding="utf-8")
print(f"da viet {test}")
