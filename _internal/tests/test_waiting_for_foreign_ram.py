"""A run does not throw away its afternoon because another program took the memory.

alpha.26 stopped at 357 of 948 segments on "available RAM 1.1 GB" while three Unity
editors and an IDE held about five and a half gigabytes. The run was not the cause - it
had already unloaded its own models and the measurement still went 1.4 -> 1.1 GB. Every
gigabyte of that shortage comes back on its own when the other program closes, so the run
idles through it instead of dying, and resumes by itself.

Waiting is only safe because it happens after everything this process holds is released.
These tests pin the parts that make it safe: a stop request still stops, a shortage that
turns out to be disk or heat is not waited on, and a shortage that never ends still ends
the run.
"""
from __future__ import annotations

import ebook_reader.pipeline as pipeline_module
from ebook_reader.models import ResourceDecision, ResourceLevel


class _Resources:
    """Hands back a scripted sequence of measurements, one per poll."""

    def __init__(self, readings: list[tuple[float, bool, bool]]) -> None:
        # (free_ram_gb, critical, ram_only)
        self.readings = readings
        self.taken = 0

    def _current(self) -> tuple[float, bool, bool]:
        """The reading the most recent snapshot returned.

        decide() and is_ram_only_critical() answer about the snapshot that was taken, the
        way the real manager does; only snapshot() advances the script.
        """
        index = min(max(0, self.taken - 1), len(self.readings) - 1)
        return self.readings[index]

    def snapshot(self, force: bool = False):
        index = min(self.taken, len(self.readings) - 1)
        self.taken += 1

        class _Snapshot:
            free_ram_gb = self.readings[index][0]

        return _Snapshot()

    def decide(self, _snapshot) -> ResourceDecision:
        _ram, critical, _ram_only = self._current()
        return ResourceDecision(
            level=ResourceLevel.CRITICAL_STOP if critical else ResourceLevel.MAXIMUM,
            reason="test",
            critical=critical,
        )

    def is_ram_only_critical(self, _snapshot) -> bool:
        return self._current()[2]


class _Notifier:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def notify(self, title: str, body: str, **_kwargs) -> None:
        self.sent.append((title, body))


class _Paths:
    root = "."


def _pipeline(monkeypatch, readings, *, stop_after: int | None = None):
    """A pipeline object with only the parts _wait_for_foreign_ram touches."""
    monkeypatch.setattr(pipeline_module.time, "sleep", lambda _seconds: None)
    obj = object.__new__(pipeline_module.BookPipeline)
    obj.resources = _Resources(readings)
    obj.notifier = _Notifier()
    obj.paths = _Paths()
    obj.settings = {
        "resources": {"critical_free_ram_gb": 1.5},
        "safety": {"notify_on_critical_stop": True},
    }
    obj.log = lambda _message: obj.logged.append(_message)
    obj.logged = []
    obj.emit = lambda _kind, _payload: None
    calls = {"waits": 0}

    def _wait_pause_or_stop() -> None:
        calls["waits"] += 1
        if stop_after is not None and calls["waits"] > stop_after:
            raise KeyboardInterrupt("stop requested")

    obj._wait_pause_or_stop = _wait_pause_or_stop
    return obj, calls


def _critical(free_ram_gb: float):
    return (free_ram_gb, True, True)


def _recovered(free_ram_gb: float):
    return (free_ram_gb, False, False)


def test_a_run_resumes_by_itself_when_the_memory_comes_back(monkeypatch) -> None:
    pipeline = _pipeline(monkeypatch, [_critical(1.1), _critical(1.2), _recovered(6.0)])[0]

    snapshot, decision = pipeline._wait_for_foreign_ram(
        pipeline.resources.snapshot(), pipeline.resources.decide(None), "chapter 3"
    )

    assert decision.critical is False
    assert snapshot.free_ram_gb == 6.0
    assert any("hồi phục" in line for line in pipeline.logged)


def test_the_user_is_told_once_why_nothing_is_happening(monkeypatch) -> None:
    """Idling silently for half an hour looks identical to being hung."""
    pipeline = _pipeline(monkeypatch, [_critical(1.1)] * 3 + [_recovered(6.0)])[0]

    pipeline._wait_for_foreign_ram(
        pipeline.resources.snapshot(), pipeline.resources.decide(None), "chapter 3"
    )

    assert len(pipeline.notifier.sent) == 1, "one notification, not one per poll"
    assert "chờ RAM" in pipeline.notifier.sent[0][0]


def test_waiting_still_answers_a_stop_request(monkeypatch) -> None:
    """A plain sleep would outlive the user's patience; every poll asks first."""
    pipeline, calls = _pipeline(monkeypatch, [_critical(1.1)], stop_after=2)

    try:
        pipeline._wait_for_foreign_ram(
            pipeline.resources.snapshot(), pipeline.resources.decide(None), "chapter 3"
        )
    except KeyboardInterrupt:
        pass
    else:  # pragma: no cover - the stop must propagate
        raise AssertionError("a stop request was swallowed")

    assert calls["waits"] == 3


def test_a_shortage_of_disk_or_cooling_is_not_waited_on(monkeypatch) -> None:
    """Waiting for memory does not make a full disk emptier or a hot card cooler."""
    pipeline = _pipeline(monkeypatch, [_critical(1.1), (1.1, True, False)])[0]

    _snapshot, decision = pipeline._wait_for_foreign_ram(
        pipeline.resources.snapshot(), pipeline.resources.decide(None), "chapter 3"
    )

    assert decision.critical is True


def test_memory_that_never_comes_back_still_stops_the_run(monkeypatch) -> None:
    """The timeout is what keeps this a wait rather than a hang."""
    monkeypatch.setattr(pipeline_module, "CRITICAL_RAM_WAIT_TIMEOUT_SECONDS", 0.0)
    pipeline = _pipeline(monkeypatch, [_critical(1.1)])[0]

    _snapshot, decision = pipeline._wait_for_foreign_ram(
        pipeline.resources.snapshot(), pipeline.resources.decide(None), "chapter 3"
    )

    assert decision.critical is True
