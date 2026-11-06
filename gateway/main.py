import json
import os
import redis.asyncio as redis

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
import time

load_dotenv()

VLLM_URL = os.getenv("VLLM_URL", "http://localhost:8000")
API_KEYS: dict[str, str] = json.loads(os.getenv("API_KEYS", "{}"))

# Running totals per team. Kept in memory for now; Postgres comes later.
USAGE: dict[str, dict[str, int]] = {}
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "5"))
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = redis.from_url(REDIS_URL)
app = FastAPI(title="Forge Gateway")
WINDOWS: dict[str, tuple[int,int]] = {}

def check_rate_limit(team: str) -> None:
    now = time.time()
    current_minute = int(now // 60)
    window, count = WINDOWS.get(team, (current_minute, 0))
    if window != current_minute:  # a new minute started: reset
        window, count = current_minute, 0
    if count >= RATE_LIMIT_PER_MINUTE:
        retry_after = 60 - int(now % 60)
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
    WINDOWS[team] = (window, count + 1)


def check_api_key(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing API key")
    key = authorization.removeprefix("Bearer ")
    team = API_KEYS.get(key)
    if team is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return team


def record_usage(team: str, usage: dict) -> None:
    totals = USAGE.setdefault(
        team, {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0}
    )
    totals["requests"] += 1
    totals["prompt_tokens"] += usage.get("prompt_tokens", 0)
    totals["completion_tokens"] += usage.get("completion_tokens", 0)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/usage")
def get_usage():
    return USAGE


@app.post("/v1/chat/completions")
async def chat(request: Request, authorization: str | None = Header(default=None)):
    team = check_api_key(authorization)
    check_rate_limit(team)
    body = await request.json()
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            resp = await client.post(f"{VLLM_URL}/v1/chat/completions", json=body)
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502, detail="Model server unavailable"
            ) from exc
    data = resp.json()
    if resp.status_code == 200:
        record_usage(team, data.get("usage", {}))
        print(f"{team} used {data.get('usage', {}).get('total_tokens', 0)} tokens")
    return JSONResponse(data, status_code=resp.status_code)
