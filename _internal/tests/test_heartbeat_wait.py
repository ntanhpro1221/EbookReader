"""Chờ nền có trần: không bao giờ quá 30 phút, và thức sớm khi điều kiện đạt - xem docstring của script."""
from __future__ import annotations

import os
import time

import pytest

import scripts.heartbeat_wait as hw


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def test_a_wait_longer_than_thirty_minutes_is_refused() -> None:
    with pytest.raises(ValueError):
        hw.wait(None, hw.CAP_SECONDS + 1, 60)
    assert hw.main(["--max", str(hw.CAP_SECONDS + 1)]) == 2


def test_without_a_condition_it_wakes_at_the_cap_and_never_later() -> None:
    fake = FakeClock()
    reason, _ = hw.wait(None, 1800, 700, clock=fake.clock, sleep=fake.sleep)
    assert reason == hw.CAP_REACHED
    assert fake.now == 1800, "buoc cuoi phai ngan lai de khong vuot tran"
    assert fake.slept == [700, 700, 400]


def test_a_condition_that_holds_wakes_it_early() -> None:
    fake = FakeClock()
    answers = iter([(False, ""), (False, ""), (True, "du 40 doan")])
    reason, output = hw.wait(["x.py"], 1800, 120, clock=fake.clock, sleep=fake.sleep,
                             check=lambda _until: next(answers))
    assert (reason, output) == (hw.CONDITION_MET, "du 40 doan")
    assert fake.now == 240


def test_a_condition_that_never_holds_still_stops_at_the_cap() -> None:
    fake = FakeClock()
    reason, _ = hw.wait(["x.py"], 600, 120, clock=fake.clock, sleep=fake.sleep,
                        check=lambda _until: (False, "WAIT 3"))
    assert reason == hw.CAP_REACHED and fake.now == 600


def test_a_silent_daemon_is_reported_with_the_command_to_restart_it(tmp_path, monkeypatch) -> None:
    last = tmp_path / "heartbeat_last.txt"
    monkeypatch.setattr(hw, "LAST", last)
    assert "chua tung chay" in hw.daemon_warning()
    last.write_text("x", encoding="utf-8")
    fresh = time.time()
    os.utime(last, (fresh, fresh))
    assert hw.daemon_warning(now=fresh + 60) == ""
    warning = hw.daemon_warning(now=fresh + hw.DAEMON_SILENT_SECONDS + 60)
    assert "im" in warning and "Start-Process" in warning and "heartbeat_daemon.py" in warning
