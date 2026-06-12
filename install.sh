#!/usr/bin/env bash
# Pilot Agent installer.
#
# What it writes:
#   - source checkout: ~/.pilot-agent-src
#   - command wrapper: ~/.local/bin/pilot-agent
#   - install log: /tmp/pilot-agent-install-<timestamp>.log
#
# It never uses sudo. User-space dependencies such as uv may be installed under
# ~/.local; system dependencies such as Docker or git are reported with an exact
# fix command and left to the user.
set -euo pipefail

repo_url="${PILOT_AGENT_REPO_URL:-https://github.com/Hqzdev/pilot-agent.git}"
src="${PILOT_AGENT_SRC:-$HOME/.pilot-agent-src}"
bin_dir="${PILOT_AGENT_BIN_DIR:-$HOME/.local/bin}"
log="${TMPDIR:-/tmp}/pilot-agent-install-$(date +%Y%m%d%H%M%S).log"
assume_yes=0
verbose="${PILOT_AGENT_INSTALL_VERBOSE:-0}"
mode="native"
step_label="preflight"

while [ "$#" -gt 0 ]; do
  case "$1" in
    -y|--yes) assume_yes=1 ;;
    -v|--verbose) verbose=1 ;;
    *) echo "Unknown option: $1"; exit 2 ;;
  esac
  shift
done

mkdir -p "$(dirname "$log")"
: > "$log"

use_color=0
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ] && command -v tput >/dev/null 2>&1; then
  use_color=1
fi
if [ "$use_color" -eq 1 ]; then
  accent="$(tput setaf 6)"
  green="$(tput setaf 2)"
  red="$(tput setaf 1)"
  yellow="$(tput setaf 3)"
  dim="$(tput dim)"
  reset="$(tput sgr0)"
else
  accent=""
  green=""
  red=""
  yellow=""
  dim=""
  reset=""
fi

case "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in
  *UTF-8*|*utf8*) ok="✓"; fail="✗"; warn="⚠"; arrow="→" ;;
  *) ok="+"; fail="x"; warn="!"; arrow="->" ;;
esac

say() {
  printf '%b\n' "$*"
}

has() {
  command -v "$1" >/dev/null 2>&1
}

fix_for_step() {
  case "$step_label" in
    preflight) echo "Check network access to github.com, then rerun: bash install.sh" ;;
    "Fetching Pilot Agent") echo "Check network/proxy settings, then rerun: bash install.sh" ;;
    "Building sandbox image") echo "Start Docker, then rerun: bash install.sh" ;;
    "Installing uv") echo "Install curl or check https://astral.sh/uv, then rerun: bash install.sh" ;;
    *) echo "Rerun anytime: bash install.sh" ;;
  esac
}

on_error() {
  rc=$?
  say "${red}${fail} failed at step ${step_label}, see log: ${log}${reset}"
  tail -n 5 "$log" 2>/dev/null || true
  say "$(fix_for_step)"
  exit "$rc"
}

on_interrupt() {
  say ""
  say "${yellow}${warn} installation cancelled, nothing broken - re-run anytime${reset}"
  exit 130
}

trap on_error ERR
trap on_interrupt INT

run_logged() {
  step_label="$1"
  shift
  local start
  local elapsed
  start="$(date +%s)"
  printf '[%s] %s ... ' "$step_label" "$*" >> "$log"
  if [ "$verbose" = "1" ]; then
    "$@" 2>&1 | tee -a "$log"
  else
    "$@" >> "$log" 2>&1
  fi
  elapsed=$(( $(date +%s) - start ))
  say "${green}${ok}${reset} ${step_label} ${dim}${elapsed}s${reset}"
}

install_commands_for_os() {
  case "$(uname -s)" in
    Darwin) echo "Install Docker Desktop: https://docs.docker.com/desktop/setup/install/mac-install/" ;;
    Linux)
      if has apt-get; then
        echo "Install Docker: sudo apt-get update && sudo apt-get install -y docker.io docker-compose-plugin"
      elif has brew; then
        echo "Install Docker Desktop: brew install --cask docker"
      else
        echo "Install Docker Desktop: https://docs.docker.com/get-docker/"
      fi
      ;;
  esac
}

preflight() {
  case "$(uname -s)" in
    Darwin|Linux) ;;
    *)
      say "${red}${fail} Unsupported platform. On Windows use WSL2, then rerun this command.${reset}"
      exit 2
      ;;
  esac
  if ! has git; then
    say "${red}${fail} git not found.${reset}"
    case "$(uname -s)" in
      Darwin) say "Run: brew install git" ;;
      Linux) say "Run: sudo apt-get update && sudo apt-get install -y git" ;;
    esac
    exit 2
  fi
  if ! has curl; then
    say "${red}${fail} curl not found.${reset}"
    case "$(uname -s)" in
      Darwin) say "Run: brew install curl" ;;
      Linux) say "Run: sudo apt-get update && sudo apt-get install -y curl" ;;
    esac
    exit 2
  fi
  if has docker && docker info >/dev/null 2>&1; then
    mode="docker"
  else
    mode="native"
  fi
}

confirm_plan() {
  local git_version docker_line uv_line install_kind action step_count
  git_version="$(git --version | awk '{print $3}')"
  if [ "$mode" = "docker" ]; then
    docker_line="${green}${ok}${reset} docker $(docker --version | awk '{print $3}' | tr -d ',') found, daemon running"
    install_kind="docker sandbox (recommended)"
    step_count=3
  else
    docker_line="${yellow}${warn}${reset} docker missing or daemon stopped ${arrow} native install via uv"
    install_kind="native"
    step_count=2
  fi
  if has uv; then
    uv_line="${green}${ok}${reset} uv found"
  else
    uv_line="${red}${fail}${reset} uv missing ${arrow} will install to ~/.local (no sudo)"
  fi
  action="install"
  if [ -d "$src/.git" ]; then
    action="update"
  fi
  say "${accent}Pilot Agent installer${reset}"
  say "${green}${ok}${reset} git ${git_version} found"
  say "$docker_line"
  say "$uv_line"
  say "${accent}${arrow}${reset} install mode: ${install_kind}"
  say "${accent}${arrow}${reset} ${action} mode: ${step_count} steps, ~2 min"
  if [ ! -t 0 ] || [ "$assume_yes" -eq 1 ]; then
    return
  fi
  printf 'Continue? [Y/n] '
  read -r answer
  case "$answer" in
    n|N|no|NO) exit 0 ;;
  esac
}

clone_or_update() {
  if [ -d "$src/.git" ]; then
    git -C "$src" pull --ff-only
    return
  fi
  if [ -e "$src" ]; then
    say "${red}${fail} ${src} exists but is not a git checkout. Move it aside and rerun install.sh.${reset}"
    exit 2
  fi
  local tmp
  tmp="${src}.tmp.$$"
  rm -rf "$tmp"
  git clone --depth 1 "$repo_url" "$tmp"
  mv "$tmp" "$src"
}

install_wrapper() {
  mkdir -p "$bin_dir"
  cat > "$bin_dir/pilot-agent" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec docker compose -f "$src/docker-compose.yml" run --rm \
  -v "\$PWD":/workspace \
  -e TERM="\${TERM:-xterm-256color}" \
  -e PILOT_AGENT_HOME=/home/agent/.pilot-agent \
  pilot-agent "\$@"
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

install_native() {
  install_uv_if_missing
  if uv tool list | grep -q '^pilot-agent '; then
    uv tool upgrade pilot-agent
  else
    uv tool install "git+$repo_url"
  fi
}

verify_path() {
  if ! command -v pilot-agent >/dev/null 2>&1 && [ ! -x "$bin_dir/pilot-agent" ]; then
    say "${yellow}${warn}${reset} Add this to your shell rc, then restart the terminal:"
    say "  export PATH=\"\$HOME/.local/bin:\$PATH\""
  fi
}

preflight
confirm_plan

if [ "$mode" = "docker" ]; then
  run_logged "Fetching Pilot Agent" clone_or_update
  run_logged "Building sandbox image" docker compose -f "$src/docker-compose.yml" build
  run_logged "Installing wrapper" install_wrapper
  verify_path
  "$bin_dir/pilot-agent" version >> "$log" 2>&1 || true
else
  run_logged "Installing uv" install_uv_if_missing
  run_logged "Installing Pilot Agent" install_native
  verify_path
fi

say "${green}${ok}${reset} Pilot Agent installed (${mode})"
say "Next:"
say "  cd <project-folder>"
say "  pilot-agent setup     # first-time setup (1 minute)"
say "  pilot-agent init && pilot-agent run"
say "Log: $log"
