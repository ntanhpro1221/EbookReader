"""Would serving analysis batches concurrently make the biggest phase cheaper?

Analysis is now the largest phase of a run - 4,490s against ASR's 3,870s - and analysis.py
drives it as a plain sequential loop: 424 requests, one at a time, each waiting for the last.
Ollama serves one at a time to match.

Generation is memory-bandwidth bound. Two requests decoded together read the model weights
once and produce two tokens for that read, so aggregate throughput should rise well short of
doubling the cost. That is the standard reason batched LLM serving wins, and it is the
largest untouched lever left in a run.

It is not free. Each concurrent slot needs its own KV cache - about 1.06 GB at num_ctx
7,168 for qwen3:8b - on a card that already holds the model. Buying throughput by spilling
a layer to CPU would lose more than it gains, which is exactly what the previous measurement
caught num_ctx doing. So this reports VRAM alongside the speed.

DO NOT RUN THIS DURING A RUN. It loads the analysis model, and a book in its synthesis phase
has already sized its TTS pool against the VRAM that is free right now.

The server has to allow it: OLLAMA_NUM_PARALLEL caps how many requests Ollama decodes
together, and below the concurrency asked for here the extra requests simply queue - which
looks like "concurrency does not help" rather than "the server refused". The script reads
the setting back and says so.

    python scripts/measure_ollama_parallel.py [model] [max_concurrency]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
DEFAULT_MODEL = "qwen3:8b"
DEFAULT_MAX = 4
# The shape a real analysis request has, taken from alpha.43's logged usage lines: prompts
# ran 1,768-4,358 tokens and generation 156-710. A synthetic prompt of the wrong size would
# measure a different problem.
PROMPT_TOKENS = 2600
OUTPUT_TOKENS = 400
NUM_CTX = 7168


def _post(path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{HOST}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.loads(response.read().decode("utf-8"))


def _vram_used_mb() -> float:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15, check=True,
        )
        return float(out.stdout.strip().splitlines()[0])
    except Exception:  # noqa: BLE001
        return 0.0


def _one_request(model: str, index: int, results: list, position: int) -> None:
    # Distinct text per slot: an identical prompt could be served from a cache and would
    # measure the cache rather than the decode.
    filler = "Nhan vat buoc qua canh cong da va nhin thay bau troi doi mau. "
    prompt = (
        f"Yeu cau {index}. Doc doan van sau va viet lai that dai bang tieng Viet.\n\n"
        + filler * (PROMPT_TOKENS // 12)
    )
    started = time.perf_counter()
    try:
        body = _post(
            "/api/generate",
            {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_ctx": NUM_CTX,
                    "num_predict": OUTPUT_TOKENS,
                    "temperature": 0.0,
                },
            },
        )
    except (urllib.error.URLError, TimeoutError) as error:
        results[position] = ("error", str(error), 0.0)
        return
    results[position] = ("ok", int(body.get("eval_count") or 0), time.perf_counter() - started)


def main(model: str, max_concurrency: int) -> int:
    try:
        _post("/api/show", {"model": model})
    except Exception as error:  # noqa: BLE001
        print(f"khong goi duoc Ollama tai {HOST}: {error}")
        print("Chay 'ollama serve' roi thu lai. Dung chay khi dang co mot lan chay sach.")
        return 2

    parallel = os.environ.get("OLLAMA_NUM_PARALLEL", "(khong dat - Ollama tu chon)")
    print(f"model {model} tai {HOST}, num_ctx {NUM_CTX}, OLLAMA_NUM_PARALLEL={parallel}")
    print(
        "Neu server chi cho 1 request cung luc thi cac request thua xep hang, va bang duoi "
        "se trong y nhu 'song song khong giup gi'."
    )

    idle_vram = _vram_used_mb()
    baseline = 0.0
    print()
    print(f"{'song song':>9}  {'tong':>8}  {'token':>7}  {'tok/s gop':>10}  {'nhanh hon':>10}  {'VRAM':>9}")
    for concurrency in range(1, max_concurrency + 1):
        results: list = [None] * concurrency
        threads = [
            threading.Thread(target=_one_request, args=(model, index, results, index))
            for index in range(concurrency)
        ]
        started = time.perf_counter()
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        elapsed = time.perf_counter() - started
        peak_vram = _vram_used_mb()

        failed = [item for item in results if item and item[0] == "error"]
        if failed:
            print(f"{concurrency:9d}  loi: {str(failed[0][1])[:70]}")
            break
        tokens = sum(int(item[1]) for item in results if item)
        rate = tokens / elapsed if elapsed else 0.0
        if concurrency == 1:
            baseline = rate
        print(
            f"{concurrency:9d}  {elapsed:7.1f}s  {tokens:7d}  {rate:10.1f}"
            f"  {rate / baseline if baseline else 0:9.2f}x  {peak_vram - idle_vram:7.0f}MiB"
        )

    print()
    print(
        "Dang xay khi tok/s gop tang ro VA VRAM them van con cho cho pool TTS. Moi cho song "
        "song can mot KV cache rieng, va mua thong luong bang cach day mot lop xuong CPU thi "
        "lo - dung cai bay num_ctx 9216 da sap vao."
    )
    return 0


if __name__ == "__main__":
    if len(sys.argv) - 1 > 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(
        main(
            sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL,
            int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_MAX,
        )
    )
