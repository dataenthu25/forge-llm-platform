import json
import os
import time
from contextlib import asynccontextmanager

import asyncpg
import httpx
import redis.asyncio as redis
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

load_dotenv()

VLLM_URL = os.getenv("VLLM_URL", "http://localhost:8000")
API_KEYS: dict[str, str] = json.loads(os.getenv("API_KEYS", "{}"))

RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "5"))
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = redis.from_url(REDIS_URL)

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://forge:forge@localhost:5433/forge"
)
db_pool: asyncpg.Pool | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once at startup (before yield) and once at shutdown (after yield).
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    yield
    await db_pool.close()


app = FastAPI(title="Forge Gateway", lifespan=lifespan)


async def check_rate_limit(team: str) -> None:
    now = time.time()
    current_minute = int(now // 60)
    key = f"ratelimit:{team}:{current_minute}"
    count = await redis_client.incr(key)
    if count == 1:  # first request this minute: let Redis delete the key later
        await redis_client.expire(key, 60)
    if count > RATE_LIMIT_PER_MINUTE:
        retry_after = 60 - int(now % 60)
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )


def check_api_key(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing API key")
    key = authorization.removeprefix("Bearer ")
    team = API_KEYS.get(key)
    if team is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return team


async def record_usage(team: str, model: str, usage: dict, latency_ms: int) -> None:
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO usage_events (team, model, prompt_tokens, completion_tokens, latency_ms)
            VALUES ($1, $2, $3, $4, $5)
            """,
            team,
            model,
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
            latency_ms,
        )


@app.get("/health")
async def health():
    try:
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
    except (OSError, asyncpg.PostgresError, asyncpg.InterfaceError) as e:
        # Database is unreachable: tell the caller (and Kubernetes) to wait.
        return JSONResponse(
            status_code=503, content={"status": "degraded", "db": str(e)}
        )
    return {"status": "ok", "db": "ok"}


@app.get("/usage")
async def get_usage():
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT team,
                   COUNT(*)                  AS requests,
                   SUM(prompt_tokens)        AS prompt_tokens,
                   SUM(completion_tokens)    AS completion_tokens,
                   ROUND(AVG(latency_ms))    AS avg_latency_ms
            FROM usage_events
            GROUP BY team
            ORDER BY team
            """
        )
    # Each row is like a Map; turn them into {"team-b": {...}, ...}
    return {r["team"]: {k: int(v) for k, v in r.items() if k != "team"} for r in rows}


@app.post("/v1/chat/completions")
async def chat(request: Request, authorization: str | None = Header(default=None)):
    team = check_api_key(authorization)
    await check_rate_limit(team)
    body = await request.json()
    async with httpx.AsyncClient(timeout=120) as client:
        start = time.perf_counter()  # a stopwatch, like System.nanoTime()
        try:
            resp = await client.post(f"{VLLM_URL}/v1/chat/completions", json=body)
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502, detail="Model server unavailable"
            ) from exc
        latency_ms = int((time.perf_counter() - start) * 1000)
    data = resp.json()
    if resp.status_code == 200:
        await record_usage(
            team, data.get("model", "unknown"), data.get("usage", {}), latency_ms
        )
        print(
            f"{team} used {data.get('usage', {}).get('total_tokens', 0)} tokens in {latency_ms} ms"
        )
    return JSONResponse(data, status_code=resp.status_code)
