"""Does a sentence carrying a transliterated name read slower, or were those three a tail?

alpha.32 finished with three segments that never got audio at all. Four synthesis attempts
each - tts.max_retries, not the "five to fifteen" an earlier note in this file claimed -
every take rejected by the pace gate for being too slow, and the sentences too short to
split:

    Tên tôi là Samael Kaizer Theosbane.                     12.25 chars/s
    Ông ta chính là cha tôi, Arthur Kaizer Theosbane.       12.13 chars/s
    Cấp Linh Hồn ... C » B » A » S » SS » SSS                9.36 chars/s

The bound is 12.5 and it is not mis-set: over 807 accepted segments the median is 15.82,
the fifth percentile is 13.69, and not one falls below. Those three really are slower than
every take the run accepted.

Two of the three read a name the project itself turned into hyphenated Vietnamese
syllables - "Samael Kaizer Theosbane" becomes "Xa-ma-eo Cai-dơ Thê-ô-xờ-ben" - and the
voice says those deliberately. If that is systematic, the pace gate and the transliterator
are two features of one project working against each other, and the gate needs to know.
If it is not, three sentences drew a short straw and nothing should change.

Since written, scripts/pace_retry_reachability.py has shown the three are not one class:
two missed the bound by 0.03 and 0.25 chars/s and would clear it most of the time given
more attempts, while the third reads a rank ladder aloud and no budget reaches it. The
question below is still worth asking - it is about the other two - but "the three" is no
longer a thing.

n=3 cannot tell those apart. This asks the whole book: it splits accepted segments by
whether a locked-name anchor lands in them and compares the pace distributions, computed
exactly the way audio_io computes them - speakable characters over speech seconds with the
pauses punctuation forces taken out.

    python scripts/pace_of_transliterated_names.py <project_root> [<project_root> ...]
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import statistics
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ebook_reader.audio_io import (  # noqa: E402
    MAX_PAUSE_FRACTION,
    MIN_SPEECH_SECONDS,
    PAUSE_GROUP_SECONDS,
    pause_group_count,
)
from ebook_reader.database import ProjectDB  # noqa: E402
from ebook_reader.tts import TTSCoordinator  # noqa: E402


def _pace(spoken: str, duration: float) -> float | None:
    speakable = sum(character.isalnum() for character in spoken)
    if speakable < 24 or duration <= 0:
        return None
    pause = min(PAUSE_GROUP_SECONDS * pause_group_count(spoken), duration * MAX_PAUSE_FRACTION)
    return speakable / max(duration - pause, MIN_SPEECH_SECONDS)


def _collect(root: Path) -> tuple[list[float], list[float]]:
    database = root / "project.sqlite3"
    if not database.is_file():
        return [], []
    workspace = Path(tempfile.mkdtemp(prefix="pace-names-"))
    working = workspace / "project.sqlite3"
    shutil.copy2(database, working)
    settings = json.loads((root / "book_settings.json").read_text(encoding="utf-8"))
    db = ProjectDB(working)
    tts = TTSCoordinator(settings, db, lambda _message: None)

    connection = sqlite3.connect(f"file:{working}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        "SELECT * FROM segments WHERE status IN ('verified','warning') AND wav_duration > 0"
    ).fetchall()
    connection.close()

    with_name: list[float] = []
    without_name: list[float] = []
    for row in rows:
        try:
            spoken, anchors = tts.spoken_text_with_anchors(row)
        except Exception:  # noqa: BLE001
            continue
        rate = _pace(spoken, float(row["wav_duration"]))
        if rate is None:
            continue
        (with_name if anchors else without_name).append(rate)
    return with_name, without_name


def _describe(label: str, values: list[float], bound: float) -> None:
    if not values:
        print(f"  {label:<28} (không có mẫu)")
        return
    ordered = sorted(values)
    count = len(ordered)
    below = sum(1 for value in ordered if value < bound)
    print(
        f"  {label:<28} n={count:<5} trung vị {statistics.median(ordered):6.2f}"
        f"  p5 {ordered[count // 20]:6.2f}  p25 {ordered[count // 4]:6.2f}"
        f"  dưới {bound}: {below} ({below / count:.1%})"
    )


def main(roots: list[str]) -> int:
    with_name: list[float] = []
    without_name: list[float] = []
    for value in roots:
        left, right = _collect(Path(value))
        print(f"{Path(value).name}: {len(left)} có tên khoá, {len(right)} không")
        with_name.extend(left)
        without_name.extend(right)
    if not with_name or not without_name:
        print("cần cả hai nhóm mới so được")
        return 1

    bound = 12.5
    print()
    print(f"nhịp đọc (ký tự nói được / giây nói, đã trừ khoảng lặng), cận dưới {bound}:")
    _describe("có tên chuyển tự", with_name, bound)
    _describe("không có", without_name, bound)

    difference = statistics.median(without_name) - statistics.median(with_name)
    print()
    print(f"  chênh lệch trung vị: {difference:+.2f} ký tự/s")
    pooled = statistics.pstdev(with_name + without_name)
    if pooled:
        print(f"  tính theo độ lệch chuẩn gộp: {difference / pooled:+.2f} sigma")
    print()
    if difference > 0.5:
        print(
            "Câu có tên chuyển tự đọc chậm hơn một cách hệ thống. Cổng nhịp và bộ chuyển "
            "tự đang đánh nhau, và cổng cần biết về những câu ấy."
        )
    else:
        print(
            "Không có khác biệt hệ thống. Ba segment không có audio của alpha.32 là đuôi "
            "phân bố, không phải một lớp - đừng nới cổng vì chúng."
        )
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1:]))
