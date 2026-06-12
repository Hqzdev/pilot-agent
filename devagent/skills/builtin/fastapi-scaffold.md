---
name: fastapi-scaffold
description: Scaffold a FastAPI service with uv, pydantic-settings, and a healthcheck endpoint.
triggers: [fastapi, python, api]
version: 1
source: builtin
success_count: 0
failure_count: 0
deprecated: false
---
## When to use
Use when creating a Python HTTP API MVP with FastAPI and uv.

## Steps
1. Create `app/main.py`, `app/settings.py`, and `tests/test_health.py`.
2. Add dependencies: `uv add fastapi uvicorn pydantic-settings`.
3. Add a health endpoint:
   `@app.get("/health")` returning `{"status": "ok"}`.
4. Run locally with `uv run uvicorn app.main:app --reload --port 8000`.

## Known pitfalls
- Keep settings in `BaseSettings`; do not read secrets at import time.
- Use `python-dotenv` only for local development, not as the deployment secret store.
- Health checks should not depend on external services.

## Verified commands
- `uv run pytest`
- `uv run uvicorn app.main:app --port 8000`
- `curl -fsS http://localhost:8000/health`
