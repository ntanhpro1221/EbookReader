"""Hai chuông của nhịp tim (26-09): A reo theo sự kiện, B reo khi A im quá lâu. Xem `scripts/bells.py`.

Mọi phép thử ở đây chạy trên ảnh chụp giả và đồng hồ giả - không phụ thuộc tiến trình thật nào đang chạy trên máy,
vì bộ test đầy đủ chạy ngay giữa ranh giới, lúc chính `boundary.sh` đang sống.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

import scripts.bells as bells
import scripts.heartbeat_event as event
import scripts.heartbeat_timeout as timeout_bell


def shot(roots=("boundary.sh 18",), done=3, last_done=(), problems=(), battery=False):
    return {"roots": None if roots is None else list(roots), "done": done, "last_done": list(last_done),
            "problems": list(problems), "battery": battery}


# --- chuông A ------------------------------------------------------------------------------------------


def test_a_detached_run_finishing_rings_at_once() -> None:
    """Ca của sáng 26-09: ranh giới 17 ghi "xong (mã 0)" lúc 08:47 - phải reo ở lần dò kế, không đợi giờ."""
    watch = event.Watch(shot(done=3))
    line = "2026-09-26 08:47:23 pid=7000 xong (mã 0): bash scripts/boundary.sh 17"
    ring = watch.observe(shot(done=4, last_done=[line]))
    assert ring and "xong (mã 0)" in ring[0]


def test_a_boundary_vanishing_rings_only_after_two_polls() -> None:
    watch = event.Watch(shot(roots=["boundary.sh 18"]))
    assert watch.observe(shot(roots=[])) == []
    ring = watch.observe(shot(roots=[]))
    assert ring == ["boundary.sh 18 không còn chạy (xong hoặc chết)"]


def test_a_a_shadow_for_one_poll_does_not_ring() -> None:
    """Ngay sau khi thả ranh giới, phép đếm từng thấy bóng vài giây - một lần dò lệch rồi trở lại thì im."""
    watch = event.Watch(shot(roots=["boundary.sh 18"]))
    assert watch.observe(shot(roots=[])) == []
    assert watch.observe(shot(roots=["boundary.sh 18"])) == []
    assert watch.observe(shot(roots=[])) == []


def test_a_unreadable_process_list_is_not_a_death() -> None:
    watch = event.Watch(shot(roots=["boundary.sh 18"]))
    for _ in range(3):
        assert watch.observe(shot(roots=None)) == []


def test_a_a_boundary_i_just_launched_is_watched_silently_then_rings_when_it_ends() -> None:
    watch = event.Watch(shot(roots=[]))
    assert watch.observe(shot(roots=["boundary.sh 19"])) == []
    assert watch.observe(shot(roots=["boundary.sh 19"])) == []
    assert "boundary.sh 19" in watch.roots
    watch.observe(shot(roots=[]))
    assert watch.observe(shot(roots=[])) == ["boundary.sh 19 không còn chạy (xong hoặc chết)"]


def test_a_rings_on_a_new_problem_but_not_an_old_one() -> None:
    watch = event.Watch(shot(problems=["ĐỨNG IM lo09_x"]))
    assert watch.observe(shot(problems=["ĐỨNG IM lo09_x"])) == []
    assert watch.observe(shot(problems=["ĐỨNG IM lo09_x", "CHẾT lo18_y"])) == []
    assert watch.observe(shot(problems=["ĐỨNG IM lo09_x", "CHẾT lo18_y"])) == ["project CHẾT lo18_y"]


def test_a_rings_when_the_charger_comes_out_not_while_it_stays_out() -> None:
    """24-09: sạc rút lúc 22:50, không ai biết tới 00:07. Sườn lên thì reo; đang chạy pin từ trước thì không."""
    unplugged = event.Watch(shot(battery=False))
    unplugged.observe(shot(battery=True))
    assert unplugged.observe(shot(battery=True)) == ["máy chuyển sang chạy PIN"]

    already = event.Watch(shot(battery=True))
    assert already.observe(shot(battery=True)) == []
    assert already.observe(shot(battery=False)) == []
    already.observe(shot(battery=True))
    assert already.observe(shot(battery=True)) == ["máy chuyển sang chạy PIN"]


def test_a_names_a_detached_boundary_tree_once() -> None:
    procs = [
        (25992, 1000, "C:\\Windows\\explorer.exe"),
        (24536, 25992, "runtime\\.venv\\Scripts\\pythonw.exe scripts\\run_detached.py bash scripts/boundary.sh 18"),
        (56044, 24536, "C:\\Python311\\pythonw.exe scripts\\run_detached.py bash scripts/boundary.sh 18"),
        (33104, 56044, "C:\\Program Files\\Git\\bin\\bash.exe scripts/boundary.sh 18"),
        (34616, 33104, "C:\\Program Files\\Git\\usr\\bin\\bash.exe scripts/boundary.sh 18"),
    ]
    assert event.boundary_roots(procs) == ["boundary.sh 18"]
    assert event.boundary_roots(None) is None


def test_a_reads_finished_detached_runs(tmp_path) -> None:
    log = tmp_path / "detached_runs.log"
    log.write_text(
        "2026-09-25 23:41:03 pid=7000 bắt đầu: bash scripts/boundary.sh 17\n"
        "2026-09-26 08:47:23 pid=7000 xong (mã 0): bash scripts/boundary.sh 17\n",
        encoding="utf-8",
    )
    assert event.finished_runs(log) == ["2026-09-26 08:47:23 pid=7000 xong (mã 0): bash scripts/boundary.sh 17"]
    assert event.finished_runs(tmp_path / "missing.log") == []


# --- chuông B ------------------------------------------------------------------------------------------


class FakeClock:
    def __init__(self, start: float) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_b_rings_its_hours_after_it_starts() -> None:
    clock = FakeClock(1000.0)
    deadline = timeout_bell.wait_out(1000.0, 2.0, 60.0, clock=clock, sleep=clock.sleep, reset=lambda: None)
    assert deadline == 1000.0 + 7200.0
    assert clock.now == deadline


def test_b_counts_from_zero_again_when_a_rings() -> None:
    """"mỗi khi heartbeat A được reo lên thì reset luôn heartbeat B lại từ đầu" - A reo ở phút 60 thì B dời tới
    phút 180, không reo ở phút 120."""
    clock = FakeClock(1000.0)
    reset_at: list[float] = []

    def sleep(seconds: float) -> None:
        clock.sleep(seconds)
        if not reset_at and clock.now >= 1000.0 + 3600.0:
            reset_at.append(clock.now)

    deadline = timeout_bell.wait_out(1000.0, 2.0, 60.0, clock=clock, sleep=sleep,
                                     reset=lambda: reset_at[0] if reset_at else None)
    assert deadline == reset_at[0] + 7200.0


def test_b_ignores_a_reset_older_than_itself() -> None:
    clock = FakeClock(1000.0)
    deadline = timeout_bell.wait_out(1000.0, 2.0, 60.0, clock=clock, sleep=clock.sleep, reset=lambda: 10.0)
    assert deadline == 1000.0 + 7200.0


# --- phần chung ----------------------------------------------------------------------------------------


def test_a_dead_or_foreign_pid_is_not_a_live_bell() -> None:
    assert not bells.alive(None, bells.EVENT_MARKER)
    assert not bells.alive(4_000_000, bells.EVENT_MARKER)
    assert not bells.alive(os.getpid(), "không-script-nào-tên-thế-này.py")


def test_a_second_bell_of_the_same_kind_is_refused(tmp_path) -> None:
    """Hai chuông A cùng canh thì mỗi sự kiện reo hai lần - cái thứ hai phải tự lui."""
    state = tmp_path / "bell.json"
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)  # bell_marker_probe"],
                               creationflags=flags)
    try:
        deadline = time.time() + 20
        while not bells.alive(sleeper.pid, "bell_marker_probe") and time.time() < deadline:
            time.sleep(0.1)
        bells.write_state(state, {"pid": sleeper.pid, "started_at": 1.0})
        assert bells.claim(state, "bell_marker_probe", {})["pid"] == sleeper.pid
        assert bells.read_state(state)["pid"] == sleeper.pid
    finally:
        sleeper.kill()
        sleeper.wait(timeout=20)
    assert bells.claim(state, "bell_marker_probe", {}) is None
    assert bells.read_state(state)["pid"] == os.getpid()
    bells.release(state)
    assert not state.exists()


def test_the_tick_line_says_when_no_bell_is_watching(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(bells, "EVENT_STATE", tmp_path / "a.json")
    monkeypatch.setattr(bells, "TIMEOUT_STATE", tmp_path / "b.json")
    assert bells.describe() == "chuông: A KHÔNG CHẠY | B KHÔNG CHẠY"
