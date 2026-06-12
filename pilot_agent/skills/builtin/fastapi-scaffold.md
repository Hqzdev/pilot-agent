---
name: fastapi-scaffold
description: Scaffold a FastAPI API with uv, pydantic-settings, and a health probe.
triggers: [python, fastapi, api, backend]
version: 1
source: builtin
success_count: 0
failure_count: 0
deprecated: false
---
## When to use
Use in Coding when the MVP needs a Python API or a backend service separate
from the frontend.

## Steps
1. Initialize dependencies with uv:
   `uv init --app --python 3.12`
   `uv add fastapi uvicorn pydantic-settings`
   `uv add --dev pytest httpx ruff mypy`
2. Create this structure:
   - `app/main.py`
   - `app/routers/`
   - `app/models.py`
   - `app/db.py`
   - `app/settings.py`
3. Add settings with `pydantic-settings`; read env vars through a single
   `Settings` class.
4. Add `/health` immediately:
   `@app.get("/health")`
   `def health() -> dict[str, str]: return {"status": "ok"}`
5. Start uvicorn without reload in verification:
   `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
6. Verify with `run_and_check` and `http_probe` `http://127.0.0.1:8000/health`.

## Known pitfalls
- `--reload` starts a supervisor process and can confuse process-group cleanup.
  Do not use reload in `run_and_check`.
- In Docker, bind to `0.0.0.0`; probe `127.0.0.1` from inside the same sandbox.
- Keep application creation in `app/main.py`. Avoid side-effect imports that
  connect to databases during module import.
- Do not mix global env reads across routers; use the settings object.

## Verified commands
- `uv add fastapi uvicorn pydantic-settings`
- `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`
- `curl -fsS http://127.0.0.1:8000/health`
