"""Va test double: FakeDB co list_characters, va hai test cho viec mang nhan vat sang lo sau."""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "tests" / "test_analysis_required.py"
s = io.open(p, encoding="utf-8").read()

OLD_INIT = '''        self.chapters = [{"id": 1, "title": "Chương 1"}]

    def list_segments(self, statuses=None):
        if statuses is not None:
            return []
        return self.rows

    def list_chapters(self):
        return self.chapters
'''

NEW_INIT = '''        self.chapters = [{"id": 1, "title": "Chương 1"}]
        # What a previous batch established: rows already analysed in THIS project, and
        # characters port_casting.py carried in from the batch before. Both empty by
        # default, which is a book run in one pass, so every test written before this sees
        # exactly the prompt it saw before.
        self.analysed = []
        self.characters = []

    def list_segments(self, statuses=None):
        if statuses is not None:
            return self.analysed
        return self.rows

    def list_chapters(self):
        return self.chapters

    def list_characters(self):
        return self.characters
'''

assert OLD_INIT in s, "khong khop FakeDB"
s = s.replace(OLD_INIT, NEW_INIT, 1)

TEST = '''

def test_a_carried_character_appears_in_the_known_list_of_the_next_batch() -> None:
    """A batch boundary must not make the model re-guess a cast the last batch worked out.

    The prompt carries a section headed "Nhân vật đã biết từ các phần trước", built from what
    this project has already analysed. A fresh batch has analysed nothing, so without this the
    section is empty at every seam. Measured on this book's own text: from the second batch
    onward 80% of a batch's proper nouns have already appeared in an earlier one, and by the
    ninth batch 95%. An empty list at a seam is most of the cast.
    """
    db = FakeDB()
    db.characters = [
        {"canonical_name": "JULIANA", "gender": "female", "mention_count": 55},
        # Roles and casting buckets are not people, and a chapter-local NPC is scoped to a
        # chapter of the PREVIOUS batch - none of them may reach the prompt.
        {"canonical_name": "NARRATOR", "gender": "male", "mention_count": 941},
        {"canonical_name": "NPC_LOCAL::C00001::R2E34", "gender": "male", "mention_count": 2},
        {"canonical_name": "UNKNOWN", "gender": "male", "mention_count": 12},
        # Nothing was established about this one, so there is nothing to carry.
        {"canonical_name": "AI ĐÓ", "gender": "unknown", "mention_count": 3},
    ]

    analyzer = OllamaBookAnalyzer(build_settings(), db, lambda _message: None)
    summary = analyzer._known_summary()

    assert "JULIANA" in summary
    assert "gender đã biết=female" in summary
    assert "số lần đã gặp=55" in summary
    for excluded in ("NARRATOR", "NPC_LOCAL", "UNKNOWN", "AI ĐÓ"):
        assert excluded not in summary


def test_a_count_this_project_measured_outranks_a_carried_one() -> None:
    """The two never add up: a carried count is what we were told, not what we saw."""
    db = FakeDB()
    db.analysed = [
        {
            "speaker": "JULIANA",
            "gender": "female",
            "text": "Chào cậu.",
            "chapter_id": 1,
            "status": "analyzed",
        }
    ]
    db.characters = [
        {"canonical_name": "JULIANA", "gender": "female", "mention_count": 55}
    ]

    analyzer = OllamaBookAnalyzer(build_settings(), db, lambda _message: None)

    assert analyzer._speaker_counts["JULIANA"] == 1


def test_an_empty_carry_leaves_the_prompt_exactly_as_it_was() -> None:
    """The first batch of a book, and every single-pass run, must be untouched by all this."""
    analyzer = OllamaBookAnalyzer(build_settings(), FakeDB(), lambda _message: None)

    assert analyzer._known_summary() == "(Chưa có nhân vật đã biết)"
'''

s = s.rstrip() + "\n" + TEST
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")
