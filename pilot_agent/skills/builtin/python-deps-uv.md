---
name: python-deps-uv
description: Manage Python dependencies with uv without drifting from the lock file.
triggers: [python, dependencies, uv]
version: 1
source: builtin
success_count: 0
failure_count: 0
deprecated: false
---
## When to use
Use whenever adding, removing, syncing, or running Python dependencies in a uv
project.

## Steps
1. Add runtime dependencies with `uv add <package>`.
2. Add dev-only dependencies with `uv add --dev <package>`.
3. Run project commands through `uv run <command>` unless the repo already has
   a `.venv` and scripts intentionally call `.venv/bin/...`.
4. Sync from lock with `UV_CACHE_DIR=.uv-cache uv sync --all-groups --frozen`
   in CI or verification.
5. Regenerate the lock with `UV_CACHE_DIR=.uv-cache uv lock` after changing
   `pyproject.toml`.
6. Read resolver errors from the bottom up. The last "because" chain usually
   names the incompatible package pair.
7. Pin only when necessary: `uv add 'fastapi>=0.115,<0.116'`.

## Known pitfalls
- Do not run `pip install` inside a uv-managed project. It mutates the venv
  without updating `uv.lock`.
- A system `python` can differ from uv's Python. Prefer `uv run python`.
- If `uv sync --frozen` fails, the lock file is stale; run `uv lock`, inspect
  the diff, and commit both `pyproject.toml` and `uv.lock`.
- Resolver conflicts are often caused by old transitive pins. Avoid adding a
  top-level pin unless the error proves it is needed.

## Verified commands
- `UV_CACHE_DIR=.uv-cache uv lock --check`
- `UV_CACHE_DIR=.uv-cache uv sync --all-groups --frozen`
- `uv run python --version`
