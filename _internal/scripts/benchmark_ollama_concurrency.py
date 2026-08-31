"""Measure whether this GPU serves concurrent analysis requests faster than one at a time.

Analysis dominates the wall clock - a 20-chapter run spent hours in `analysis` while
`chapter_synthesis` is comparatively cheap - and the server it talks to runs with
`OLLAMA_NUM_PARALLEL:1`, which serialises every request no matter how many the pipeline
sends. Raising it is therefore the largest single throughput lever in the project, and
also the least obvious: qwen3:8b already holds 6.09 of this card's 8.0 GiB, and each extra
slot costs another KV cache. Whether a second slot even fits, let alone helps, is a
question about this machine that arithmetic cannot answer.

This script restarts Ollama at each requested parallelism, replays the same prompts, and
reports aggregate throughput plus peak VRAM. It deliberately drives the *real* model at
the *real* context length, because a smaller probe would fit where the real one does not.

It restarts the Ollama server, so no project run may be in progress. Writes nothing into
any project.

Usage:
    python scripts/benchmark_ollama_concurrency.py --out <scratch-dir>
        [--parallel 1,2,3] [--concurrency 4] [--requests 8]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE_URL = "http://127.0.0.1:11434"
MODEL = "qwen3:8b"
NUM_CTX = 16384

# A prompt shaped like the real analysis call: a system rule plus a handful of Vietnamese
# narrative segments to label. Length matters - a short prompt would understate the KV
# cache each concurrent slot actually needs.
SEGMENTS = (
    "Hạ Phong đột ngột bật dậy thở dốc, "
    "mồ hôi ướt đẫm cả lưng áo.",
    "‘Tỉnh dậy, phải tỉnh dậy!’",
    "Cậu nhớ lại giấc mơ hỏa hoạn, khói dày "
    "đặc phủ kín cả căn phòng nhỏ.",
    "«Cậu không sao chứ?» - người bên cạnh "
    "khẽ hỏi, giọng đầy lo lắng.",
    "Ngoài cửa sổ, trời đã sáng từ lúc "
    "nào, tiếng chim hót vang khắp khu vườn.",
)
PROMPT = (
    "Bạn là đạo diễn audiobook tiếng Việt. Với "
    "mỗi đoạn dưới đây, trả về JSON gồm "
    "id, kind (narration/dialogue/thought), speaker, emotion, intensity, pace, volume. "
    "Chỉ trả JSON, không thêm văn bản nào khác.\n\n"
    + "\n".join(f"{index}. {text}" for index, text in enumerate(SEGMENTS, 1))
)


def _vram_used_mib() -> float:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if result.returncode != 0:
            return 0.0
        return float(result.stdout.strip().splitlines()[0])
    except Exception:  # noqa: BLE001
        return 0.0


def _server_up() -> bool:
    try:
        return requests.get(f"{BASE_URL}/api/tags", timeout=5).status_code == 200
    except requests.RequestException:
        return False


def _stop_server() -> None:
    if os.name == "nt":
        for image in ("ollama.exe", "ollama app.exe"):
            subprocess.run(
                ["taskkill", "/F", "/IM", image, "/T"], capture_output=True, check=False
            )
    else:
        subprocess.run(["pkill", "-f", "ollama"], capture_output=True, check=False)
    for _ in range(30):
        if not _server_up():
            return
        time.sleep(1)
    raise RuntimeError("Ollama did not stop")


def _start_server(parallel: int, log_path: Path) -> subprocess.Popen[bytes]:
    executable = shutil.which("ollama")
    if not executable:
        raise RuntimeError("ollama is not on PATH")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, "OLLAMA_NUM_PARALLEL": str(parallel)}
    handle = log_path.open("ab", buffering=0)
    process = subprocess.Popen(
        [executable, "serve"],
        stdout=handle,
        stderr=subprocess.STDOUT,
        env=environment,
        creationflags=(
            getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        ),
    )
    for _ in range(60):
        if _server_up():
            return process
        time.sleep(1)
    raise RuntimeError(f"Ollama did not come up with OLLAMA_NUM_PARALLEL={parallel}")


def _one_request(index: int) -> dict[str, Any]:
    started = time.monotonic()
    response = requests.post(
        f"{BASE_URL}/api/generate",
        json={
            "model": MODEL,
            "prompt": PROMPT,
            "stream": False,
            "think": False,
            "options": {"num_ctx": NUM_CTX, "temperature": 0.0, "seed": 42 + index},
        },
        timeout=900,
    )
    response.raise_for_status()
    body = response.json()
    return {
        "seconds": time.monotonic() - started,
        "eval_count": int(body.get("eval_count", 0)),
        "prompt_eval_count": int(body.get("prompt_eval_count", 0)),
    }


def _measure(concurrency: int, requests_total: int) -> dict[str, Any]:
    # Warm the weights so the first timed request does not pay for the model load.
    _one_request(0)
    peak_vram = _vram_used_mib()
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(_one_request, range(requests_total)))
    elapsed = time.monotonic() - started
    peak_vram = max(peak_vram, _vram_used_mib())
    generated = sum(item["eval_count"] for item in results)
    return {
        "concurrency": concurrency,
        "requests": requests_total,
        "seconds": round(elapsed, 2),
        "generated_tokens": generated,
        "tokens_per_second": round(generated / elapsed, 2) if elapsed else 0.0,
        "requests_per_minute": (
            round(requests_total / elapsed * 60.0, 2) if elapsed else 0.0
        ),
        "peak_vram_mib": round(peak_vram),
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--parallel", default="1,2,3")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=0,
        help="concurrent requests; defaults to the parallelism under test",
    )
    parser.add_argument("--requests", type=int, default=8)
    parser.add_argument("--json", dest="json_out", type=Path, default=None)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    reports: list[dict[str, Any]] = []
    print(f"model={MODEL}  num_ctx={NUM_CTX}  requests={args.requests}\n", flush=True)
    baseline_rate = 0.0
    for parallel in [int(part) for part in args.parallel.split(",") if part.strip()]:
        _stop_server()
        process = _start_server(parallel, args.out / f"ollama_p{parallel}.log")
        try:
            concurrency = args.concurrency or parallel
            report: dict[str, Any] = {
                "num_parallel": parallel,
                **_measure(concurrency, args.requests),
            }
        except Exception as exc:  # noqa: BLE001
            report = {"num_parallel": parallel, "error": repr(exc)}
        finally:
            process.terminate()
            _stop_server()
        reports.append(report)
        if "error" in report:
            print(
                f"  NUM_PARALLEL={parallel:2d}  FAILED  {str(report['error'])[:90]}",
                flush=True,
            )
            continue
        rate = float(report["tokens_per_second"])
        baseline_rate = baseline_rate or rate
        print(
            f"  NUM_PARALLEL={parallel:2d}  conc={report['concurrency']:2d}  "
            f"{report['seconds']:7.1f}s  {rate:7.1f} tok/s  "
            f"speedup {rate / baseline_rate:4.2f}x  "
            f"peak VRAM {report['peak_vram_mib']:5d} MiB",
            flush=True,
        )

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nJSON written to {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
