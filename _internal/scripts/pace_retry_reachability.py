"""How many attempts would the pace-failed segments actually have needed?

alpha.32 finished with three segments that never got audio. They were recorded as one
class - "the pace gate rejected them" - and the remedy was recorded as "more attempts or a
different seed". Neither claim survives reading the log.

They are not one class. Each segment gets tts.max_retries = 4 attempts, and the takes do
differ, so the spread of those four says whether the bound was ever within reach:

    c00010_s0000017   11.81  10.44  12.47  12.13   best 12.47, bound 12.50
    c00005_s0000013   11.05  11.82  12.25  12.25   best 12.25
    c00009_s0000008    9.22  10.51  10.70   9.36   best 10.70

The first missed by 0.03 chars/s. That is a coin toss, not a defect. The last is 17% short
of the bound and its text is a rank ladder - "C » B » A » S » SS » SSS" - where the voice
speaks letter names, so a characters-per-second bound calibrated on prose mis-prices it by
construction. No retry budget reaches it.

This reads the attempts out of a run's log and estimates, per segment, the chance a single
attempt clears the bound and what budget would have been needed. It separates "unlucky"
from "unreachable", which is the distinction that decides whether raising max_retries is
the answer.

    python scripts/pace_retry_reachability.py <project_root>

The bound is per segment, not global: tts.pace_chars_per_second gives slow [7.0, 19.0],
normal [12.5, 24.5] and fast [14.0, 30.0], and analysis picks which one a line gets. An
earlier version of this script assumed 12.5 for everything, which is right only for the
`normal` band - and alpha.43 lost a segment precisely because its analysis called a line
afraid/fast, raising the floor to 14.0 so that a take measuring 12.70 failed where the
identical take had passed at `normal`.

Read-only: opens the project database read-only and writes nothing.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import statistics
import sys
from pathlib import Path

# Mirrors tts.pace_chars_per_second. Read from the project's own settings when available so
# a retuned book is measured against its own gate rather than against this default.
DEFAULT_BANDS = {"slow": (7.0, 19.0), "normal": (12.5, 24.5), "fast": (14.0, 30.0)}
ATTEMPT = re.compile(
    r"TTS segment (?P<segment>\w+) chưa đạt lần (?P<attempt>\d+)/(?P<budget>\d+).*?"
    r"speech pace (?P<pace>[\d.]+) chars/s"
)
# Only a segment that ran out of attempts is a question. One that tripped the gate once and
# passed on the retry is the gate working, and counting it here made 11 segments look
# troubled when 3 were.
EXHAUSTED = re.compile(r"TTS segment (?P<segment>\w+) thất bại hoàn toàn")
BUDGETS = (4, 6, 8, 10, 12, 16)


def _chance_per_attempt(paces: list[float], bound: float, too_fast: bool) -> float:
    """Normal tail from this segment's own attempts.

    Four samples is a thin basis for a standard deviation and the number is quoted as an
    order of magnitude, not a probability to bet on. It is still enough to tell a segment
    sitting half a sigma from the bound from one sitting three sigma away, which is the
    only question being asked.
    """
    if len(paces) < 2:
        return 0.0
    spread = statistics.stdev(paces)
    if spread <= 0:
        return 1.0 if paces[0] >= bound else 0.0
    z = (bound - statistics.fmean(paces)) / spread
    tail = 0.5 * math.erfc(z / math.sqrt(2))
    # The gate has two bounds. Reading every rejection as "too slow" turned segments that
    # were rejected for racing - 25.30, 27.51 against an upper bound of 24.5 - into
    # segments that supposedly cleared the lower one every time.
    return 1.0 - tail if too_fast else tail


def _bands(root: Path) -> dict[str, tuple[float, float]]:
    settings = root / "book_settings.json"
    if not settings.is_file():
        return dict(DEFAULT_BANDS)
    try:
        raw = json.loads(settings.read_text(encoding="utf-8"))
        ranges = raw.get("tts", {}).get("pace_chars_per_second", {})
        return {key: (float(value[0]), float(value[1])) for key, value in ranges.items()} or dict(DEFAULT_BANDS)
    except Exception:  # noqa: BLE001
        return dict(DEFAULT_BANDS)


def _segment_bands(root: Path) -> dict[str, str]:
    database = root / "project.sqlite3"
    if not database.is_file():
        return {}
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    out = {str(row["stable_id"]): str(row["pace"] or "normal")
           for row in connection.execute("SELECT stable_id, pace FROM segments")}
    connection.close()
    return out


def main(project_root: str) -> int:
    root = Path(project_root)
    path = root / "logs" / "ebook_reader.log"
    if not path.is_file():
        print(f"không tìm thấy log: {path}")
        return 2
    bands = _bands(root)
    segment_band = _segment_bands(root)
    text = path.read_text(encoding="utf-8", errors="replace")

    exhausted = {match.group("segment") for match in EXHAUSTED.finditer(text)}
    attempts: dict[str, dict[int, float]] = {}
    budget_seen = 0
    for match in ATTEMPT.finditer(text):
        # A resumed run repeats the same attempts verbatim; keyed by attempt number so a
        # replay does not inflate the sample.
        attempts.setdefault(match.group("segment"), {})[int(match.group("attempt"))] = float(
            match.group("pace")
        )
        budget_seen = max(budget_seen, int(match.group("budget")))
    retried_then_passed = sorted(set(attempts) - exhausted)
    attempts = {key: value for key, value in attempts.items() if key in exhausted}
    if not attempts:
        print("không segment nào hết lượt vì cổng nhịp")
        if retried_then_passed:
            print(f"({len(retried_then_passed)} segment chạm cổng rồi qua ở lần sau)")
        return 0

    print("cổng nhịp theo dải: " + ", ".join(f"{k} [{v[0]}, {v[1]}]" for k, v in sorted(bands.items()))
          + f"; ngân sách hiện tại {budget_seen} lần")
    print(f"{len(retried_then_passed)} segment chạm cổng rồi qua - không tính ở đây")
    print()
    header = "  ".join(f"{value:>4}" for value in BUDGETS)
    print(f"{'segment':<30} {'các lần thử':<26} {'dải':>6} {'phía':>6} {'p/lần':>7}   {header}")
    reachable: list[str] = []
    for segment, by_attempt in sorted(attempts.items()):
        paces = [by_attempt[key] for key in sorted(by_attempt)]
        band = segment_band.get(segment, "normal")
        lower, upper = bands.get(band, bands.get("normal", (12.5, 24.5)))
        too_fast = statistics.fmean(paces) > upper
        bound = upper if too_fast else lower
        chance = _chance_per_attempt(paces, bound, too_fast)
        cells = "  ".join(
            f"{1 - (1 - chance) ** budget:4.0%}" if chance else "   -" for budget in BUDGETS
        )
        shown = " ".join(f"{value:5.2f}" for value in paces)
        side = "nhanh" if too_fast else "chậm"
        print(f"{segment[:30]:<30} {shown:<26} {band:>6} {side:>6} {chance:7.1%}   {cells}")
        if chance >= 0.05:
            reachable.append(segment)

    print()
    if reachable:
        print(
            f"{len(reachable)}/{len(attempts)} segment nằm trong tầm với: chúng trượt vì "
            f"hết lượt, không phải vì giọng không đọc nổi. Nâng tts.max_retries chỉ tốn "
            "thêm lượt cho đúng những segment đang hỏng - phần còn lại của sách không "
            "chạm tới ngân sách ấy."
        )
    unreachable = [key for key in attempts if key not in reachable]
    if unreachable:
        print(
            f"{len(unreachable)}/{len(attempts)} segment ngoài tầm với ở mọi ngân sách. "
            "Thêm lượt thử không cứu được, và nới cận thì sai - trên 807 segment đã nhận "
            "không cái nào rơi xuống dưới cận của dải nó. Hai nguyên nhân khác nhau, và "
            "cột `dải` ở trên phân biệt chúng:"
        )
        # The distinction decides who fixes it. A `normal` segment that cannot reach its
        # floor is about the text. A `slow`/`fast` one is about the directive analysis gave
        # it, and the same audio would have passed in another band - which is how alpha.43
        # lost c00007_s0000074 at 12.70 against a `fast` floor of 14.0 after alpha.32 passed
        # the identical take at `normal`.
        for segment in unreachable:
            band = segment_band.get(segment, "normal")
            if band == "normal":
                print(f"    {segment[:30]:<30} dải normal - vấn đề ở **văn bản**: một thang "
                      "bậc ký tự đọc thành tên chữ cái vốn chậm hơn văn xuôi.")
            else:
                low = bands.get(band, (0.0, 0.0))[0]
                print(f"    {segment[:30]:<30} dải {band} (cận {low}) - vấn đề ở **chỉ dẫn "
                      f"diễn xuất**, không phải bản thu: cùng bản thu ấy sẽ qua ở dải normal. "
                      "Phân tích đã gán một nhịp mà câu này không đọc tới được.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
