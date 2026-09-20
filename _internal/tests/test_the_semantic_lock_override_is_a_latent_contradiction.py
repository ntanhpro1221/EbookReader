"""Ghim một mâu thuẫn CHƯA vá, cố ý: ghi-đè khoá nghĩa khai `raw_accept: False` trong khi host ĐỒNG Ý.

Đây là test *tài liệu*, không phải test đòi sửa. Nó tồn tại vì hai lý do, cả hai đều đã tốn thời gian thật:

1. Cùng hình dạng ấy ở nhánh TIÊU ĐỀ đã giết lô 11 lúc 17:02 ngày 20-09, và mất một buổi để đọc ra (xem
   `tests/test_an_inaudible_delta_on_a_heading_needs_no_override.py` và `docs/WHAT_BLOCKS_A_CHAPTER.md`).
   Nếu ca này nổ, test này cho người đọc biết ngay nó là ca nào, thay vì lần lại từ đầu.
2. Cách sửa ở đây **khác** chỗ tiêu đề, nên đừng dán bản vá kia sang. Chỗ tiêu đề gác bằng `blocking_deltas`
   là đúng, vì khoá tiêu đề nói về ĐỘ NGHE ĐƯỢC. Khoá nghĩa tồn tại để giữ Ý NGHĨA - gác nó bằng
   `blocking_deltas` là xoá luôn khoá trong mọi ca nó cần. Đường đúng là sửa phía sổ: mong đợi ghi-đè theo
   `raw_accept` THẬT thay vì đòi nó bằng `False`.

## Vì sao vẫn để nguyên: một phép đo, không phải một linh cảm (21-09 04:4x)

Đếm trên toàn bộ 11 lô đã bay của cuốn 2 (`analysis_candidates.candidate_json`, 53.899 dòng phản biện đã ghi):

    dòng có khoá `emotion`           586
      trong đó tiêu đề chương        579   <- khoá tiêu đề, KHÔNG phải khoá nghĩa; đã vá ở ranh giới 11
      khoá nghĩa thật                  7   <- tất cả ở lô 1, cùng một cảnh bóng đè chương 1-2

Và cả 7 lần ấy model đã trả đúng cảm xúc bị khoá, nên điều kiện thứ hai (`corrected["emotion"]` nằm ngoài
`allowed_emotions`) chưa từng xảy ra. Phơi nhiễm 7/53.899 = 0,013%, dồn vào một cảnh, và cần thêm một sự
trùng hợp nữa mới nổ. Sửa `ebook_reader/database.py` - một trong ba cổng của file bị khoá chặt nhất dự án -
cho con số ấy là đổi sai chiều. Ghim bằng test, để lại cho ca tái hiện thật.

Kiểm bằng cách soi mã nguồn, cùng lối với `tests/test_critic_accept_coherence.py`, vì cả hai nhánh nằm sâu
trong một lượt gọi LLM.
"""
from __future__ import annotations

import inspect

from ebook_reader.analysis import _adjudicate_director_critic
from ebook_reader.database import host_derived_accept


def _critic_source() -> str:
    source = inspect.getsource(_adjudicate_director_critic)
    assert "semantic_override = {" in source, "nhánh khoá nghĩa đã chuyển chỗ - đọc lại trước khi sửa test"
    return source


def test_the_semantic_override_still_hard_codes_a_refusal() -> None:
    """Nếu dòng này biến mất thì mâu thuẫn đã được sửa - xoá test và ghi vào WHAT_BLOCKS_A_CHAPTER.md."""
    source = _critic_source()
    semantic = source[source.index("semantic_override = {"):]
    assert '"raw_accept": False,' in semantic[:600]


def test_the_semantic_override_is_not_gated_on_blocking_deltas() -> None:
    """Chỗ tiêu đề gác bằng `blocking_deltas`; chỗ này KHÔNG, và cố ý không - xem docstring đầu file."""
    source = _critic_source()
    semantic_head = source[source.index("semantic_lock is not None"):]
    assert "blocking_deltas" not in semantic_head[:400]


def test_an_emotion_only_delta_is_an_agreement_so_the_two_halves_disagree() -> None:
    """Đúng một dòng số học làm nên mâu thuẫn: host đồng ý, mà bản ghi khai từ chối."""
    assert host_derived_accept(["emotion:neutral->afraid"]) is True
    # Điều kiện sinh ghi-đè khoá nghĩa gồm `delta_fields == ("emotion",)`, tức đúng ca trên. Phía sổ chỉ
    # coi ghi-đè ấy hợp lệ khi `raw_accept_value is False`, mà cờ accept lưu lại là `host_derived_agreement`.
    assert host_derived_accept(["emotion:neutral->afraid", "kind:narration->dialogue"]) is False
