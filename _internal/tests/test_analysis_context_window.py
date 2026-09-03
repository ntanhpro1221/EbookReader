"""The context window is sized by the work, and a prompt that overruns it says so.

num_ctx was one constant, 16384, for every profile. It is right for the default profile -
28 segments a batch, an output budget of 5,888 tokens on its own - but high_quality
overrides the batch down to 5 and inherited the number anyway, reserving about 2.4 GB of
KV cache to carry prompts measured at a fifth of it. On a card that cannot already hold
the model, context nobody uses is paid for in the slowest half of the work.

Sizing it down is only safe with the second half of this: Ollama truncates an oversized
prompt in silence, and a truncated analysis batch still returns valid JSON.
"""
from __future__ import annotations

import pytest

from ebook_reader.analysis import AnalysisPromptTruncatedError, _check_prompt_fits
from ebook_reader.config import analysis_context_window, build_settings


def test_a_smaller_batch_asks_for_a_smaller_window() -> None:
    high_quality = build_settings("high_quality")["analysis"]
    balanced = build_settings("balanced")["analysis"]

    assert high_quality["batch_segments"] < balanced["batch_segments"]
    assert high_quality["num_ctx"] < balanced["num_ctx"]
    assert high_quality["num_ctx"] < 16384, "the profile actually in use paid the most"


def test_the_output_budget_is_never_halved_by_the_window_that_carries_it() -> None:
    """The trap that makes this more than arithmetic.

    The budget is min(512 + segments * 192, num_ctx // 2, 6144). A window merely larger
    than the requested output still lets the // 2 term cut it, and an analysis batch whose
    answer is cut off mid-JSON fails a whole chapter. So the window is at least twice the
    request, not merely bigger than it.
    """
    for segments in (1, 5, 12, 28, 40, 100):
        window = analysis_context_window({"batch_segments": segments, "batch_chars": 6200})
        requested = min(512 + segments * 192, 6144)
        assert window // 2 >= requested, segments


def test_the_window_leaves_room_for_the_prompt_as_well_as_the_answer() -> None:
    window = analysis_context_window({"batch_segments": 5, "batch_chars": 6200})
    # Every character the batch is allowed to carry, at a generous two per token, plus the
    # fixed instruction block and the schema.
    assert window >= 6200 / 2 + min(512 + 5 * 192, 6144)


def test_more_text_per_batch_needs_more_room() -> None:
    small = analysis_context_window({"batch_segments": 5, "batch_chars": 2000})
    large = analysis_context_window({"batch_segments": 5, "batch_chars": 20000})
    assert large > small


def test_a_caller_who_names_a_number_keeps_it() -> None:
    """Deriving a default is help; overriding a deliberate choice is not."""
    settings = build_settings("high_quality", overrides={"analysis": {"num_ctx": 32768}})
    assert settings["analysis"]["num_ctx"] == 32768


def test_a_prompt_cut_to_fit_raises_instead_of_being_analysed() -> None:
    """Ollama reports the truncated count, so a prompt at exactly the room available is a
    prompt that was cut. Nothing downstream can tell: the answer is valid JSON about the
    segments that survived."""
    with pytest.raises(AnalysisPromptTruncatedError, match="cắt bớt"):
        _check_prompt_fits({"prompt_eval_count": 6720}, num_ctx=8192, num_predict=1472)


def test_a_prompt_that_fits_passes_silently() -> None:
    _check_prompt_fits({"prompt_eval_count": 2481}, num_ctx=8192, num_predict=1472)


def test_a_response_without_counters_cannot_accuse_anyone() -> None:
    """An older Ollama that sends no counters is not evidence of truncation."""
    _check_prompt_fits({}, num_ctx=8192, num_predict=1472)
    _check_prompt_fits({"prompt_eval_count": 0}, num_ctx=8192, num_predict=1472)
    _check_prompt_fits({"prompt_eval_count": 9000}, num_ctx=0, num_predict=0)


def test_an_oversized_prompt_is_treated_as_a_batch_to_split() -> None:
    """The recovery already existed; the new error just has to reach it.

    A batch that is too big for the context is the same shape of problem as one that runs
    past its output budget or its wall clock, and the pipeline answers all of those by
    halving the batch and trying again. Halving it halves the segment text, which is the
    only part of the prompt that grows - so the split is the actual remedy rather than a
    generic retry. Left in the catch-all branch, this error would have re-sent the
    identical batch until the attempts ran out and then failed the chapter.
    """
    import inspect

    from ebook_reader import analysis

    source = inspect.getsource(analysis.OllamaBookAnalyzer)
    handler = source[source.index("AnalysisOutputBudgetError,\n") :]
    clause = handler[: handler.index(") as exc:")]
    assert "AnalysisPromptTruncatedError" in clause, (
        "an oversized prompt must reach the splitting handler, not the catch-all"
    )
