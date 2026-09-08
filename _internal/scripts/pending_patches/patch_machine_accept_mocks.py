"""Va test cu: cong doc `ruled_` chu khong con `accepted_`, nen ba mock phai theo."""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])

# ---------------------------------------------------------- test_pipeline_mock.py
p = root / "tests" / "test_pipeline_mock.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''    class _NothingAccepted:
        """The check now asks what a listener has accepted; nobody has accepted anything
        here, which is the case this test has always been about."""

        @staticmethod
        def accepted_segment_warnings() -> dict:
            return {}'''
NEW = '''    class _NothingRuledOn:
        """Nobody - and nothing - has ruled on these takes, which is the case this test has
        always been about.

        The gate reads `ruled_segment_warnings` rather than `accepted_segment_warnings` since
        2026-09-08: a take can now be let through by a listener who heard it *or* by the
        machine when ASR is the only witness against it. The gate asks whether anything is
        still to be decided; only the reports ask who decided."""

        @staticmethod
        def ruled_segment_warnings() -> dict:
            return {}'''
assert OLD in s, "khong khop _NothingAccepted"
s = s.replace(OLD, NEW, 1)
s = s.replace("    pipeline.db = _NothingAccepted()", "    pipeline.db = _NothingRuledOn()", 1)
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")

# --------------------------------------------------- test_listener_accepts_a_take.py
p = root / "tests" / "test_listener_accepts_a_take.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''    class _DB:
        def __init__(self, accepted):
            self._accepted = accepted

        def accepted_segment_warnings(self):
            return self._accepted'''
NEW = '''    class _DB:
        # `ruled_`, không phải `accepted_`: cổng hỏi "còn phải quyết lại gì không", và câu
        # trả lời gồm cả phán quyết của người nghe lẫn của máy. Test này vẫn nói về người
        # nghe - `ProjectDB.ruled_segment_warnings` hợp hai bảng, và phán quyết của người
        # đi vào đúng bằng đường cũ.
        def __init__(self, accepted):
            self._accepted = accepted

        def ruled_segment_warnings(self):
            return self._accepted'''
assert OLD in s, "khong khop _DB co __init__"
s = s.replace(OLD, NEW, 1)

OLD = '''    class _DB:
        def accepted_segment_warnings(self):
            return {("c00003_s0000001", "old"): {WARNING}}'''
NEW = '''    class _DB:
        def ruled_segment_warnings(self):
            return {("c00003_s0000001", "old"): {WARNING}}'''
assert OLD in s, "khong khop _DB khong __init__"
s = s.replace(OLD, NEW, 1)

io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")
