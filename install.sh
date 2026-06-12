#!/usr/bin/env bash
set -euo pipefail

repo_url="${DEVAGENT_REPO_URL:-https://github.com/Hqzdev/pilot-agent.git}"
src="${DEVAGENT_SRC:-$HOME/.devagent-src}"
bin_dir="${DEVAGENT_BIN_DIR:-$HOME/.local/bin}"
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
  cat > "$bin_dir/devagent" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exec docker compose -f "$HOME/.devagent-src/docker-compose.yml" run --rm \
  -v "$PWD":/workspace \
  -e TERM="${TERM:-xterm-256color}" \
  devagent "$@"
EOF
  chmod +x "$bin_dir/devagent"
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
  if ! command -v devagent >/dev/null 2>&1; then
    echo "Add this to your shell rc, then restart the terminal:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
  fi
  "$bin_dir/devagent" version || true
else
  install_uv_if_missing
  if uv tool list | grep -q '^devagent '; then
    uv tool upgrade devagent
  else
    uv tool install "git+$repo_url"
  fi
  command -v devagent >/dev/null 2>&1 || {
    echo "Add uv's tool directory to PATH, then rerun: devagent version"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
  }
fi

echo "✓ DevAgent установлен ($mode)"
echo "Дальше:"
echo "  cd <папка проекта>"
echo "  devagent setup     # первичная настройка (1 минута)"
echo "  devagent init && devagent run"
