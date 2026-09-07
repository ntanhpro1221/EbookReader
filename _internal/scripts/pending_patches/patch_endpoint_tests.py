"""Va test: endpoint chi con chan khi mot lan giai ma truot."""
import io
import sys
from pathlib import Path

root = Path(sys.argv[1])
p = root / "tests" / "test_database_safety.py"
s = io.open(p, encoding="utf-8").read()

OLD = '''        ("generation_endpoint_active", {"generation_endpoint_active": 1.0}, {}),
        ("pace_outlier", {"pace_outlier": 1.0}, {}),
    ],
)'''

NEW = '''        ("pace_outlier", {"pace_outlier": 1.0}, {}),
    ],
)'''

assert OLD in s, "khong khop danh sach parametrize"
s = s.replace(OLD, NEW, 1)

TEST = '''

def test_a_take_both_decoders_accepted_survives_the_endpoint_signal(tmp_path: Path) -> None:
    """generation_endpoint_active must not outvote two transcripts of the whole line.

    The flag fires when the take still has energy at its end, and it is there to catch a
    reading cut off mid-word. A transcript refutes that directly: if both decoders wrote out
    the expected text, nothing was cut.

    Unnarrowed it did not catch truncation, it caught intonation that had not fallen yet.
    Across 956 rejected takes in alpha.50-55 it fired fourteen times and every one was text
    ending in a comma or a question mark - 10 of 37 comma endings, 4 of 20 question endings,
    against 0 of 662 full stops, 0 of 202 exclamation marks, 0 of 35 ending in a letter. A
    comma means the sentence continues and a question ends on a rise; both are supposed to
    keep their energy.

    `"Rồi, rồi,"` in alpha.55 produced takes at rounds 3 and 4 that beam and greedy both
    scored 1.0 with zero WER. Both were discarded over this flag, the segment kept an
    incumbent at 0.43, reported ASR_MISMATCH_UNRESOLVED - a reason its own record contradicts
    - and blocked chapter 016 permanently.
    """
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate_path = tmp_path / "candidates" / "r0.wav"
    candidate_sha256 = _write_candidate_artifact(candidate_path, "endpoint-but-heard")
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=351,
        wav_path=candidate_path,
        candidates_root=tmp_path / "candidates",
    )
    candidate_id = int(candidate["id"])
    _checkpoint_candidate_signal(
        db,
        candidate_id,
        repair_round=0,
        generation_seed=351,
        wav_path=candidate_path,
        wav_sha256=candidate_sha256,
        signal_overrides={"generation_endpoint_active": 1.0},
    )
    for confirmation in (False, True):
        check_id = _candidate_decode_check(
            db,
            segment_id=segment_id,
            artifact_sha256=candidate_sha256,
            repair_round=0,
            generation_seed=351,
            confirmation=confirmation,
            verdict="pass",
            reason="ok",
        )
        db.checkpoint_segment_candidate_decode(
            candidate_id,
            quality_check_id=check_id,
            confirmation=confirmation,
        )

    row = db.get_segment_candidate(candidate_id)

    assert str(row["state"]) == "dual_passed"
    assert not str(row["failure_reason"] or "")


def test_the_endpoint_signal_still_blocks_when_a_decode_fails(tmp_path: Path) -> None:
    """Narrowed, not removed: without a transcript to refute it the flag keeps its say."""
    db, segment_id, incumbent_sha256, _incumbent_path = _candidate_db(tmp_path)
    candidate_path = tmp_path / "candidates" / "r0.wav"
    candidate_sha256 = _write_candidate_artifact(candidate_path, "endpoint-and-misheard")
    candidate = db.allocate_segment_candidate(
        segment_id=segment_id,
        policy_hash="candidate-policy-v1",
        repair_round=0,
        max_repair_rounds=2,
        incumbent_sha256=incumbent_sha256,
        generation_seed=351,
        wav_path=candidate_path,
        candidates_root=tmp_path / "candidates",
    )
    candidate_id = int(candidate["id"])
    _checkpoint_candidate_signal(
        db,
        candidate_id,
        repair_round=0,
        generation_seed=351,
        wav_path=candidate_path,
        wav_sha256=candidate_sha256,
        signal_overrides={"generation_endpoint_active": 1.0},
    )
    for confirmation in (False, True):
        check_id = _candidate_decode_check(
            db,
            segment_id=segment_id,
            artifact_sha256=candidate_sha256,
            repair_round=0,
            generation_seed=351,
            confirmation=confirmation,
            verdict="fail" if confirmation else "pass",
            reason="ok" if not confirmation else "ASR_MISMATCH",
        )
        db.checkpoint_segment_candidate_decode(
            candidate_id,
            quality_check_id=check_id,
            confirmation=confirmation,
        )

    row = db.get_segment_candidate(candidate_id)

    assert str(row["state"]) == "dual_failed"
    assert "generation_endpoint_active" in str(row["failure_reason"] or "")
'''

s = s.rstrip() + "\n" + TEST
io.open(p, "w", encoding="utf-8").write(s)
print(f"da va {p}")
