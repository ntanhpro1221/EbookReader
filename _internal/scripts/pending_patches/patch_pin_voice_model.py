"""Va runtime_contract.py: ghim revision model GIONG, bang mot phep kiem RIENG.

Ban dau toi nhet model giong vao `perceptual_cache_check` va bo test bat ngay:
`test_perceptual_cache_marker_requires_locked_revision_and_checkpoint_hash` do. No dung -
ham ay dang ky la `checks["model:utmosv2_cache"]`, tuc phep kiem cua UTMOSv2, va mot lan
thieu ghim TTS bao thanh loi perceptual la bao sai cho.

Xem docs/THE_VOICE_MODEL_IS_NOT_PINNED.md.
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
# 247.974.928 byte nhưng sha256 `82b24b3f…` so với `119003a9…`. Hậu quả đo được: 1.213 đoạn
# có hạt giống và mọi đầu vào ghi lại giống hệt nhau, và **không đoạn nào** cho cùng bản thu.
#
# Vì sao đây là lỗi sản phẩm chứ không chỉ lỗi phương pháp: kế hoạch sản xuất là 16 lô trải
# nhiều ngày (docs/PRODUCTION_PLAN.md). Upstream đẩy một revision ở giữa thì giọng người dẫn
# chuyện **đổi giữa cuốn sách**, và mọi phép kiểm trong dự án đều mù với nó - mỗi chương được
# chấm theo chính nó, không ai so chương 1 với chương 200.
#
# Ghim bản MỚI, không quay về bản cũ: kế hoạch chạy lại từ chương 000 nên không có audio nào
# cần giữ liên tục, và chịu một lần đứt rồi ổn định thì rẻ hơn.
#
# **Đừng dọn cache.** `2da0efab…` là bản đã sinh ra mọi audio từ alpha.10 tới alpha.60, và là
# thứ duy nhất tái tạo lại được chúng.
VIENEU_CACHE_REPOSITORY = "models--pnnbao-ump--VieNeu-TTS-v3-Turbo"
VIENEU_CACHE_REVISION = "8b7e9cffb4b41918cb638b9f62f0a751184d14a6"
VIENEU_PREVIOUS_REVISION = "2da0efab622a1722125991736524f080b751ef5b"

VOICE_MODEL_FILES: tuple[tuple[str, int, str], ...] = (
    (
        "config.json",
        1_553,
        "eee8e032cb936a60312f594a8156c086173a9c0255a545bd11a448f22a7c77ae",
    ),
    (
        "denoiser.onnx",
        42_661_414,
        "b7621953291cfe05e695a9c0ff4255aa2f93239fc17c26627e18b7b6b8f72f0b",
    ),
    (
        "speaker_encoder.onnx",
        28_303_423,
        "a6ac6a63997761ae2997373e2ee1c47040854b4b759ea41ec48e4e42df0f4d73",
    ),
    (
        "update/model.safetensors",
        247_974_928,
        "119003a9e121760d1c3b9b50bd675bfde8d5f3de2b12641cf97a17d3883a5da7",
    ),
    (
        "update/config.json",
        2_152,
        "a9f8d9c4b4736448ab355d1a98cfe48f5e39aecf2916c37b0806c228612e9a2d",
    ),
)'''
assert OLD in s, "khong khop hang so timm"
s = s.replace(OLD, NEW, 1)

# ------------------------------------------------------------------ phép kiểm riêng
ANCHOR = "def runtime_contract_errors("
assert ANCHOR in s, "khong khop cho chen ham"
FUNC = '''def voice_model_check(runtime_root: Path) -> dict[str, Any]:
    """Model giọng có đúng revision đã ghim không, và có đúng bytes không.

    Phép kiểm **riêng**, không gộp vào `perceptual_cache_check`. Bản đầu tiên của bản vá này
    gộp vào đấy và bộ test bắt ngay: hàm ấy đăng ký là `checks["model:utmosv2_cache"]`, nên
    một lần thiếu ghim TTS sẽ báo thành lỗi perceptual - đúng lỗi, sai chỗ, và sai chỗ thì
    người đọc đi tìm nhầm hướng.

    Kiểm hai tầng như các model kia: `refs/main` cho danh tính, rồi kích thước + sha256 cho
    nội dung. Revision là cái nhãn; hash là thứ không ai đổi được mà mình không biết - và
    2026-09-08 cho thấy nhãn đổi được một cách hoàn toàn im lặng.
    """
    hub_root = runtime_root / "models" / "huggingface" / "hub"
    repository_root = hub_root / VIENEU_CACHE_REPOSITORY
    errors: list[str] = []

    ref_path = repository_root / "refs" / "main"
    actual_revision = ""
    try:
        actual_revision = ref_path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        errors.append(f"voice cache ref unavailable ({ref_path}): {exc}")
    else:
        if actual_revision != VIENEU_CACHE_REVISION:
            errors.append(
                f"voice model revision={actual_revision!r}, "
                f"expected {VIENEU_CACHE_REVISION!r}"
            )

    snapshot_root = repository_root / "snapshots" / VIENEU_CACHE_REVISION
    for filename, expected_size, expected_sha256 in VOICE_MODEL_FILES:
        snapshot_file = snapshot_root / filename
        if not snapshot_file.is_file():
            errors.append(f"missing pinned voice-model file: {snapshot_file}")
            continue
        try:
            actual_size = snapshot_file.stat().st_size
        except OSError as exc:
            errors.append(f"voice-model file unavailable ({snapshot_file}): {exc}")
            continue
        if actual_size != expected_size:
            errors.append(
                f"voice-model size={actual_size} for {snapshot_file}, "
                f"expected {expected_size}"
            )
            continue
        try:
            actual_sha256 = sha256_file(snapshot_file)
        except OSError as exc:
            errors.append(f"cannot hash voice-model file ({snapshot_file}): {exc}")
            continue
        if actual_sha256 != expected_sha256:
            errors.append(
                f"voice-model sha256={actual_sha256} for {snapshot_file}, "
                f"expected {expected_sha256}"
            )

    return {
        "ok": not errors,
        "detail": (
            f"VieNeu-TTS {VIENEU_CACHE_REVISION[:12]}"
            if not errors
            else "; ".join(errors)
        ),
        "revision": actual_revision,
        "errors": errors,
    }


def runtime_contract_errors('''
s = s.replace(ANCHOR, FUNC, 1)

# ------------------------------------------------------------------ vào bộ kiểm tổng
OLD = '''    checks = {
        "setup_marker": setup_marker_check(runtime_root),
        "perceptual_cache": perceptual_cache,'''
NEW = '''    checks = {
        "setup_marker": setup_marker_check(runtime_root),
        "perceptual_cache": perceptual_cache,
        "voice_model": voice_model_check(runtime_root),'''
assert OLD in s, "khong khop bo kiem tong"
s = s.replace(OLD, NEW, 1)

io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")

# ------------------------------------------------------------------ cli
p = root / "ebook_reader" / "cli.py"
s = io.open(p, encoding="utf-8").read()
OLD = '''    checks["model:utmosv2_cache"] = perceptual_cache_check(runtime_root)'''
NEW = '''    checks["model:utmosv2_cache"] = perceptual_cache_check(runtime_root)
    checks["model:vieneu_voice"] = voice_model_check(runtime_root)'''
assert OLD in s, "khong khop cli check"
s = s.replace(OLD, NEW, 1)
OLD = '''    perceptual_cache_check,'''
NEW = '''    perceptual_cache_check,
    voice_model_check,'''
assert OLD in s, "khong khop cli import"
s = s.replace(OLD, NEW, 1)
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")

# ------------------------------------------------------------------ test
q = root / "tests" / "test_voice_model_is_pinned.py"
q.write_text(
    '''"""Model làm ra giọng phải bị ghim chặt như model chấm điểm giọng.

2026-09-08: cache giữ ba revision của VieNeu-TTS và `refs/main` tự chuyển sang bản mới lúc
10:45, giữa hai lượt chạy. Trọng số khác thật - cùng 247.974.928 byte, sha256 `82b24b3f…` so
với `119003a9…` - và hậu quả đo được là 1.213 đoạn cùng hạt giống, không đoạn nào cùng bản thu.

Trước hôm ấy `runtime_contract` ghim wav2vec2, timm và các file model nền của perceptual QA,
kèm cả kích thước lẫn hash. Nó không ghim thứ đọc cuốn sách.
"""
from __future__ import annotations

import json
from pathlib import Path

from ebook_reader import runtime_contract as contract


def test_the_voice_model_revision_is_pinned() -> None:
    assert len(contract.VIENEU_CACHE_REVISION) == 40, "phải là một commit hash đầy đủ"


def test_the_weights_are_pinned_by_hash_not_just_by_revision() -> None:
    """Revision là một cái nhãn; hash là thứ không ai đổi được mà mình không biết."""
    weights = [
        entry for entry in contract.VOICE_MODEL_FILES if entry[0].endswith("model.safetensors")
    ]
    assert weights, "trọng số phải nằm trong danh sách ghim"
    (_name, size, digest) = weights[0]
    assert size == 247_974_928
    assert digest == "119003a9e121760d1c3b9b50bd675bfde8d5f3de2b12641cf97a17d3883a5da7"


def test_the_previous_revision_is_recorded_so_old_audio_stays_reproducible() -> None:
    """`2da0efab…` sinh ra mọi audio từ alpha.10 tới alpha.60. Mất nó là mất cách tái tạo."""
    assert contract.VIENEU_PREVIOUS_REVISION != contract.VIENEU_CACHE_REVISION
    assert len(contract.VIENEU_PREVIOUS_REVISION) == 40


def test_a_wrong_revision_is_caught(tmp_path: Path) -> None:
    ref = (
        tmp_path
        / "models" / "huggingface" / "hub" / contract.VIENEU_CACHE_REPOSITORY / "refs" / "main"
    )
    ref.parent.mkdir(parents=True)
    ref.write_text(contract.VIENEU_PREVIOUS_REVISION, encoding="utf-8")

    result = contract.voice_model_check(tmp_path)

    assert result["ok"] is False
    assert "revision" in result["detail"]


def test_it_is_its_own_check_not_folded_into_the_perceptual_one(tmp_path: Path) -> None:
    """Bản vá đầu tiên gộp vào `perceptual_cache_check` và bộ test bắt được.

    Hàm ấy đăng ký là `checks["model:utmosv2_cache"]`, nên một lần thiếu ghim TTS sẽ báo thành
    lỗi perceptual - đúng lỗi, sai chỗ, và sai chỗ thì người đọc đi tìm nhầm hướng.
    """
    import inspect

    source = inspect.getsource(contract.perceptual_cache_check)
    assert "VIENEU" not in source, "model giọng không được nằm trong phép kiểm perceptual"
    assert callable(contract.voice_model_check)


def test_the_aggregate_contract_asks_about_the_voice(tmp_path: Path) -> None:
    """Một phép kiểm không ai gọi thì chỉ là chú thích."""
    import inspect

    assert "voice_model_check(runtime_root)" in inspect.getsource(
        contract.runtime_contract_errors
    )
''',
    encoding="utf-8",
)
print(f"da tao {q}")
