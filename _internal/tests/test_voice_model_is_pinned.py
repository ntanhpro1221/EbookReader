"""Model làm ra giọng phải bị ghim chặt như model chấm điểm giọng.

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
