#!/usr/bin/env bash
set -euo pipefail

export UV_CACHE_DIR="${UV_CACHE_DIR:-.uv-cache}"

uv sync --all-groups --frozen

.venv/bin/ruff check devagent tests
.venv/bin/mypy --no-incremental --no-sqlite-cache devagent
.venv/bin/pytest
.venv/bin/python -m compileall devagent
.venv/bin/python -m devagent.cli --help >/dev/null
