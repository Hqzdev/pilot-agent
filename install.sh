#!/usr/bin/env bash
set -euo pipefail

repo_url="${PILOT_AGENT_REPO_URL:-https://github.com/Hqzdev/pilot-agent.git}"
src="${PILOT_AGENT_SRC:-$HOME/.pilot-agent-src}"
bin_dir="${PILOT_AGENT_BIN_DIR:-$HOME/.local/bin}"
mode="native"

case "$(uname -s)" in
  Darwin|Linux) ;;
  *)
    echo "Unsupported platform. On Windows use WSL2, then rerun this command."
    exit 1
    ;;
esac

has() {
  command -v "$1" >/dev/null 2>&1
}

clone_or_update() {
  if [ -d "$src/.git" ]; then
    git -C "$src" pull --ff-only
  elif [ -e "$src" ]; then
    echo "$src exists but is not a git checkout. Move it aside and rerun install.sh."
    exit 1
  else
    git clone --depth 1 "$repo_url" "$src"
  fi
}

install_wrapper() {
  mkdir -p "$bin_dir"
  cat > "$bin_dir/pilot-agent" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exec docker compose -f "$HOME/.pilot-agent-src/docker-compose.yml" run --rm \
  -v "$PWD":/workspace \
  -e TERM="${TERM:-xterm-256color}" \
  pilot-agent "$@"
EOF
  chmod +x "$bin_dir/pilot-agent"
}

install_uv_if_missing() {
  if has uv; then
    return
  fi
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
}

if has docker && docker info >/dev/null 2>&1; then
  mode="docker"
  clone_or_update
  docker compose -f "$src/docker-compose.yml" build
  install_wrapper
  if ! command -v pilot-agent >/dev/null 2>&1; then
    echo "Add this to your shell rc, then restart the terminal:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
  fi
  "$bin_dir/pilot-agent" version || true
else
  install_uv_if_missing
  if uv tool list | grep -q '^pilot-agent '; then
    uv tool upgrade pilot-agent
  else
    uv tool install "git+$repo_url"
  fi
  command -v pilot-agent >/dev/null 2>&1 || {
    echo "Add uv's tool directory to PATH, then rerun: pilot-agent version"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
  }
fi

echo "✓ Pilot Agent installed ($mode)"
echo "Next:"
echo "  cd <project-folder>"
echo "  pilot-agent setup     # first-time setup (1 minute)"
echo "  pilot-agent init && pilot-agent run"
