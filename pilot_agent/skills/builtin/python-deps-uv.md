---
name: python-deps-uv
description: Manage Python dependencies with uv add, sync, run, and lock-file recovery.
triggers: [python, uv, dependencies]
version: 1
source: builtin
success_count: 0
failure_count: 0
deprecated: false
---
## When to use
Use for Python package setup, dependency additions, and reproducible commands.

## Steps
1. Add runtime packages with `uv add package-name`.
2. Add development packages with `uv add --dev pytest ruff mypy`.
3. Sync from lock with `uv sync --frozen` in CI.
4. Run commands through `uv run`, for example `uv run pytest`.
5. In restricted sandboxes, set `UV_CACHE_DIR=.uv-cache` if the default cache is blocked.

## Known pitfalls
- `uv run` can fail before project creation if `pyproject.toml` is absent.
- Do not commit `.venv/` or `.uv-cache/`.
- After changing Python constraints, regenerate `uv.lock` with `uv sync`.

## Verified commands
- `UV_CACHE_DIR=.uv-cache uv sync`
- `UV_CACHE_DIR=.uv-cache uv run pytest`
