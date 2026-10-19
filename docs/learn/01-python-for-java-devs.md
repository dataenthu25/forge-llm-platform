# 01 · Python for a Java / Spring Boot developer

Just enough Python to read and write everything in this repo. Each line maps
something you know to its Python equivalent.

## Tooling

| Java | Python (in this repo) |
|---|---|
| JDK install / SDKMAN | `uv python install 3.12` |
| Maven / Gradle | [`uv`](https://docs.astral.sh/uv/): dependencies, virtualenvs, running scripts |
| `pom.xml` | `pyproject.toml` |
| `~/.m2` per project | `.venv/` folder per project (a "virtual environment") |
| Checkstyle + Spotless | `ruff check` + `ruff format` |
| Compiler type checks | `mypy` (optional static checking of type hints) |
| JUnit | `pytest` |
| Spring Boot | FastAPI (Phase 2) |
| Jackson DTOs + Bean Validation | Pydantic models |
| `WebClient` | `httpx.AsyncClient` |
| JPA / Flyway | SQLAlchemy / Alembic |

`scripts/smoke_test.py` uses a neat uv feature: dependencies are declared in a
comment block at the top of the file, and `uv run scripts/smoke_test.py`
creates a throwaway environment with them. No setup needed.

## The language in 10 snippets

```python
# 1. Variables and type hints (hints are checked by tools, not at runtime)
model: str = "qwen2.5-0.5b-instruct"
max_tokens: int = 64
first_token_at: float | None = None      # like a nullable Double

# 2. Collections
models = ["a", "b"]                       # List<String>
limits = {"free": 10, "pro": 100}         # Map<String, Integer>
ids = [m.id for m in response.data]       # stream().map(...).toList()

# 3. Functions
def tpot(decode_seconds: float, tokens: int) -> float:
    return decode_seconds / max(tokens - 1, 1)

# 4. f-strings (String.format)
print(f"TTFT: {ttft * 1000:.0f} ms")

# 5. Classes: usually dataclasses or Pydantic instead of POJOs
from pydantic import BaseModel
class ChatRequest(BaseModel):             # validated DTO
    model: str
    max_tokens: int = 256

# 6. Exceptions
try:
    client.models.list()
except APIConnectionError as e:
    print(f"server down: {e}")

# 7. Context managers (try-with-resources)
with open("prompts.txt") as f:
    lines = f.readlines()

# 8. Iterators: a streaming response is just a for-loop
for chunk in stream:
    print(chunk.choices[0].delta.content, end="")

# 9. Entry point (public static void main)
if __name__ == "__main__":
    main()

# 10. async / await: covered below
```

## async / await (the one new concept)

FastAPI and our gateway are **async**. An LLM request spends seconds waiting
on the model server. With async, one process can wait on thousands of those
at once without a thread per request, much like Spring WebFlux or Java 21
virtual threads.

```python
import httpx

async def forward(payload: dict) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post("http://chat-vllm-pool:8000/v1/chat/completions", json=payload)
        return resp.json()
```

Rules of thumb:

- `async def` marks a function that can pause; `await` is where it pauses.
- Never call blocking code (e.g. `requests.get`, `time.sleep`) inside `async def`.
  Use the async version (`httpx`, `asyncio.sleep`).

## Practice before Phase 2

1. `uv init scratch && cd scratch && uv add fastapi uvicorn`.
2. Rebuild a tiny "todo" REST API in FastAPI with a Pydantic model and one test.
3. Compare with how you would write it in Spring Boot: you'll be surprised how short it is.
