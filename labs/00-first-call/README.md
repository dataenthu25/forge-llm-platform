# Lab 0: your first call to a self-hosted LLM

Goal: run an open-weight model on your own machine and talk to it with the same
SDK people use for OpenAI. No Kubernetes yet; that is Lab 1.

## Steps

```bash
cd labs/00-first-call
docker compose up          # first run downloads ~1 GB of model weights
```

Wait for the log line `Application startup complete`. In a second terminal:

```bash
curl localhost:8000/v1/models                       # what is being served?
curl localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen2.5-0.5b-instruct","messages":[{"role":"user","content":"Hello!"}]}'

uv run ../../scripts/smoke_test.py                  # same thing from Python, with timings
curl -s localhost:8000/metrics | grep '^vllm:' | head -30   # Prometheus metrics
```

## What to notice

1. **Startup is slow, requests are fast.** Most of startup is loading weights
   into memory. That is why the Helm chart in Lab 1 has a long `startupProbe`.
2. **The answer streams.** The smoke test prints TTFT and TPOT. Run it with
   `--max-tokens 8` and `--max-tokens 256`: TTFT barely changes, total time grows
   with output length. Read [docs/learn/00-how-llm-serving-works.md](../../docs/learn/00-how-llm-serving-works.md) for why.
3. **It is just HTTP.** `/v1/chat/completions` is the OpenAI API shape. Anything
   that speaks it (LangChain, LlamaIndex, the `openai` SDK) works unchanged.
4. **`/metrics`.** Find `vllm:num_requests_running`, `vllm:num_requests_waiting`
   and `vllm:kv_cache_usage_perc` (called `gpu_cache_usage_perc` in older vLLM). Phase 3 and 4 build on them.

## Try this

- Send 10 requests at once (`for i in $(seq 10); do uv run ../../scripts/smoke_test.py & done`)
  and watch `vllm:num_requests_running` in `/metrics`. That is continuous batching.
- Restart with `--max-model-len=512` and send a long prompt. Read the error.
