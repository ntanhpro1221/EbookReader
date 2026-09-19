"""Luật "tên ngay trước 'nói:' là người nói" im khi tên là người NGHE hay mẩu tên bị cắt (cuốn 2: ~29 câu)."""
from __future__ import annotations

from ebook_reader.analysis import _trailing_speech_attribution


def test_the_listener_named_before_the_speech_verb_is_not_the_speaker() -> None:
    for text in (
        "Nhìn Neeshka, Salgueiro và các ủy viên khác rời đi, Levski quay sang Lucien nói:",
        "Ông đưa đôi mắt xám bạc nhìn Lucien nói:",
        "Công tước James nghiêm nghị nhìn Tử tước Harrison nói:",
        "Lucien khẽ gật đầu rồi dùng giọng Beaulac nói:",
        "Nghĩ vậy, ông liền phối hợp với Heidi nói:",
        "Xong xuôi tất cả, Benjamin nhìn đám người Lucien nói:",
        "Lucien cười cười quan sát Heidi, sau đó quay sang đám học trò Annick nói:",
        "Lucien không đáp ngay mà dùng phong thái nghiêm cẩn của một Arcanist nói:",
    ):
        assert _trailing_speech_attribution(text) is None, text


def test_a_name_cut_short_by_its_accents_is_not_a_name() -> None:
    assert _trailing_speech_attribution("Cảm thấy khó hiểu trước hành vi này của Giáo Sư, Triết Gia hỏi:") is None
    assert _trailing_speech_attribution("một phát túm lấy tai Trịnh Vĩnh Mong nói:") is None


def test_the_subject_still_takes_the_line() -> None:
    assert _trailing_speech_attribution("Lucien nói:") == "Lucien"
    assert _trailing_speech_attribution("Rồi Lucien nói:") == "Lucien"
    assert _trailing_speech_attribution("Sau đó, Lucien hỏi:") == "Lucien"
    assert _trailing_speech_attribution("Khi những người lùn bắt đầu cảnh giác, tổng giám mục Augustus nói:") == "Augustus"
    assert _trailing_speech_attribution("Đại hồng y mới tấn thăng Philip nói:") == "Philip"
    assert _trailing_speech_attribution("Nhìn Natasha một cách đầy thành khẩn, Bá tước Barady nói:") == "Barady"
    assert _trailing_speech_attribution("chưa kể nó cũng rất phù hợp, thế nên Raventi nói:") == "Raventi"
