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

    python scripts/pace_retry_reachability.py <log_path> [lower_bound] [upper_bound]

Read-only.
"""
from __future__ import annotations

import math
import re
import statistics
import sys
from pathlib import Path

DEFAULT_LOWER_BOUND = 12.5
DEFAULT_UPPER_BOUND = 24.5
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


def main(log_path: str, lower: float, upper: float) -> int:
    path = Path(log_path)
    if not path.is_file():
        print(f"không tìm thấy log: {path}")
        return 2
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

    print(f"cổng nhịp [{lower}, {upper}] ký tự/s, ngân sách hiện tại {budget_seen} lần")
    print(f"{len(retried_then_passed)} segment chạm cổng rồi qua - không tính ở đây")
    print()
    header = "  ".join(f"{value:>4}" for value in BUDGETS)
    print(f"{'segment':<30} {'các lần thử':<30} {'phía':>6} {'p/lần':>7}   {header}")
    reachable: list[str] = []
    for segment, by_attempt in sorted(attempts.items()):
        paces = [by_attempt[key] for key in sorted(by_attempt)]
        too_fast = statistics.fmean(paces) > upper
        bound = upper if too_fast else lower
        chance = _chance_per_attempt(paces, bound, too_fast)
        cells = "  ".join(
            f"{1 - (1 - chance) ** budget:4.0%}" if chance else "   -" for budget in BUDGETS
        )
        shown = " ".join(f"{value:5.2f}" for value in paces)
        side = "nhanh" if too_fast else "chậm"
        print(f"{segment[:30]:<30} {shown:<30} {side:>6} {chance:7.1%}   {cells}")
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
            "Nâng số lần thử không cứu được chúng, và nới cận dưới thì sai: trên 807 "
            "segment đã nhận, không segment nào rơi xuống dưới 12.5. Cần nhìn vào văn bản "
            "- một thang bậc ký tự đọc thành tên chữ cái vốn dĩ chậm hơn văn xuôi, và "
            "thước đo ký tự/giây đang định giá sai loại văn bản ấy."
        )
    return 0


if __name__ == "__main__":
    if not 1 <= len(sys.argv) - 1 <= 3:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(
        main(
            sys.argv[1],
            float(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_LOWER_BOUND,
            float(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_UPPER_BOUND,
        )
    )
