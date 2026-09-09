"""A momentary VRAM shortage must not disable the synthesis pool for the whole run.

_synthesis_pool sizes itself from free VRAM and refuses to build below two workers. That
refusal used to set _tts_pool_failed, the same latch the exception path uses - so a single
low reading turned the pool off for every chapter that followed.

alpha.44 did exactly that. The pool ran for chapter 2, then a sample taken at the chapter
boundary read 4,467 MiB - enough for one worker, not two - and chapters 3 through 10 were
synthesized serially. Main-path TTS went from 2,233s in alpha.43 to 4,270s, about 2,037
seconds, on a run whose analysis phase had just been made 742s faster.

Free VRAM at a chapter boundary is a reading of one instant, taken while the previous
chapter's models may still be releasing. The next chapter deserves to be asked again. An
exception while building the pool is different: that is a broken pool, and it stays latched.
"""
from __future__ import annotations

from types import SimpleNamespace

from ebook_reader.pipeline import BookPipeline


class _Recorder:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, message: str) -> None:
        self.lines.append(str(message))


def _pipeline(free_mb: int) -> BookPipeline:
    pipeline = object.__new__(BookPipeline)
    pipeline.settings = {"tts": {"parallel_workers": 3}}
    pipeline._tts_pool = None
    pipeline._tts_pool_failed = False
    pipeline.log = _Recorder()
    # `free_ram_gb` là trường thật của `ResourceSnapshot`, và từ khi pool cũng đếm RAM thì
    # thiếu nó ở đây làm `_synthesis_pool` ném AttributeError bên trong `try` — tức biến một
    # thiếu hụt nhất thời thành cái chốt vĩnh viễn mà chính file này cấm. Cho dư RAM, vì bài
    # test này nói về VRAM.
    pipeline.resources = SimpleNamespace(
        snapshot=lambda: SimpleNamespace(
            gpu_free_mb=free_mb, gpu_total_mb=8151, free_ram_gb=20.0
        )
    )
    # The exception path records a warning event before giving up.
    pipeline.db = SimpleNamespace(event=lambda *args, **kwargs: None, path="/tmp/x.sqlite3")
    return pipeline


def test_a_low_vram_reading_does_not_latch() -> None:
    """The chapter after it must still get a pool if the card has room by then."""
    pipeline = _pipeline(4467)  # alpha.44's actual reading
    assert pipeline._synthesis_pool() is None
    assert pipeline._tts_pool_failed is False, (
        "a shortage at one chapter boundary must not disable the pool for the rest of the run"
    )


def test_the_refusal_is_reported_per_chapter() -> None:
    pipeline = _pipeline(4467)
    pipeline._synthesis_pool()
    assert any("không đủ cho pool TTS" in line for line in pipeline.log.lines)


def test_a_pool_that_cannot_be_built_does_latch() -> None:
    """An exception is a broken pool, not a busy card, and retrying it every chapter is waste."""
    pipeline = _pipeline(8000)
    pipeline.resources = SimpleNamespace(snapshot=_raise)
    assert pipeline._synthesis_pool() is None
    assert pipeline._tts_pool_failed is True


def _raise():
    raise RuntimeError("no CUDA here")


def test_a_ram_shortage_does_not_latch_either() -> None:
    """Thiếu RAM cũng là đọc một khoảnh khắc, y như thiếu VRAM — không được chốt.

    Thêm cùng lúc với việc pool bắt đầu đếm RAM: nếu không có bài này thì đường mới sẽ là
    đường duy nhất trong hàm chưa ai kiểm xem nó có chốt hay không, và chốt là thứ đã tốn
    alpha.44 khoảng 2.037 giây.
    """
    pipeline = _pipeline(8000)
    pipeline.resources = SimpleNamespace(
        snapshot=lambda: SimpleNamespace(
            gpu_free_mb=8000, gpu_total_mb=8151, free_ram_gb=3.6
        )
    )

    assert pipeline._synthesis_pool() is None
    assert pipeline._tts_pool_failed is False
    assert any("RAM" in line for line in pipeline.log.lines)


def test_parallel_workers_below_two_still_returns_none() -> None:
    pipeline = _pipeline(8000)
    pipeline.settings = {"tts": {"parallel_workers": 1}}
    assert pipeline._synthesis_pool() is None
