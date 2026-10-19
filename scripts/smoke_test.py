# /// script
# requires-python = ">=3.11"
# dependencies = ["openai>=1.40"]
# ///
"""Smoke test for any OpenAI-compatible endpoint (vLLM now, the Forge gateway later).

It checks that the server answers, then measures the three numbers every
LLMOps engineer watches:

* TTFT  (time to first token): how long the user waits before text appears.
* TPOT  (time per output token): how fast text streams after that.
* Throughput (tokens/second) for this one request.

Run:  uv run scripts/smoke_test.py --base-url http://localhost:8000/v1
"""

from __future__ import annotations

import argparse
import sys
import time

from openai import OpenAI


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--base-url", default="http://localhost:8000/v1")
    # vLLM ignores the key unless it was started with --api-key.
    p.add_argument("--api-key", default="not-needed-yet")
    p.add_argument("--prompt", default="In two sentences, what is Kubernetes?")
    p.add_argument("--max-tokens", type=int, default=64)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    client = OpenAI(base_url=args.base_url, api_key=args.api_key, timeout=120)

    # 1. Which models does the server offer? (GET /v1/models)
    models = [m.id for m in client.models.list().data]
    if not models:
        print("FAIL: server returned no models")
        return 1
    model = models[0]
    print(f"models served: {models}")

    # 2. Stream a chat completion and time each chunk as it arrives.
    start = time.perf_counter()
    first_token_at: float | None = None
    chunks = 0
    text = []
    usage = None

    stream = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": args.prompt}],
        max_tokens=args.max_tokens,
        temperature=0,
        stream=True,
        stream_options={"include_usage": True},  # last chunk carries token counts
    )
    for chunk in stream:
        if chunk.usage:
            usage = chunk.usage
        if chunk.choices and chunk.choices[0].delta.content:
            if first_token_at is None:
                first_token_at = time.perf_counter()
            chunks += 1
            text.append(chunk.choices[0].delta.content)
    end = time.perf_counter()

    if first_token_at is None:
        print("FAIL: no tokens were streamed back")
        return 1

    output_tokens = usage.completion_tokens if usage else chunks
    ttft = first_token_at - start
    decode_time = end - first_token_at
    tpot = decode_time / max(output_tokens - 1, 1)

    print(f"\nanswer: {''.join(text).strip()}\n")
    print(f"prompt tokens : {usage.prompt_tokens if usage else 'n/a'}")
    print(f"output tokens : {output_tokens}")
    print(f"TTFT          : {ttft * 1000:.0f} ms")
    print(f"TPOT          : {tpot * 1000:.1f} ms/token")
    print(
        f"throughput    : {output_tokens / (end - start):.1f} tokens/s (single request)"
    )
    print("\nPASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
