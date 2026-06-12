#!/usr/bin/env bash
set -euo pipefail

docker compose build
docker compose run --rm devagent version
docker compose run --rm devagent doctor --json || true

if [ "${DEVAGENT_RELEASE_CHECK:-0}" = "1" ]; then
  if grep -R "NotImplementedError\\|TODO:" devagent docs tests README.md AGENTS.md CONTRIBUTING.md SECURITY.md; then
    echo "Release gate failed: NotImplementedError or TODO marker remains."
    exit 1
  fi
fi
