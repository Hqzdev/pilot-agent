#!/usr/bin/env bash
set -euo pipefail

export UV_CACHE_DIR="${UV_CACHE_DIR:-.uv-cache}"

uv run ruff check devagent tests
uv run mypy devagent
uv run pytest
uv run python -m compileall devagent
uv run python -m devagent.cli --help >/dev/null
