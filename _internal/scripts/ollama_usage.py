"""What the analysis phase actually asked Ollama for, read back out of a run's log.

Every /api/generate response ends with a chunk carrying how big the prompt was, how many
tokens came back, and how long each half took. Those counters are written to the log one
line per request (see _ollama_usage_line in analysis.py). This reads them back and answers
the questions that decide how the analysis phase performs:

  - How big does a prompt actually get? num_ctx reserves KV cache in VRAM whether the
    prompt fills it or not, and on this machine qwen3:8b does not fit, so it runs part of
    itself on the CPU. Reserving context nobody uses is paid for in generation speed.
  - Which half is slow? Prompt evaluation is compute bound and generation is memory
    bandwidth bound. Only the second one suffers from the CPU spill, and if generation
    dominates then freeing VRAM is the lever.

The maximum matters more than the mean: a prompt that exceeds num_ctx is truncated by
Ollama in silence, and a truncated analysis batch still returns valid JSON.

    python scripts/ollama_usage.py <project_root_or_log>
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

USAGE_PATTERN = re.compile(
    r"Ollama: prompt ([\d,]+) tok(?:/([\d,]+) ctx \(\d+%\))?"
    r" \| sinh ([\d,]+) tok"
    r"(?: \| nạp prompt ([\d,.]+) tok/s)?"
    r"(?: \| sinh ([\d,.]+) tok/s)?"
    r"(?: \| nạp model ([\d.]+)s)?"
    r"(?: \| tổng ([\d.]+)s)?"
)


def _number(text: str | None) -> float:
    return float(text.replace(",", "")) if text else 0.0


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))
    return ordered[index]


def main(argument: str) -> int:
    target = Path(argument)
    log = target if target.is_file() else target / "logs" / "ebook_reader.log"
    if not log.is_file():
        print(f"không tìm thấy log: {log}")
        return 2

    prompts: list[float] = []
    outputs: list[float] = []
    prompt_rates: list[float] = []
    output_rates: list[float] = []
    totals: list[float] = []
    load_seconds = 0.0
    context = 0

    with log.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            match = USAGE_PATTERN.search(line)
            if match is None:
                continue
            prompts.append(_number(match.group(1)))
            context = int(_number(match.group(2))) or context
            outputs.append(_number(match.group(3)))
            if match.group(4):
                prompt_rates.append(_number(match.group(4)))
            if match.group(5):
                output_rates.append(_number(match.group(5)))
            load_seconds += _number(match.group(6))
            totals.append(_number(match.group(7)))

    if not prompts:
        print(
            "log chưa có dòng đếm nào. Cần code từ commit 18295d5 trở đi; "
            "lần chạy cũ hơn không ghi lại các bộ đếm này."
        )
        return 1

    largest = max(prompts)
    largest_pair = max(p + o for p, o in zip(prompts, outputs))
    print(f"{len(prompts):,} yêu cầu, num_ctx = {context:,}")
    print()
    print(f"  prompt   : lớn nhất {largest:,.0f} | p95 {_percentile(prompts, 0.95):,.0f} "
          f"| trung bình {sum(prompts) / len(prompts):,.0f} tok")
    print(f"  sinh ra  : lớn nhất {max(outputs):,.0f} | trung bình "
          f"{sum(outputs) / len(outputs):,.0f} tok")
    print(f"  prompt+sinh lớn nhất: {largest_pair:,.0f} tok")
    if context:
        print(f"  dùng nhiều nhất {largest_pair / context:.1%} của ngữ cảnh đã đặt chỗ")
    print()
    if prompt_rates:
        print(f"  nạp prompt: {sum(prompt_rates) / len(prompt_rates):,.0f} tok/s trung bình")
    if output_rates:
        print(f"  sinh token: {sum(output_rates) / len(output_rates):,.1f} tok/s trung bình "
              f"(thấp nhất {min(output_rates):,.1f})")
    total_seconds = sum(totals)
    if total_seconds:
        generation = sum(o / r for o, r in zip(outputs, output_rates) if r) if output_rates else 0.0
        print()
        print(f"  tổng thời gian Ollama: {total_seconds:,.0f}s")
        if generation:
            print(f"    trong đó sinh token: {generation:,.0f}s ({generation / total_seconds:.0%})")
        if load_seconds:
            print(f"    nạp model         : {load_seconds:,.0f}s ({load_seconds / total_seconds:.0%})")

    if context and largest_pair * 2 < context:
        # The KV cache of qwen3:8b is about 36 * 2 * 8 * 128 * num_ctx * 2 bytes.
        per_token_bytes = 36 * 2 * 8 * 128 * 2
        for candidate in (4096, 8192):
            if candidate <= context and largest_pair < candidate * 0.8:
                freed = (context - candidate) * per_token_bytes / 1e9
                print()
                print(
                    f"  num_ctx {candidate:,} vẫn thừa chỗ cho yêu cầu lớn nhất "
                    f"({largest_pair:,.0f} tok) và trả lại ~{freed:.2f} GB VRAM."
                )
                break
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
