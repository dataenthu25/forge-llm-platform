# Forge Gateway

An OpenAI-compatible API gateway that sits in front of vLLM. Clients call it
exactly like the OpenAI API; the gateway adds what a shared platform needs:

| Feature | How it works |
|---|---|
| **API keys per team** | `Authorization: Bearer <key>` is mapped to a team name. Missing or unknown key: `401`. |
| **Rate limit per team** | Fixed window in **Redis** (`INCR` + `EXPIRE` on `ratelimit:{team}:{minute}`), shared by every gateway replica. Over the limit: `429` with `Retry-After`. |
| **Usage metering** | Every successful request is saved as one row in **Postgres** (`usage_events`: team, model, tokens, latency, time). |
| **Health check** | `/health` checks the database and returns `503` when it is unreachable, ready for a Kubernetes readiness probe. |
| **Model down** | If vLLM can't be reached, the gateway answers `502`. |

```
client ──► gateway ──► vLLM
             │  │
             │  └──► Postgres  (usage_events)
             └─────► Redis     (rate limit counters)
```

## Run it locally

You need Docker and [uv](https://docs.astral.sh/uv/). The ports below avoid
clashing with any Redis or Postgres you already run.

**1. Start the dependencies**

```bash
# the model server (first start downloads the model)
docker run -d --name forge-vllm -p 8000:8000 --shm-size=2g \
  -e VLLM_CPU_KVCACHE_SPACE=2 \
  -v hf-cache:/root/.cache/huggingface \
  vllm/vllm-openai-cpu:v0.31.0 \
  --model=Qwen/Qwen2.5-0.5B-Instruct --served-model-name=qwen --max-model-len=2048

docker run -d --name forge-redis -p 6380:6379 redis:7.4

docker run -d --name forge-postgres \
  -e POSTGRES_USER=forge -e POSTGRES_PASSWORD=forge -e POSTGRES_DB=forge \
  -p 5433:5432 postgres:17
```

Next time, `docker start forge-vllm forge-redis forge-postgres` is enough.

**2. Create the table** (safe to run again)

```bash
docker exec -i forge-postgres psql -U forge < gateway/schema.sql
```

**3. Configure and start the gateway**

```bash
cd gateway
cp .env.example .env      # then edit the API keys
uv sync
uv run uvicorn main:app --port 9100 --reload
```

The gateway refuses to start if Postgres is down (like a Spring Boot app that
can't reach its datasource). Once running, it survives a database restart and
reconnects by itself.

## Try it

```bash
curl -s localhost:9100/health
# {"status":"ok","db":"ok"}

curl -s localhost:9100/v1/chat/completions \
  -H "Authorization: Bearer sk-team-a-123" -H "Content-Type: application/json" \
  -d '{"model":"qwen","messages":[{"role":"user","content":"Say hi"}],"max_tokens":10}'

curl -s localhost:9100/usage
# {"team-a":{"requests":1,"prompt_tokens":31,"completion_tokens":10,"avg_latency_ms":761}}
```

Send more than `RATE_LIMIT_PER_MINUTE` requests in one minute to see the `429`.

## Configuration

Read from environment variables, or from `.env` (see `.env.example`).

| Variable | Default | Meaning |
|---|---|---|
| `VLLM_URL` | `http://localhost:8000` | vLLM base URL. In Kubernetes: `http://chat-vllm-pool:8000`. |
| `API_KEYS` | `{}` | JSON object mapping bearer tokens to team names. |
| `RATE_LIMIT_PER_MINUTE` | `5` | Requests per team per minute. |
| `REDIS_URL` | `redis://localhost:6379` | Redis for rate limit counters. |
| `DATABASE_URL` | `postgresql://forge:forge@localhost:5433/forge` | Postgres for usage. |

Never commit `.env` or real API keys. In Kubernetes, provide `API_KEYS` and the
database password through a Secret.

## Endpoints

| Method | Path | What |
|---|---|---|
| `POST` | `/v1/chat/completions` | OpenAI-compatible chat, proxied to vLLM |
| `GET` | `/usage` | Requests, tokens and average latency per team, from Postgres |
| `GET` | `/health` | `200` when the database is reachable, `503` when it isn't |

## Checks

CI runs these on every PR; run them before you push:

```bash
uv sync --locked
uvx ruff check .
uvx ruff format --check .
uv run python -c "import main"
```
