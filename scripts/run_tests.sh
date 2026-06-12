#!/usr/bin/env bash
set -euo pipefail

export UV_CACHE_DIR="${UV_CACHE_DIR:-.uv-cache}"

uv sync --all-groups --frozen

.venv/bin/ruff check pilot_agent tests
.venv/bin/mypy --no-incremental --no-sqlite-cache pilot_agent
.venv/bin/pytest
.venv/bin/python -m compileall pilot_agent
.venv/bin/python -m pilot_agent.cli --help >/dev/null
