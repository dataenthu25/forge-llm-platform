# Forge: a self-hosted LLM inference platform on Kubernetes

[![ci](https://github.com/dataenthu25/forge-llm-platform/actions/workflows/ci.yaml/badge.svg)](https://github.com/dataenthu25/forge-llm-platform/actions/workflows/ci.yaml)

Forge runs open-weight LLMs (Qwen, Llama, …) on Kubernetes with
[vLLM](https://github.com/vllm-project/vllm) and grows, phase by phase, into the
platform a company would put under its AI features: an OpenAI-compatible
gateway with tenants and quotas, LLM-specific observability, autoscaling on
queue depth, and model releases gated by evals and canaries.

It is also a learning log. Every phase ships a plain-language explainer in
[`docs/learn/`](docs/learn/), written from the point of view of a DevOps
engineer moving into LLMOps.

## Roadmap

| Phase | What | Status |
|---|---|---|
| 0 | Run vLLM locally, learn the core serving concepts | ✅ [Lab 0](labs/00-first-call/) |
| 1 | vLLM on Kubernetes: Helm chart, kind cluster, CI that serves a real model | ✅ this release |
| 2 | FastAPI gateway: OpenAI-compatible, tenants, API keys, rate limits, token metering (Postgres + Redis) | ⏳ |
| 3 | Observability: TTFT/TPOT/throughput dashboards, SLOs, tracing | ⏳ |
| 4 | Autoscaling with KEDA + GPU tuning and benchmarks on AKS | ⏳ |
| 5 | Eval-gated releases: eval suite, load tests, Argo Rollouts canary | ⏳ |
| 6 | Demo RAG tenant on pgvector, polish | ⏳ |

## Quick start (local, no GPU needed)

Prerequisites: Docker, [kind](https://kind.sigs.k8s.io/), kubectl, Helm, [uv](https://docs.astral.sh/uv/). About 8 GB of free RAM.

```bash
make tools          # check prerequisites
make cluster-up     # local Kubernetes cluster in Docker
make deploy         # install the vLLM pool (Qwen2.5-0.5B on CPU)
make wait           # first start downloads the model, give it a few minutes
make port-forward   # in a second terminal
make smoke          # call the model and print TTFT / TPOT / tokens per second
```

The smoke test prints the served models, the answer, and three latency numbers (TTFT, TPOT, tokens/s) that are explained in [doc 00](docs/learn/00-how-llm-serving-works.md). Phase 4 publishes real GPU benchmarks.

## Repository layout

```
deploy/charts/vllm-pool/   Helm chart for a pool of vLLM servers (CPU and GPU values)
deploy/kind/               local cluster config
scripts/smoke_test.py      OpenAI-SDK smoke test with latency metrics
labs/                      hands-on exercises, one per concept
docs/learn/                explainers: LLM serving basics, Python for Java devs, vLLM on K8s
.github/workflows/         CI: lint + deploy to a kind cluster and run the smoke test
```

## Learn along

1. [How LLM serving works (for infrastructure people)](docs/learn/00-how-llm-serving-works.md)
2. [Python for a Java / Spring Boot developer](docs/learn/01-python-for-java-devs.md)
3. [Running vLLM on Kubernetes: a guided tour of the chart](docs/learn/02-vllm-on-kubernetes.md)

## License

MIT
