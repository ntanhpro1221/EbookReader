"""Vá runtime_contract.py: đưa `vieneu` và `sea-g2p` vào bảng phiên bản bắt buộc.

Chạy: python patch_the_sdk_that_makes_the_voice_is_checked_too.py <root>

**XẾP Ở MỘT RANH GIỚI.** `runtime_contract.py` nằm trong `QUALITY_IMPLEMENTATION_FILES`, và hơn thế:
`build_quality_policy` ghi `runtime_dependencies` theo đúng bảng này, nên thêm một dòng là **đổi nội
dung chính sách chất lượng** của mọi lượt sau. Giữa lô thì resume bị từ chối.

## Cái lỗ

`CRITICAL_RUNTIME_DISTRIBUTIONS` kiểm torch, torchaudio, torchvision, huggingface-hub, librosa, timm,
transformers, utmosv2 — **không kiểm `vieneu`**, tức đúng cái gói quyết định giọng nói nghe ra sao.
Hợp đồng chỉ ghim *trọng số* (`VIENEU_CACHE_REVISION`), mà trọng số không phải thứ duy nhất đổi âm:

- 3.8.0 sửa bộ mã hoá **nối thêm một frame đệm nghe được vào clip tham chiếu** và đổi clip mẫu của
  Trúc Ly; 3.6.x đổi cách cắt/nối mảnh và độ dài ngừng. Trọng số y nguyên, giọng đổi.
- Đo 17-09/18-09: cùng preset, cùng seed, cùng câu, 3.3.0 và 3.8.1 cho cao độ Trúc Ly 220 Hz và
  257 Hz. Không một phép kiểm nào của dự án nhìn thấy điều đó.

Nghĩa là `pip install -U vieneu` vào `runtime/.venv` giữa một cuốn sẽ **im lặng đổi giọng của các
chương còn lại**. Hash chính sách chỉ bắt được khi ai đó cũng sửa `pyproject.toml`/`uv.lock` — mà đúng
cái ca nguy hiểm (cài đè, không sửa file ghim) thì không sửa gì cả.

`sea-g2p` vào cùng vì nó quyết **cách phát âm** các tên đã khoá (neo ASR), cùng một loại rủi ro im lặng.

## Sau bản vá

Phiên bản vieneu vào `runtime_dependencies` của chính sách, nên mỗi project mang theo bằng chứng nó
được đọc bằng SDK nào; `test_the_contract_table_agrees_with_the_pinned_versions` (đã có) giữ bảng này
khớp `pyproject.toml`; và nâng SDK sẽ đòi sửa cả hai chỗ — đúng ý muốn, vì nâng SDK là đổi giọng.
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "runtime_contract.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''    "transformers": ("transformers", "5.16.1"),
    "utmosv2": ("utmosv2", "1.3.1.dev0"),
}'''

NEW = '''    "transformers": ("transformers", "5.16.1"),
    "utmosv2": ("utmosv2", "1.3.1.dev0"),
    # The package that decides how the voice sounds, and the one this table never checked.
    # Pinning the weights (VIENEU_CACHE_REVISION) is not enough: 3.8.0 changed the reference
    # clip encoder and Trúc Ly's sample clip, and the same preset, seed and sentence measured
    # 220 Hz on 3.3.0 against 257 Hz on 3.8.1 with identical weights. So `pip install -U
    # vieneu` mid-book would silently re-cast the rest of the chapters.
    "vieneu": ("vieneu", "3.3.0"),
    # Same silent class: sea-g2p decides the pronunciation of locked names.
    "sea-g2p": ("sea_g2p", "0.9.1"),
}'''

assert OLD in s, "khong khop duoi bang CRITICAL_RUNTIME_DISTRIBUTIONS"
s = s.replace(OLD, NEW, 1)
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")

# ---------------------------------------------------------------------- test
p = root / "tests" / "test_runtime_contract.py"
s = io.open(p, encoding="utf-8").read()

ANCHOR = '''def test_the_contract_table_agrees_with_the_pinned_versions() -> None:'''

ADDED = '''def test_the_engine_that_makes_the_voice_is_version_checked() -> None:
    """Ghim trọng số không đủ: SDK cũng đổi âm.

    Bảng này từng kiểm mọi thứ quanh giọng (torch, transformers, utmosv2) mà không kiểm chính
    `vieneu`. 3.8.0 sửa bộ mã hoá clip tham chiếu và đổi clip mẫu của Trúc Ly: cùng preset, cùng
    seed, cùng câu, cao độ đo được 220 Hz ở 3.3.0 và 257 Hz ở 3.8.1 - trọng số y nguyên. Nên
    `pip install -U vieneu` giữa một cuốn là đổi giọng các chương còn lại mà không gì báo.
    """
    table = runtime_contract.CRITICAL_RUNTIME_DISTRIBUTIONS
    assert table.get("vieneu") == ("vieneu", "3.3.0")
    assert table.get("sea-g2p") == ("sea_g2p", "0.9.1")

    checks = runtime_contract.critical_dependency_checks()
    assert checks["vieneu"]["ok"] is True, checks["vieneu"]["detail"]


'''

assert ANCHOR in s, "khong thay test_the_contract_table_agrees_with_the_pinned_versions"
assert "test_the_engine_that_makes_the_voice_is_version_checked" not in s, "da va roi"
s = s.replace(ANCHOR, ADDED + ANCHOR, 1)
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")
