"""Ollama's own counters, kept instead of dropped.

Every /api/generate response has always ended with a chunk carrying how many tokens the
prompt was, how many were generated, and how long each half took. The project read
``eval_count`` from it and threw the rest away, so the size of an analysis prompt was a
guess - and with it every decision that depends on the size: whether ``num_ctx`` of 16384
is twice what the work needs, whether five segments is the right batch, whether the model
spilling part of itself onto the CPU is worth freeing VRAM for.
"""
from ebook_reader.analysis import _ollama_usage, _ollama_usage_line


DONE_CHUNK = {
    "done": True,
    "done_reason": "stop",
    "prompt_eval_count": 3072,
    "prompt_eval_duration": 6_000_000_000,
    "eval_count": 512,
    "eval_duration": 32_000_000_000,
    "load_duration": 1_500_000_000,
    "total_duration": 39_500_000_000,
}


def test_every_counter_ollama_sends_is_kept() -> None:
    assert _ollama_usage(DONE_CHUNK) == {
        "prompt_eval_count": 3072,
        "prompt_eval_duration": 6_000_000_000,
        "eval_count": 512,
        "eval_duration": 32_000_000_000,
        "load_duration": 1_500_000_000,
        "total_duration": 39_500_000_000,
    }


def test_a_chunk_without_counters_reports_nothing_rather_than_zeroes() -> None:
    """A zero here would read as "the prompt was empty", which is a different claim."""
    assert _ollama_usage({"done": True}) is None
    assert _ollama_usage({"done": True, "eval_count": None}) is None


def test_a_counter_that_arrives_alone_is_still_worth_keeping() -> None:
    assert _ollama_usage({"done": True, "eval_count": 40}) == {"eval_count": 40}


def test_the_line_says_how_much_of_the_context_the_prompt_used() -> None:
    """The number the whole exercise is for: 3072 of 16384 means 13312 tokens of KV cache
    were reserved in VRAM and never written to."""
    line = _ollama_usage_line(DONE_CHUNK, 16384)
    assert "prompt 3,072 tok/16,384 ctx (19%)" in line
    assert "sinh 512 tok" in line


def test_the_line_separates_reading_the_prompt_from_writing_the_answer() -> None:
    """Two rates, because they are two different bottlenecks: prompt evaluation is compute
    bound and generation is memory bound, and only the second one cares about the CPU spill.
    """
    line = _ollama_usage_line(DONE_CHUNK, 16384)
    assert "nạp prompt 512.0 tok/s" in line
    assert "sinh 16.0 tok/s" in line


def test_model_load_time_is_named_so_it_is_not_counted_as_slow_generation() -> None:
    line = _ollama_usage_line(DONE_CHUNK, 16384)
    assert "nạp model 1.5s" in line
    assert "tổng 39.5s" in line


def test_a_duration_of_zero_does_not_divide_by_it() -> None:
    line = _ollama_usage_line(
        {"prompt_eval_count": 10, "prompt_eval_duration": 0, "eval_count": 0}, 0
    )
    assert "tok/s" not in line
    assert "ctx" not in line
    assert "prompt 10 tok" in line
