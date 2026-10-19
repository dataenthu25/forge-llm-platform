# 00 · How LLM serving works (for infrastructure people)

You already know how to run a Spring Boot service: a request comes in, the
service does some CPU work and a DB call, a response goes out in ~50 ms.
An LLM server is different in three ways that drive every design choice in Forge.

## 1. Text is processed as tokens

A model doesn't read characters or words. A **tokenizer** splits text into
**tokens** (about ¾ of an English word each) and maps each token to a number.

```
"Kubernetes is great"  →  ["Kub", "ernetes", " is", " great"]  →  [42, 9133, 374, 2294]
```

Everything is counted in tokens: request size, response size, context limit
(`--max-model-len`), and cost. "Price per 1M tokens" is the LLM version of
"price per request".

## 2. Generation happens in two phases

**Prefill.** The model reads the whole prompt in one pass. This is
compute-heavy but parallel, so a 1,000-token prompt is not 1,000× slower than a
1-token one.

**Decode.** The model produces the answer **one token at a time**. Each new
token needs a full pass through the model and depends on all the tokens
before it. A 300-token answer means 300 sequential steps.

That is why we measure three numbers instead of one "latency":

| Metric | Meaning | What users feel | Mostly driven by |
|---|---|---|---|
| **TTFT** (time to first token) | Request sent → first token back | "Is it doing anything?" | Prefill, queueing |
| **TPOT / ITL** (time per output token) | Gap between streamed tokens | Reading speed | Decode, batch size |
| **Throughput** (tokens/s) | Total tokens generated per second by the server | Your cost per token | Batching, GPU usage |

`scripts/smoke_test.py` prints all three. A typical SLO looks like "p95 TTFT
< 800 ms and p95 TPOT < 50 ms".

**Why streaming matters.** Answers take seconds, so servers stream tokens back
as they are produced (Server-Sent Events). The client sees text in under a second
even if the full answer takes ten. Your gateway, ingress and load balancer must
not buffer responses, or the stream breaks.

## 3. Memory, not CPU, is the bottleneck

A model is a large file of numbers called **weights** (the "parameters").
Rough sizing:

```
memory for weights ≈ parameters × bytes per parameter
Qwen2.5-0.5B in bf16 (2 bytes)  ≈ 1 GB
Llama-3.1-8B in bf16            ≈ 16 GB
Llama-3.1-8B in 4-bit AWQ       ≈ 5 GB     ← "quantization" = fewer bytes per weight
```

On top of the weights, every in-flight request needs a **KV cache**: the
model's working memory of the tokens it has seen so far. It grows with
context length × number of concurrent requests. When the KV cache is full,
new requests wait in a queue. That is why vLLM exposes
`vllm:num_requests_waiting` and `vllm:kv_cache_usage_perc`, and why Forge
autoscales on queue depth rather than CPU (Phase 4).

Your DevOps intuition: **the KV cache is like a connection pool**. Size it too
small and requests queue; there is no "just add CPU" fix.

## 4. What vLLM adds

A naive server handles one request at a time and wastes most of the GPU.
vLLM is the most widely used open-source serving engine because of:

- **Continuous batching.** Instead of waiting for a whole batch to finish,
  vLLM adds and removes requests at every decode step. Think of it as a
  thread pool that never idles, versus a batch job.
- **PagedAttention.** The KV cache is stored in fixed-size blocks, like OS
  virtual-memory pages, so memory isn't wasted on reserved space. This means
  more concurrent requests fit on the same GPU.
- **Prefix caching.** Requests that share a prompt prefix (e.g. the same system
  prompt) reuse the cached KV blocks, which cuts TTFT.
- **An OpenAI-compatible API.** `/v1/chat/completions`, `/v1/models` and
  `/v1/embeddings`, so any OpenAI client works unchanged.
- **Prometheus metrics** on `/metrics`.

## 5. Mapping to what you know

| You know | LLM world |
|---|---|
| Docker image + JAR | vLLM image + model weights (downloaded separately, gigabytes) |
| JVM heap sizing | GPU memory: weights + KV cache (`--gpu-memory-utilization`) |
| Slow JVM startup / warm-up | Model load: minutes → long `startupProbe` |
| Request latency p95 | TTFT p95 and TPOT p95 |
| Requests/sec | Tokens/sec |
| Thread pool / connection pool exhaustion | KV cache full → `num_requests_waiting` grows |
| HPA on CPU | KEDA on queue depth (CPU is a bad signal for GPU work) |
| Blue/green on a new JAR | Canary on a new **model version**, gated by evals (Phase 5) |

## Check yourself

1. Why does doubling `max_tokens` barely change TTFT?
2. Why can a server at 30% CPU still be "full"?
3. Which takes more memory: 50 users with 500-token chats, or 5 users with 8,000-token documents?

(Answers: 1. TTFT is prefill only; decode happens after. 2. The KV cache, not CPU, is the limit.
3. The 5 long documents: 40k tokens of KV cache vs 25k. Long contexts are expensive.)
