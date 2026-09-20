"""Trạng ngữ giữa tên và động từ nói không xoá người nói; ba chốt chống gán sai."""
from __future__ import annotations

from ebook_reader.analysis import _trailing_speech_attribution


def test_a_modifier_between_a_name_and_said() -> None:
    assert _trailing_speech_attribution("Arthen nghiêm nghị hỏi:") == "Arthen"
    assert _trailing_speech_attribution("James mỉm cười nói:") == "James"
    assert _trailing_speech_attribution("Sau khi tán gẫu một hồi, Lazar đột nhiên hỏi:") == "Lazar"
    assert _trailing_speech_attribution("Rút tay về, Sophia thở hổn hển nói:") == "Sophia"


def test_the_plain_form_still_works() -> None:
    assert _trailing_speech_attribution("Lucien nói:") == "Lucien"
    assert _trailing_speech_attribution("Không có tên nào ở đây cả.") is None


def test_an_object_is_not_the_speaker() -> None:
    # Giới từ liền trước tên -> tên là đối tượng.
    assert _trailing_speech_attribution("James chỉ vào Lucien rồi nói:") is None
    # Nhưng giới từ ở xa thì không cản.
    assert _trailing_speech_attribution("Bước vào phòng, Sophia lạnh lùng nói:") == "Sophia"


def test_a_listener_directed_word_in_the_middle_is_not_an_attribution() -> None:
    assert _trailing_speech_attribution("Lucien nhìn sang nói:") is None


def test_a_truncated_vietnamese_name_is_refused() -> None:
    # LATIN_PROPER_NAME chỉ bắt âm cuối; gán "Mong" hay "Ca" là sinh ra nhân vật mới.
    assert _trailing_speech_attribution("Trịnh Vĩnh Mong nhíu mày nói:") is None
    assert _trailing_speech_attribution("Sơn Ca cười khúc khích nói:") is None
