# One-command workflows. Run `make help` to list them.
CLUSTER      ?= forge
NAMESPACE    ?= forge
RELEASE      ?= chat
CHART        := deploy/charts/vllm-pool
VALUES       ?= $(CHART)/values.yaml
LOCAL_PORT   ?= 8000

.PHONY: help tools cluster-up cluster-down deploy wait port-forward smoke logs undeploy lint

help: ## List targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

tools: ## Check required CLIs are installed
	@for t in docker kind kubectl helm uv; do command -v $$t >/dev/null || { echo "missing: $$t"; exit 1; }; done; echo "all tools found"

cluster-up: ## Create the local kind cluster
	kind get clusters | grep -qx $(CLUSTER) || kind create cluster --config deploy/kind/cluster.yaml
	kubectl create namespace $(NAMESPACE) --dry-run=client -o yaml | kubectl apply -f -

cluster-down: ## Delete the local kind cluster
	kind delete cluster --name $(CLUSTER)

deploy: ## Install or upgrade the vLLM pool
	helm upgrade --install $(RELEASE) $(CHART) -n $(NAMESPACE) -f $(VALUES)

wait: ## Wait until the model is loaded and ready (can take minutes on first run)
	kubectl -n $(NAMESPACE) rollout status deploy/$(RELEASE)-vllm-pool --timeout=30m

port-forward: ## Expose the pool on localhost:$(LOCAL_PORT)
	kubectl -n $(NAMESPACE) port-forward svc/$(RELEASE)-vllm-pool $(LOCAL_PORT):8000

smoke: ## Run the smoke test against localhost:$(LOCAL_PORT)
	uv run scripts/smoke_test.py --base-url http://localhost:$(LOCAL_PORT)/v1

logs: ## Tail vLLM logs
	kubectl -n $(NAMESPACE) logs -f deploy/$(RELEASE)-vllm-pool

undeploy: ## Remove the release (the model cache volume is kept)
	helm uninstall $(RELEASE) -n $(NAMESPACE)

lint: ## Lint the chart and Python code
	helm lint $(CHART)
	helm lint $(CHART) -f $(CHART)/values-gpu.yaml
	uvx ruff check scripts
	uvx ruff format --check scripts
