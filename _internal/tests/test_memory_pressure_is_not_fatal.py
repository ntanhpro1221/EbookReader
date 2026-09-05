"""Another program taking the memory must not kill a book that has been running for hours.

The owner reported it plainly: opening Unity, Rider or Photoshop mid-run made the book start
failing "for no reason", and asked why a resource shortage was not simply retried within
whatever headroom remained.

It was not without reason. VieNeu raised an out-of-memory error, "out of memory" sat in
FATAL_TTS_MARKERS beside "no module named", and the pipeline raised "Fatal TTS engine
failure" - ending the run. A missing module will still be missing after waiting; memory
somebody else is holding will not. The pipeline already knew that, in _wait_for_foreign_ram,
but an OOM raised inside the engine never reached it.
"""
from __future__ import annotations

import pytest

from ebook_reader.tts import is_fatal_tts_error, is_transient_tts_memory_error

TRANSIENT = (
    "CUDA out of memory. Tried to allocate 2.00 GiB",
    "DefaultCPUAllocator: not enough memory: you tried to allocate 8589934592 bytes",
    "RuntimeError: [enforce fail at alloc_cpu.cpp:117]",
    "CUDA_ERROR_OUT_OF_MEMORY",
)
FATAL = (
    "No module named 'vieneu'",
    "CUDA driver version is insufficient for CUDA runtime version",
    "cuBLAS error: CUBLAS_STATUS_NOT_INITIALIZED",
    "Thiếu VieNeu preset",
    "locked VieNeu preset missing",
    "only VieNeu profiles are supported",
)


@pytest.mark.parametrize("message", TRANSIENT)
def test_memory_pressure_is_transient_not_fatal(message: str) -> None:
    error = RuntimeError(message)
    assert is_transient_tts_memory_error(error)
    assert not is_fatal_tts_error(error), "this used to end the run"


@pytest.mark.parametrize("message", FATAL)
def test_a_broken_environment_is_still_fatal(message: str) -> None:
    """Waiting does not install a module or fix a driver, so these must not be retried."""
    error = RuntimeError(message)
    assert is_fatal_tts_error(error)
    assert not is_transient_tts_memory_error(error)


def test_the_two_classes_never_overlap() -> None:
    """A message matching both must be treated as fatal - retrying a broken engine forever
    is worse than stopping, and the transient check defers to the fatal one for that reason."""
    error = RuntimeError("cuBLAS error: out of memory")
    assert is_fatal_tts_error(error)
    assert not is_transient_tts_memory_error(error)


def test_an_ordinary_failure_is_neither() -> None:
    error = ValueError("speech pace 11.05 chars/s")
    assert not is_fatal_tts_error(error)
    assert not is_transient_tts_memory_error(error)
