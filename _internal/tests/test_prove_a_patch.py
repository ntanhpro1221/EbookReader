"""Bốn kết cục của một lô vá, và ba trong bốn không phải bằng chứng.

Sau lô vá của lô 1 tôi hỏi "chương xanh chưa?" và coi bốn bản vá là đã chứng minh; ba trong bốn
thì không — mã đơn giản không nổ lại, vì lỗi phụ thuộc seed. Bài này ghim đúng chỗ ấy: một đoạn
sạch phải đọc thành *KHÔNG TÁI DIỄN — không chứng minh gì*, chứ không thành "xanh rồi".
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.prove_a_patch import compare, read_segments, text_key, verdict


def _project(
    root: Path,
    name: str,
    chapters: dict[str, tuple[str, list[dict[str, object]]]],
    *,
    machine_accepted: list[str] = [],
) -> Path:
    """`chapters` = {tiêu đề: (trạng thái chương, [đoạn])}; mỗi đoạn cần `hash` và có thể có
    `status`, `warning_code`, `error`, `attempts`, `text`."""
    folder = root / name
    folder.mkdir(parents=True)
    conn = sqlite3.connect(str(folder / "project.sqlite3"))
    try:
        conn.executescript(
            """
            CREATE TABLE chapters (id INTEGER PRIMARY KEY, title TEXT, status TEXT);
            CREATE TABLE segments (
                id INTEGER PRIMARY KEY, chapter_id INTEGER, stable_id TEXT, status TEXT,
                warning_code TEXT, error TEXT, attempt_count INTEGER, text TEXT
            );
            CREATE TABLE machine_audio_acceptances (
                id INTEGER PRIMARY KEY, segment_stable_id TEXT, warning_code TEXT
            );
            """
        )
        for index, (title, (status, segments)) in enumerate(chapters.items(), 1):
            conn.execute("INSERT INTO chapters VALUES (?,?,?)", (index, title, status))
            for seq, segment in enumerate(segments, 1):
                conn.execute(
                    "INSERT INTO segments (chapter_id, stable_id, status, warning_code, error,"
                    " attempt_count, text) VALUES (?,?,?,?,?,?,?)",
                    (
                        index,
                        f"c{index:05d}_s{seq:07d}_{segment['hash']}",
                        segment.get("status", "verified"),
                        segment.get("warning_code", ""),
                        segment.get("error", ""),
                        segment.get("attempts", 1),
                        segment.get("text", "Một câu."),
                    ),
                )
        for stable_id in machine_accepted:
            conn.execute(
                "INSERT INTO machine_audio_acceptances (segment_stable_id, warning_code)"
                " VALUES (?,?)",
                (stable_id, "ASR_MISMATCH_UNRESOLVED"),
            )
        conn.commit()
    finally:
        conn.close()
    return folder


def test_segments_match_across_projects_by_text_not_by_stable_id(tmp_path: Path) -> None:
    """Chương 075 là `c00016` trong lô và `c00001` trong project vá một chương."""
    assert text_key("c00016_s0000007_2dd21f158c6c") == "2dd21f158c6c"
    assert text_key("c00001_s0000001_2dd21f158c6c") == "2dd21f158c6c"

    batch = _project(
        tmp_path,
        "lo03",
        {
            "074": ("completed", [{"hash": "aaaaaaaaaaaa"}]),
            "075": ("failed", [{"hash": "2dd21f158c6c", "status": "failed"}]),
        },
    )
    repair = _project(
        tmp_path, "lo03v_075", {"075": ("completed", [{"hash": "2dd21f158c6c"}])}
    )

    assert ("075", "2dd21f158c6c") in read_segments(batch)
    watched, _fresh = compare(batch, repair)
    assert [row["chapter"] for row in watched] == ["075"], "chương 074 không có ở project mới"


def test_a_clean_segment_proves_nothing(tmp_path: Path) -> None:
    batch = _project(
        tmp_path,
        "lo03",
        {"075": ("failed", [{"hash": "2dd21f158c6c", "status": "failed", "attempts": 11}])},
    )
    repair = _project(
        tmp_path, "lo03v_075", {"075": ("completed", [{"hash": "2dd21f158c6c"}])}
    )

    watched, _fresh = compare(batch, repair)

    assert [row["verdict"] for row in watched] == ["KHÔNG TÁI DIỄN"]
    assert "không chứng minh gì" in str(watched[0]["why"])


def test_a_code_that_fires_again_but_ships_is_the_evidence(tmp_path: Path) -> None:
    """Bằng chứng thật: phép kiểm vẫn nói điều nó thấy, quyết định thì đổi."""
    batch = _project(
        tmp_path,
        "lo02",
        {"031": ("failed", [{"hash": "beefbeefbeef", "warning_code": "ASR_MISMATCH_UNRESOLVED"}])},
    )
    repair = _project(
        tmp_path,
        "lo02v_031",
        {
            "031": (
                "completed",
                [{"hash": "beefbeefbeef", "warning_code": "ASR_MISMATCH_UNRESOLVED"}],
            )
        },
        machine_accepted=["c00001_s0000001_beefbeefbeef"],
    )

    watched, _fresh = compare(batch, repair)

    assert [row["verdict"] for row in watched] == ["ĐI ĐƯỜNG KHÁC"]
    assert "máy" in str(watched[0]["why"]), "phải nói bảng nào đã ghi quyết định"


def test_a_code_that_still_blocks_says_so(tmp_path: Path) -> None:
    batch = _project(
        tmp_path,
        "lo03",
        {"075": ("failed", [{"hash": "2dd21f158c6c", "status": "failed"}])},
    )
    repair = _project(
        tmp_path,
        "lo03v_075",
        {
            "075": (
                "failed",
                [
                    {
                        "hash": "2dd21f158c6c",
                        "status": "failed",
                        "attempts": 10,
                        "error": "high-quality TTS retry required: speech pace 11.00 chars/s",
                    }
                ],
            )
        },
    )

    watched, _fresh = compare(batch, repair)

    assert [row["verdict"] for row in watched] == ["VẪN CHẶN"]
    assert "10 lần thử" in str(watched[0]["why"])


def test_a_failed_segment_in_a_published_chapter_is_not_called_blocked(tmp_path: Path) -> None:
    """Ca thật: lô 2 chương 031, đoạn "Tao là Bradly Stormwatch!" vẫn `failed` mà chương vẫn lên
    sách - cơ chế xuất-bản-không-người-nghe. Bản đầu của `verdict` kiểm `failed` trước và gọi
    đó là "VẪN CHẶN", tức nói một chương đã xuất bản là bị chặn."""
    batch = _project(
        tmp_path,
        "lo02",
        {"031": ("failed", [{"hash": "b0b0b0b0b0b0", "warning_code": "ASR_LOCKED_NAME_ANCHOR_MISMATCH"}])},
    )
    repair = _project(
        tmp_path,
        "lo02v_031",
        {
            "031": (
                "completed",
                [{"hash": "b0b0b0b0b0b0", "status": "failed", "error": "ASR mismatch remained"}],
            )
        },
    )

    watched, _fresh = compare(batch, repair)

    assert [row["verdict"] for row in watched] == ["HỎNG, CHƯƠNG VẪN XUẤT"]
    assert "chương xuất bản được" in str(watched[0]["why"])


def test_a_different_code_on_the_same_line_says_so(tmp_path: Path) -> None:
    """"Mã cũ nổ lại" và "một mã khác nổ trên cùng câu ấy" là hai sự thật khác nhau."""
    batch = _project(
        tmp_path,
        "lo02",
        {
            "053": (
                "failed",
                [{"hash": "d0d0d0d0d0d0", "warning_code": "ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE"}],
            )
        },
    )
    repair = _project(
        tmp_path,
        "lo02v_053",
        {
            "053": (
                "completed",
                [{"hash": "d0d0d0d0d0d0", "warning_code": "ASR_UNVERIFIABLE_SHORT_TEXT"}],
            )
        },
    )

    watched, _fresh = compare(batch, repair)

    assert watched[0]["verdict"] == "ĐI ĐƯỜNG KHÁC"
    assert "mã ĐỔI ASR_TRANSCRIPT_TIMELINE_IMPOSSIBLE → ASR_UNVERIFIABLE_SHORT_TEXT" in str(
        watched[0]["why"]
    )


def test_a_rewritten_line_is_reported_as_lost_not_as_fixed(tmp_path: Path) -> None:
    """Văn bản đổi thì hash đổi, và im lặng coi đó là 'đã sửa' là tự lừa mình."""
    batch = _project(
        tmp_path,
        "lo03",
        {"075": ("failed", [{"hash": "2dd21f158c6c", "status": "failed"}])},
    )
    repair = _project(
        tmp_path, "lo03v_075", {"075": ("completed", [{"hash": "ffffffffffff"}])}
    )

    watched, _fresh = compare(batch, repair)

    assert [row["verdict"] for row in watched] == ["MẤT ĐOẠN"]


def test_a_new_code_in_the_repair_is_surfaced(tmp_path: Path) -> None:
    """Lô vá chữa một thứ và làm hỏng thứ khác là kết cục phải thấy được, không phải đoán."""
    batch = _project(
        tmp_path,
        "lo03",
        {
            "075": (
                "failed",
                [
                    {"hash": "2dd21f158c6c", "status": "failed"},
                    {"hash": "cafecafecafe"},
                ],
            )
        },
    )
    repair = _project(
        tmp_path,
        "lo03v_075",
        {
            "075": (
                "completed",
                [
                    {"hash": "2dd21f158c6c"},
                    {"hash": "cafecafecafe", "warning_code": "TTS_SPLIT_RECOVERY"},
                ],
            )
        },
    )

    watched, fresh = compare(batch, repair)

    assert [row["verdict"] for row in watched] == ["KHÔNG TÁI DIỄN"]
    assert [(row["chapter"], row["warning_code"]) for row in fresh] == [
        ("075", "TTS_SPLIT_RECOVERY")
    ]


def test_a_chapter_still_running_is_not_reported_as_blocked(tmp_path: Path) -> None:
    """Chạy công cụ trong khi chương đúc lại còn `verifying` thì mười đoạn đọc thành "VẪN CHẶN" -
    tức báo một chương đang chạy là đã thất bại. Đúng lỗi tôi mắc lúc 21:45 ngày 2026-09-10."""
    batch = _project(
        tmp_path,
        "lo03",
        {"075": ("failed", [{"hash": "2dd21f158c6c", "warning_code": "ASR_MISMATCH_UNRESOLVED"}])},
    )
    repair = _project(
        tmp_path,
        "lo03v_075",
        {
            "075": (
                "verifying",
                [{"hash": "2dd21f158c6c", "warning_code": "ASR_MISMATCH_UNRESOLVED"}],
            )
        },
    )

    watched, _fresh = compare(batch, repair)

    assert [row["verdict"] for row in watched] == ["CHƯA XONG"]
    assert "hỏi lại khi nó xong" in str(watched[0]["why"])


def test_verdict_without_a_new_row_is_a_lost_segment() -> None:
    label, why = verdict({"warning_code": "X", "status": "failed"}, None)
    assert label == "MẤT ĐOẠN" and "project mới" in why
