#!/usr/bin/env bash
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

UV_CACHE_DIR="${UV_CACHE_DIR:-.uv-cache}" uv sync --all-groups

if command -v pre-commit >/dev/null 2>&1; then
  pre-commit install
else
  echo "pre-commit not installed; skipping hook setup"
fi

cat > pilot-agent-dev <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exec uv run pilot-agent "$@"
EOF
chmod +x pilot-agent-dev

cat > pilot-agent <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exec uv run pilot-agent "$@"
EOF
chmod +x pilot-agent

echo "OK: run ./pilot-agent --help"
