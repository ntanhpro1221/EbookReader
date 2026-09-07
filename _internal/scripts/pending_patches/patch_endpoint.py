"""Va database.py: ban thu ma CA HAI bo giai ma chep dung khong bi loai vi con tieng o cuoi."""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "ebook_reader" / "database.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''            signal = self._json_object(candidate["signal_json"], "candidate signal metrics")
            blocking_signal_flags = self._candidate_blocking_signal_flags(signal)
            dual_passed = dual_passed and not blocking_signal_flags'''

NEW = '''            signal = self._json_object(candidate["signal_json"], "candidate signal metrics")
            blocking_signal_flags = self._candidate_blocking_signal_flags(signal)
            if dual_passed:
                # generation_endpoint_active means the take still has energy at its end, and
                # it is there to catch a reading cut off mid-word. A transcript refutes that
                # directly: if both decoders wrote the whole expected text, nothing was cut.
                #
                # Left alone it does not catch truncation, it catches intonation that has not
                # fallen yet. Across 956 rejected takes in six versions it fired 14 times and
                # every single one was text ending in a comma or a question mark - 10 of 37
                # comma endings and 4 of 20 question endings, against 0 of 662 full stops, 0
                # of 202 exclamation marks and 0 of 35 ending in a letter. A comma means the
                # sentence continues and a question ends on a rise; both are supposed to keep
                # their energy.
                #
                # Two of those fourteen had both decoders passing outright. `"Rồi, rồi,"` in
                # alpha.55 produced takes at rounds 3 and 4 that beam and greedy both scored
                # 1.0 with zero WER, and both were thrown away over this flag - so the
                # segment kept an incumbent at 0.43, reported ASR_MISMATCH_UNRESOLVED, and
                # blocked its chapter permanently on a reason that was not the real one.
                #
                # Narrowed rather than removed: with a failing decode the flag still blocks,
                # and pace_outlier, pitch_variant_skipped and pitch_variant_mixed are
                # untouched in every case. _validated_dual_failed_candidate_conn deliberately
                # keeps the unnarrowed view, because it validates history that was recorded
                # under the old rule and must keep validating it.
                blocking_signal_flags = tuple(
                    flag
                    for flag in blocking_signal_flags
                    if flag != "generation_endpoint_active"
                )
            dual_passed = dual_passed and not blocking_signal_flags'''

assert OLD in s, "khong khop cho quyet dinh promote"
s = s.replace(OLD, NEW, 1)

io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")
