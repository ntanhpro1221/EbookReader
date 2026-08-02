from __future__ import annotations

import os
from pathlib import Path

_INTERNAL_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_ROOT = Path(
    os.environ.get("EBOOK_READER_RUNTIME", str(_INTERNAL_ROOT / "runtime"))
).resolve()

os.environ.setdefault("EBOOK_READER_RUNTIME", str(RUNTIME_ROOT))
os.environ.setdefault("HF_HOME", str(RUNTIME_ROOT / "models" / "huggingface"))
os.environ.setdefault("HF_HUB_CACHE", str(RUNTIME_ROOT / "models" / "huggingface" / "hub"))
os.environ.setdefault("TORCH_HOME", str(RUNTIME_ROOT / "models" / "torch"))
