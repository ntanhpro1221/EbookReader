"""Va runtime_contract.py: ghim revision model GIONG, khong chi model cham diem.

CHUA AP. Xem docs/THE_VOICE_MODEL_IS_NOT_PINNED.md. Ban va nay khong doi audio - no chi lam
mot lan doi model IM LANG tro thanh mot loi noi thanh tieng. Ap duoc bat cu luc nao may ranh.
"""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "runtime_contract.py"
s = io.open(p, encoding="utf-8").read()

# ------------------------------------------------------------------ hằng số
OLD = '''TIMM_CACHE_REPOSITORY = "models--timm--tf_efficientnetv2_s.in21k_ft_in1k"
TIMM_CACHE_REVISION = "ea9abc143ea2b9d8e1ec1de277bce02149b9cf0e"'''
NEW = '''TIMM_CACHE_REPOSITORY = "models--timm--tf_efficientnetv2_s.in21k_ft_in1k"
TIMM_CACHE_REVISION = "ea9abc143ea2b9d8e1ec1de277bce02149b9cf0e"

# Model **giọng**, tức thứ thật sự làm ra cuốn sách. Trước 2026-09-08 nó là model duy nhất
# không được ghim, trong khi wav2vec2 và timm - hai model chỉ *chấm điểm* - thì có.
#
# Nó đã tự đổi: cache giữ ba revision, và `refs/main` chuyển sang bản mới lúc 10:45 ngày
# 2026-09-08, giữa alpha.60 (07:06) và alpha.62 (13:46). Trọng số khác thật, cùng kích thước
# 247.974.928 byte nhưng sha256 `82b24b3f…` so với `119003a9…`. Hậu quả đo được: 189 đoạn có
# hạt giống và mọi đầu vào ghi lại giống hệt nhau, và **không đoạn nào** cho cùng bản thu.
#
# Vì sao đây là lỗi sản phẩm chứ không chỉ lỗi phương pháp: kế hoạch sản xuất là 16 lô trải
# nhiều ngày (docs/PRODUCTION_PLAN.md). Upstream đẩy một revision ở giữa thì giọng người dẫn
# chuyện **đổi giữa cuốn sách**, và mọi phép kiểm trong dự án đều mù với nó - mỗi chương được
# chấm theo chính nó, không ai so chương 1 với chương 200.
#
# Ghim bản MỚI, không quay về bản cũ: kế hoạch chạy lại từ chương 000 nên không có audio nào
# cần giữ liên tục, và chịu một lần đứt rồi ổn định thì rẻ hơn.
#
# **Đừng dọn cache.** `2da0efab622a1722125991736524f080b751ef5b` là bản đã sinh ra mọi audio
# từ alpha.10 tới alpha.60, và là thứ duy nhất tái tạo lại được chúng.
VIENEU_CACHE_REPOSITORY = "models--pnnbao-ump--VieNeu-TTS-v3-Turbo"
VIENEU_CACHE_REVISION = "8b7e9cffb4b41918cb638b9f62f0a751184d14a6"
VIENEU_PREVIOUS_REVISION = "2da0efab622a1722125991736524f080b751ef5b"

VOICE_MODEL_FILES: tuple[tuple[str, str, str, int, str], ...] = (
    (
        VIENEU_CACHE_REPOSITORY,
        VIENEU_CACHE_REVISION,
        "config.json",
        1_553,
        "eee8e032cb936a60312f594a8156c086173a9c0255a545bd11a448f22a7c77ae",
    ),
    (
        VIENEU_CACHE_REPOSITORY,
        VIENEU_CACHE_REVISION,
        "denoiser.onnx",
        42_661_414,
        "b7621953291cfe05e695a9c0ff4255aa2f93239fc17c26627e18b7b6b8f72f0b",
    ),
    (
        VIENEU_CACHE_REPOSITORY,
        VIENEU_CACHE_REVISION,
        "speaker_encoder.onnx",
        28_303_423,
        "a6ac6a63997761ae2997373e2ee1c47040854b4b759ea41ec48e4e42df0f4d73",
    ),
    (
        VIENEU_CACHE_REPOSITORY,
        VIENEU_CACHE_REVISION,
        "update/model.safetensors",
        247_974_928,
        "119003a9e121760d1c3b9b50bd675bfde8d5f3de2b12641cf97a17d3883a5da7",
    ),
    (
        VIENEU_CACHE_REPOSITORY,
        VIENEU_CACHE_REVISION,
        "update/config.json",
        2_152,
        "a9f8d9c4b4736448ab355d1a98cfe48f5e39aecf2916c37b0806c228612e9a2d",
    ),
)'''
assert OLD in s, "khong khop hang so timm"
s = s.replace(OLD, NEW, 1)

# ------------------------------------------------------------------ cổng refs/main
OLD = '''        "timm_backbone": (
            hub_root / TIMM_CACHE_REPOSITORY / "refs" / "main",
            TIMM_CACHE_REVISION,
        ),
    }'''
NEW = '''        "timm_backbone": (
            hub_root / TIMM_CACHE_REPOSITORY / "refs" / "main",
            TIMM_CACHE_REVISION,
        ),
        "vieneu_voice": (
            hub_root / VIENEU_CACHE_REPOSITORY / "refs" / "main",
            VIENEU_CACHE_REVISION,
        ),
    }'''
assert OLD in s, "khong khop cache_refs"
s = s.replace(OLD, NEW, 1)

# ------------------------------------------------------------------ cổng kích thước + hash
OLD = '''    for repository, revision, filename, expected_size, expected_sha256 in (
        PERCEPTUAL_BASE_MODEL_FILES
    ):'''
NEW = '''    for repository, revision, filename, expected_size, expected_sha256 in (
        PERCEPTUAL_BASE_MODEL_FILES + VOICE_MODEL_FILES
    ):'''
assert OLD in s, "khong khop vong kiem file"
s = s.replace(OLD, NEW, 1)

io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")

# ------------------------------------------------------------------ test
q = root / "tests" / "test_voice_model_is_pinned.py"
q.write_text(
    '''"""Model làm ra giọng phải bị ghim chặt như model chấm điểm giọng.

2026-09-08: cache giữ ba revision của VieNeu-TTS và `refs/main` tự chuyển sang bản mới lúc
10:45, giữa hai lượt chạy. Trọng số khác thật - cùng 247.974.928 byte, sha256 `82b24b3f…` so
với `119003a9…` - và hậu quả đo được là 189 đoạn cùng hạt giống, không đoạn nào cùng bản thu.

Trước hôm ấy `runtime_contract` ghim wav2vec2, timm và các file model nền của perceptual QA,
kèm cả kích thước lẫn hash. Nó không ghim thứ đọc cuốn sách.
"""
from __future__ import annotations

from ebook_reader import runtime_contract as contract


def test_the_voice_model_revision_is_pinned() -> None:
    assert contract.VIENEU_CACHE_REVISION
    assert len(contract.VIENEU_CACHE_REVISION) == 40, "phải là một commit hash đầy đủ"


def test_the_weights_are_pinned_by_hash_not_just_by_revision() -> None:
    """Revision là một cái nhãn; hash là thứ không ai đổi được mà mình không biết."""
    weights = [
        entry for entry in contract.VOICE_MODEL_FILES if entry[2].endswith("model.safetensors")
    ]
    assert weights, "trọng số phải nằm trong danh sách ghim"
    (_repo, _rev, _name, size, digest) = weights[0]
    assert size == 247_974_928
    assert digest == "119003a9e121760d1c3b9b50bd675bfde8d5f3de2b12641cf97a17d3883a5da7"


def test_every_pinned_voice_file_names_the_pinned_revision() -> None:
    for entry in contract.VOICE_MODEL_FILES:
        assert entry[0] == contract.VIENEU_CACHE_REPOSITORY
        assert entry[1] == contract.VIENEU_CACHE_REVISION


def test_the_previous_revision_is_recorded_so_old_audio_stays_reproducible() -> None:
    """`2da0efab…` sinh ra mọi audio từ alpha.10 tới alpha.60. Mất nó là mất cách tái tạo."""
    assert contract.VIENEU_PREVIOUS_REVISION != contract.VIENEU_CACHE_REVISION
    assert len(contract.VIENEU_PREVIOUS_REVISION) == 40


def test_the_check_actually_walks_the_voice_files() -> None:
    """Ghim mà không ai đọc thì chỉ là chú thích. Vòng kiểm phải đi qua cả hai danh sách."""
    import inspect

    source = inspect.getsource(contract)
    assert "PERCEPTUAL_BASE_MODEL_FILES + VOICE_MODEL_FILES" in source
    assert "vieneu_voice" in source, "refs/main của model giọng phải nằm trong cache_refs"
''',
    encoding="utf-8",
)
print(f"da tao {q}")
