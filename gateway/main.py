import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

VLLM_URL = "http://localhost:8000"

API_KEYS = {
    "sk-team-a-123": "team-a",
    "sk-team-b-456": "team-b",
}

# Running totals per team. Kept in memory for now; Postgres comes later.
USAGE: dict[str, dict[str, int]] = {}

app = FastAPI(title="Forge Gateway")


def check_api_key(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing API key")
    key = authorization.removeprefix("Bearer ")
    team = API_KEYS.get(key)
    if team is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return team


def record_usage(team: str, usage: dict) -> None:
    totals = USAGE.setdefault(team, {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0})
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
    body = await request.json()
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{VLLM_URL}/v1/chat/completions", json=body)
    data = resp.json()
    if resp.status_code == 200:
        record_usage(team, data.get("usage", {}))
        print(f"{team} used {data['usage']['total_tokens']} tokens")
    return JSONResponse(data, status_code=resp.status_code)
