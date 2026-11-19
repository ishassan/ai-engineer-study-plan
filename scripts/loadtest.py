"""Reference solution.

Send requests at the same time to one model of the gateway, and measure its speed. Week 22.

    make loadtest ROUTE=qwen3-8b ARGS="--gpu A40 --gpu-price 0.59 --gpu-memory-gib <GiB>"
    make loadtest ROUTE=qwen3-8b ARGS="--loads 1,8"          only two loads

For each load (1, 8 and 32 requests at the same time by default), the script sends
`--requests-per-slot` times the load requests, and never more than the load at the same time.
The questions are the questions of evals/testset.jsonl, in turn. Each request goes to the
gateway (GATEWAY_URL, GATEWAY_KEY) in the format of the Messages API, as the assistant sends
them, without tools.

The result file is evals/results/load/<model>.json:

    model, gpu, gpu_price_per_hour, gpu_memory_gib, max_tokens, created_at,
    loads: [{concurrency, requests, ok, errors, seconds, output_tokens, tokens_per_second,
             requests_per_hour, latency_ms_p50, latency_ms_p95}]

`seconds` is the wall-clock time of the whole load. `tokens_per_second` is the output tokens of
all requests that succeeded, divided by `seconds`. `requests_per_hour` is the number of requests
that succeeded, divided by `seconds`, times 3600. The GPU, its price and its memory come from the
flags: read the memory in the log of vLLM or with nvidia-smi on the pod.

Your part: one_request() and run_load().
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anthropic

ROOT = Path(__file__).resolve().parent.parent
TESTSET = ROOT / "evals" / "testset.jsonl"
RESULTS = ROOT / "evals" / "results" / "load"
SYSTEM = "You are the assistant of a data platform. Answer the question in two or three sentences."


def load_questions(path: Path = TESTSET) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line)["question"] for line in lines if line.strip()]


def percentile(values: list[float], fraction: float) -> float:
    """The value below which `fraction` of the values lie (nearest rank). 0.0 for no values."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[rank - 1]


def gateway_client() -> anthropic.AsyncAnthropic:
    url, key = os.environ.get("GATEWAY_URL", ""), os.environ.get("GATEWAY_KEY", "")
    if not url:
        raise SystemExit("GATEWAY_URL is empty. Set it in .env (Phase 6, week 21).")
    return anthropic.AsyncAnthropic(base_url=url, api_key=key, max_retries=0, timeout=120)


async def one_request(client: anthropic.AsyncAnthropic, model: str, question: str, max_tokens: int) -> dict[str, Any]:
    """Reference solution."""
    started = time.perf_counter()
    try:
        message = await client.messages.create(
            model=model, max_tokens=max_tokens, system=SYSTEM, messages=[{"role": "user", "content": question}]
        )
    except anthropic.APIError as error:
        latency = (time.perf_counter() - started) * 1000
        return {"ok": False, "latency_ms": latency, "output_tokens": 0, "error": f"{type(error).__name__}: {error}"}
    latency = (time.perf_counter() - started) * 1000
    return {"ok": True, "latency_ms": latency, "output_tokens": message.usage.output_tokens}


async def run_load(
    client: anthropic.AsyncAnthropic, model: str, questions: list[str], concurrency: int, total: int, max_tokens: int
) -> dict[str, Any]:
    """Reference solution."""
    slots = asyncio.Semaphore(concurrency)

    async def limited(index: int) -> dict[str, Any]:
        async with slots:
            return await one_request(client, model, questions[index % len(questions)], max_tokens)

    started = time.perf_counter()
    results = await asyncio.gather(*(limited(index) for index in range(total)))
    seconds = time.perf_counter() - started
    ok = [result for result in results if result["ok"]]
    latencies = [result["latency_ms"] for result in ok]
    output_tokens = sum(result["output_tokens"] for result in ok)
    return {
        "concurrency": concurrency,
        "requests": total,
        "ok": len(ok),
        "errors": total - len(ok),
        "seconds": round(seconds, 3),
        "output_tokens": output_tokens,
        "tokens_per_second": output_tokens / seconds,
        "requests_per_hour": len(ok) / seconds * 3600,
        "latency_ms_p50": percentile(latencies, 0.5),
        "latency_ms_p95": percentile(latencies, 0.95),
    }


async def run(args: argparse.Namespace) -> dict[str, Any]:
    client = gateway_client()
    questions = load_questions()
    loads = []
    for concurrency in args.loads:
        result = await run_load(client, args.model, questions, concurrency, concurrency * args.requests_per_slot,
                                args.max_tokens)
        loads.append(result)
        print(
            f"load {concurrency:3}: {result['ok']}/{result['requests']} ok, {result['tokens_per_second']:.1f} tokens/s, "
            f"p50 {result['latency_ms_p50']:.0f} ms, p95 {result['latency_ms_p95']:.0f} ms"
        )
    return {
        "model": args.model,
        "gpu": args.gpu,
        "gpu_price_per_hour": args.gpu_price,
        "gpu_memory_gib": args.gpu_memory_gib,
        "max_tokens": args.max_tokens,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "loads": loads,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True, help="The name of the route in the gateway, for example qwen3-8b.")
    parser.add_argument("--loads", default="1,8,32", type=lambda text: [int(n) for n in text.split(",")])
    parser.add_argument("--requests-per-slot", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--gpu", default=None, help="The GPU of the pod, for example A40.")
    parser.add_argument("--gpu-price", type=float, default=None, help="The price of the pod in US dollars an hour.")
    parser.add_argument("--gpu-memory-gib", type=float, default=None, help="The GPU memory that vLLM uses, in GiB.")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    out = args.out or RESULTS / f"{args.model}.json"
    started = time.perf_counter()
    result = asyncio.run(run(args))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(f"results in {out} ({time.perf_counter() - started:.0f} s)")


if __name__ == "__main__":
    main()
