"""Test: ten khong doc duoc thi ghi lai va doc nguyen van, khong dung ca cuon."""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "tests" / "test_analysis_required.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''    # Names invented for the book, so CMUdict has nothing for them and no route is left.
    # A name the dictionary does know is resolved instead of blocking, which is what the
    # sibling test covers; what must still block is a name nothing at all can read.
    with pytest.raises(RuntimeError, match="High-quality pronunciation QA could not resolve"):
        analyzer.reconcile_name_pronunciations()

    assert any(
        event[1] == "NAME_PRONUNCIATION_UNCERTAIN_SKIPPED"
        for event in db.events
    )'''

NEW = '''    # Names invented for the book, so CMUdict has nothing for them and no route is left.
    #
    # This used to raise, and the raise was deliberate: high_quality refused to publish a
    # name it could not read. The owner overruled it on 2026-09-07, about this exact class of
    # failure - "if another book hits the same thing, the project has to handle it itself".
    #
    # alpha.57 is what prompted it. One word, `Cred` - the story's currency, in 24 of 478
    # chapters - stopped a run of 1,357 already-analysed segments at the step after analysis,
    # and only a person typing a reading in could restart it. Eleven other names in the same
    # batch were rescued by CMUdict or the local fallback; `Cred` has the onset cluster `cr`,
    # which is not in LATIN_NAME_ONSET_READINGS, so guessing was refused.
    #
    # Refusing to guess stays. _command_pronounce puts the reason well: a name mispronounced
    # through a whole book is worse than the reader saying the Latin letters. But the
    # conclusion of that argument is to say the letters, not to stop - stopping is only right
    # when somebody is standing there to be asked.
    analyzer.reconcile_name_pronunciations()

    assert any(
        event[1] == "NAME_PRONUNCIATION_UNCERTAIN_SKIPPED"
        for event in db.events
    ), "bỏ qua trong im lặng thì mới là hỏng; phải để lại dấu vết tra được"'''

assert OLD in s, "khong khop test chan"
s = s.replace(OLD, NEW, 1)
s = s.replace(
    "def test_high_quality_blocks_unresolved_short_name_pronunciation(monkeypatch) -> None:",
    "def test_high_quality_records_an_unresolved_short_name_and_carries_on(monkeypatch) -> None:",
    1,
)
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")
