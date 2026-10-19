# 02 · Running vLLM on Kubernetes: a guided tour of the chart

The chart in `deploy/charts/vllm-pool/` deploys one **pool**: N identical vLLM
pods serving one model behind one Service. Later phases run several pools
(stable, canary, embeddings) behind the Forge gateway.

Below is every decision in the chart and why an LLM server needs it. Most
of these are things a generic web-app chart gets wrong.

## Deployment (`templates/deployment.yaml`)

**`args: --model ... --served-model-name ...`**
`--model` is the Hugging Face id that vLLM downloads. `--served-model-name`
is the stable alias clients use. When we swap the model version, clients
don't change. This is the first step towards model routing.

**`--max-model-len`**
Caps prompt + answer tokens per request. It directly bounds KV-cache memory
per request (see doc 00). Too high on a small machine and vLLM refuses to
start because the cache won't fit.

**Rolling update with `maxSurge: 1, maxUnavailable: 0`**
A new pod needs minutes to load weights. We never take an old pod away
before the new one is Ready, or capacity drops during every deploy.

**Three probes, three jobs**

| Probe | Question | Setting |
|---|---|---|
| `startupProbe` | "Has the model finished loading?" | Up to 30 min (180 × 10 s). Download + load is slow. |
| `readinessProbe` | "Send me traffic?" | Fast, every 5 s. |
| `livenessProbe` | "Am I stuck, restart me?" | Only starts after startup succeeds, so a slow load is never killed. |

Without a startup probe, a liveness probe would kill the pod mid-load and it
would restart forever (a classic first-day bug).

**`preStop: sleep` + `terminationGracePeriodSeconds`**
LLM responses stream for many seconds. When a pod is told to stop, the
Service takes a moment to stop routing to it. The sleep keeps the pod
serving in-flight streams so users don't see cut-off answers during a deploy
or scale-down.

**`/dev/shm` as an in-memory `emptyDir`**
vLLM's worker processes share data through shared memory. Docker's default
64 MB is far too small and leads to confusing crashes.

**Model cache on a PersistentVolumeClaim (`templates/pvc.yaml`)**
Weights are gigabytes. Caching them on a volume (`HF_HOME=/models`) means a
pod restart reloads from disk instead of re-downloading from Hugging Face.
`helm.sh/resource-policy: keep` stops `helm uninstall` from deleting it.
(With several replicas you'd use a ReadWriteMany volume or pre-baked node
cache; that comes in Phase 4.)

**GPU support (`values-gpu.yaml`)**
Setting `gpu.enabled=true` adds `nvidia.com/gpu: 1` to the pod's limits. The
NVIDIA device plugin on the node advertises that resource, the same way it
advertises CPU and memory. GPU nodes usually carry a **taint** so ordinary
pods stay off expensive hardware, hence the matching toleration.

**Prometheus annotations**
vLLM serves metrics on `/metrics`. Phase 3 scrapes them.

## Service and PodDisruptionBudget

A plain ClusterIP Service on port 8000. The PDB stops a node drain (e.g. an
AKS upgrade) from evicting every replica at once.

## Values: CPU vs GPU

`values.yaml` defaults to the CPU image and a 0.5B-parameter model, so it runs
on a laptop and on a free GitHub Actions runner. `values-gpu.yaml` switches
to the CUDA image, a bigger model and GPU flags:

- `--gpu-memory-utilization 0.90`: vLLM pre-allocates 90% of GPU memory
  (weights + KV cache). Unlike the JVM, it grabs it all at startup.
- `--enable-prefix-caching`: reuse KV cache for shared prompt prefixes.

## How CI tests this for real

`.github/workflows/ci.yaml` creates a kind cluster on the CI runner, installs
the chart, waits for the model to load, port-forwards and runs
`scripts/smoke_test.py`. Every PR proves the chart actually serves a model, not
just that the YAML is valid.

## Exercises

1. `make deploy` then `kubectl get pod -w`. Note how long it stays `Running` but not `Ready`. That's the startup probe.
2. Run the smoke test in a loop and trigger `kubectl rollout restart deploy/chat-vllm-pool`. Do any requests fail? Watch `kubectl get pods`: the old pod keeps serving until the new one is Ready. That's `maxUnavailable: 0`.
3. Set `drainSeconds: 0`, redeploy, and repeat. What changes?
