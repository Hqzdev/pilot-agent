#!/usr/bin/env bash
# ============================================================================
# Pilot Agent Installer
# ============================================================================
# Installation script for Linux, macOS, and WSL2.
#
# What it writes:
#   - source checkout: ~/.pilot-agent-src
#   - command wrapper: ~/.local/bin/pilot-agent when using Docker mode
#   - user config/data: ~/.pilot-agent
#   - install log: /tmp/pilot-agent-install-<timestamp>.log
#
# It never uses sudo. User-space dependencies such as uv may be installed under
# ~/.local. System dependencies such as Docker, git, or curl are reported with
# an exact fix command and left to the user.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Hqzdev/pilot-agent/main/install.sh | bash
#
# Or with options:
#   curl -fsSL ... | bash -s -- --skip-setup --native
# ============================================================================

set -euo pipefail

if [ -n "${PYTHONPATH:-}" ]; then
  echo "Ignoring inherited PYTHONPATH during install to avoid module shadowing"
  unset PYTHONPATH
fi
if [ -n "${PYTHONHOME:-}" ]; then
  echo "Ignoring inherited PYTHONHOME during install"
  unset PYTHONHOME
fi

export UV_NO_CONFIG=1

REPO_URL="${PILOT_AGENT_REPO_URL:-https://github.com/Hqzdev/pilot-agent.git}"
BRANCH="main"
INSTALL_COMMIT=""
PILOT_HOME="${PILOT_AGENT_HOME:-$HOME/.pilot-agent}"
SRC="${PILOT_AGENT_SRC:-$HOME/.pilot-agent-src}"
SRC_EXPLICIT=false
BIN_DIR="${PILOT_AGENT_BIN_DIR:-$HOME/.local/bin}"
LOG="${TMPDIR:-/tmp}/pilot-agent-install-$(date +%Y%m%d%H%M%S).log"

ASSUME_YES=false
VERBOSE="${PILOT_AGENT_INSTALL_VERBOSE:-0}"
RUN_SETUP=true
FORCE_MODE="auto"
MODE="native"
OS="unknown"
DISTRO="unknown"
HAS_DOCKER=false
HAS_UV=false
UV_CMD=""

STEP_INDEX=0
STEP_TOTAL=0
STEP_TITLE="preflight"

if [ -t 0 ]; then
  IS_INTERACTIVE=true
else
  IS_INTERACTIVE=false
fi

if [ "${PILOT_AGENT_INSTALL_NO_SETUP:-0}" = "1" ]; then
  RUN_SETUP=false
fi

while [ "$#" -gt 0 ]; do
  case "$1" in
    -y|--yes)
      ASSUME_YES=true
      shift
      ;;
    -v|--verbose)
      VERBOSE=1
      shift
      ;;
    --no-setup|--skip-setup)
      RUN_SETUP=false
      shift
      ;;
    --native)
      FORCE_MODE="native"
      shift
      ;;
    --docker)
      FORCE_MODE="docker"
      shift
      ;;
    --branch|-b)
      BRANCH="${2:-}"
      if [ -z "$BRANCH" ]; then
        echo "--branch requires a value"
        exit 2
      fi
      shift 2
      ;;
    --commit)
      INSTALL_COMMIT="${2:-}"
      if [ -z "$INSTALL_COMMIT" ]; then
        echo "--commit requires a value"
        exit 2
      fi
      shift 2
      ;;
    --dir)
      SRC="${2:-}"
      if [ -z "$SRC" ]; then
        echo "--dir requires a value"
        exit 2
      fi
      SRC_EXPLICIT=true
      shift 2
      ;;
    --pilot-home)
      PILOT_HOME="${2:-}"
      if [ -z "$PILOT_HOME" ]; then
        echo "--pilot-home requires a value"
        exit 2
      fi
      shift 2
      ;;
    -h|--help)
      cat <<EOF
Pilot Agent Installer

Usage: install.sh [OPTIONS]

Options:
  -y, --yes          Accept the install plan without prompting.
  -v, --verbose      Stream command output to the terminal as well as the log.
  --skip-setup       Install only; do not start the setup wizard.
  --no-setup         Alias for --skip-setup.
  --native           Force native uv tool install.
  --docker           Force Docker sandbox install. Fails if Docker is unavailable.
  --branch NAME      Git branch to install for Docker mode and native git install.
  --commit SHA       Pin checkout/install to a specific commit.
  --dir PATH         Source checkout directory (default: ~/.pilot-agent-src).
  --pilot-home PATH  Config/data directory (default: ~/.pilot-agent).
  -h, --help         Show this help.

Environment:
  PILOT_AGENT_REPO_URL            Override the repository URL.
  PILOT_AGENT_SRC                 Override source checkout directory.
  PILOT_AGENT_BIN_DIR             Override command wrapper directory.
  PILOT_AGENT_HOME                Override config/data directory.
  PILOT_AGENT_INSTALL_NO_SETUP=1  Skip setup wizard.
  PILOT_AGENT_INSTALL_VERBOSE=1   Stream command output.
  NO_COLOR=1                      Disable ANSI color.
EOF
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      exit 2
      ;;
  esac
done

mkdir -p "$(dirname "$LOG")"
: > "$LOG"

USE_COLOR=false
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ] && command -v tput >/dev/null 2>&1 && [ "${TERM:-dumb}" != "dumb" ]; then
  USE_COLOR=true
fi

if [ "$USE_COLOR" = true ]; then
  RED="$(tput setaf 1)"
  GREEN="$(tput setaf 2)"
  YELLOW="$(tput setaf 3)"
  CYAN="$(tput setaf 6)"
  MAGENTA="$(tput setaf 5)"
  BOLD="$(tput bold)"
  DIM="$(tput dim)"
  NC="$(tput sgr0)"
else
  RED=""
  GREEN=""
  YELLOW=""
  CYAN=""
  MAGENTA=""
  BOLD=""
  DIM=""
  NC=""
fi

case "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in
  *UTF-8*|*utf8*)
    OK="✓"
    FAIL="✗"
    WARN="⚠"
    ARROW="→"
    BOX_TOP="┌─────────────────────────────────────────────────────────┐"
    BOX_MID="├─────────────────────────────────────────────────────────┤"
    BOX_BOT="└─────────────────────────────────────────────────────────┘"
    ;;
  *)
    OK="+"
    FAIL="x"
    WARN="!"
    ARROW="->"
    BOX_TOP="+---------------------------------------------------------+"
    BOX_MID="+---------------------------------------------------------+"
    BOX_BOT="+---------------------------------------------------------+"
    ;;
esac

say() {
  printf '%b\n' "$*"
}

log_info() {
  say "${CYAN}${ARROW}${NC} $*"
}

log_success() {
  say "${GREEN}${OK}${NC} $*"
}

log_warn() {
  say "${YELLOW}${WARN}${NC} $*"
}

log_error() {
  say "${RED}${FAIL}${NC} $*"
}

has() {
  command -v "$1" >/dev/null 2>&1
}

print_banner() {
  say ""
  say "${MAGENTA}${BOLD}${BOX_TOP}"
  if [ "$OK" = "✓" ]; then
    say "│              Pilot Agent Installer                      │"
    say "${BOX_MID}"
    say "│  CLI agent: idea to deployed MVP in one session.        │"
  else
    say "|              Pilot Agent Installer                      |"
    say "$BOX_MID"
    say "|  CLI agent: idea to deployed MVP in one session.        |"
  fi
  say "${BOX_BOT}${NC}"
  say ""
}

prompt_yes_no() {
  local question="$1"
  local default="${2:-yes}"
  local suffix="[Y/n]"
  local answer=""

  case "$default" in
    n|N|no|NO|false|0) suffix="[y/N]" ;;
  esac

  if [ "$ASSUME_YES" = true ]; then
    answer=""
  elif [ "$IS_INTERACTIVE" = true ]; then
    read -r -p "$question $suffix " answer || answer=""
  elif (: </dev/tty) 2>/dev/null; then
    printf "%s %s " "$question" "$suffix" > /dev/tty
    IFS= read -r answer < /dev/tty || answer=""
  else
    answer=""
  fi

  answer="${answer#"${answer%%[![:space:]]*}"}"
  answer="${answer%"${answer##*[![:space:]]}"}"

  if [ -z "$answer" ]; then
    case "$default" in
      n|N|no|NO|false|0) return 1 ;;
      *) return 0 ;;
    esac
  fi

  case "$answer" in
    y|Y|yes|YES|Yes) return 0 ;;
    *) return 1 ;;
  esac
}

manual_install_hint() {
  local pkg="$1"
  case "$OS:$DISTRO:$pkg" in
    macos:*:git) echo "brew install git" ;;
    macos:*:curl) echo "brew install curl" ;;
    macos:*:docker) echo "Install Docker Desktop: https://docs.docker.com/desktop/setup/install/mac-install/" ;;
    linux:ubuntu:git|linux:debian:git) echo "sudo apt-get update && sudo apt-get install -y git" ;;
    linux:ubuntu:curl|linux:debian:curl) echo "sudo apt-get update && sudo apt-get install -y curl" ;;
    linux:ubuntu:docker|linux:debian:docker) echo "sudo apt-get update && sudo apt-get install -y docker.io docker-compose-plugin" ;;
    linux:fedora:git) echo "sudo dnf install -y git" ;;
    linux:fedora:curl) echo "sudo dnf install -y curl" ;;
    linux:fedora:docker) echo "sudo dnf install -y docker docker-compose-plugin" ;;
    linux:arch:git) echo "sudo pacman -S git" ;;
    linux:arch:curl) echo "sudo pacman -S curl" ;;
    linux:arch:docker) echo "sudo pacman -S docker docker-compose" ;;
    *:docker) echo "Install Docker Desktop: https://docs.docker.com/get-docker/" ;;
    *:git) echo "Install git with your package manager" ;;
    *:curl) echo "Install curl with your package manager" ;;
    *) echo "Install $pkg with your package manager" ;;
  esac
}

fix_for_step() {
  case "$STEP_TITLE" in
    "Checking prerequisites")
      echo "Install the missing prerequisite above, then rerun: bash install.sh"
      ;;
    "Fetching Pilot Agent")
      echo "Check network access to github.com, then rerun: bash install.sh"
      ;;
    "Installing uv")
      echo "Check curl/network access to https://astral.sh/uv, then rerun: bash install.sh"
      ;;
    "Installing Pilot Agent")
      echo "Check PyPI/GitHub network access, then rerun: bash install.sh --native"
      ;;
    "Building sandbox image")
      echo "Start Docker, then rerun: bash install.sh --docker"
      ;;
    "Installing command")
      echo "Check write access to $BIN_DIR, then rerun: bash install.sh"
      ;;
    *)
      echo "Rerun anytime: bash install.sh"
      ;;
  esac
}

on_error() {
  local rc=$?
  say ""
  log_error "failed at step [$STEP_INDEX/$STEP_TOTAL] $STEP_TITLE, see log: $LOG"
  tail -n 5 "$LOG" 2>/dev/null || true
  say "$(fix_for_step)"
  exit "$rc"
}

on_interrupt() {
  say ""
  log_warn "installation cancelled, nothing broken - re-run anytime"
  exit 130
}

trap on_error ERR
trap on_interrupt INT

run_step() {
  STEP_INDEX=$((STEP_INDEX + 1))
  STEP_TITLE="$1"
  shift

  local start
  local elapsed
  local rc
  start="$(date +%s)"

  if [ "$VERBOSE" = "1" ]; then
    say "${DIM}[$STEP_INDEX/$STEP_TOTAL] $STEP_TITLE ...${NC}"
    set +e
    "$@" 2>&1 | tee -a "$LOG"
    rc=$?
    set -e
  else
    printf '%b' "${DIM}[$STEP_INDEX/$STEP_TOTAL] $STEP_TITLE ...${NC} "
    set +e
    "$@" >> "$LOG" 2>&1
    rc=$?
    set -e
  fi

  elapsed=$(( $(date +%s) - start ))
  if [ "$rc" -eq 0 ]; then
    if [ "$VERBOSE" = "1" ]; then
      log_success "$STEP_TITLE ${DIM}${elapsed}s${NC}"
    else
      say "${GREEN}${OK}${NC} ${DIM}${elapsed}s${NC}"
    fi
    return 0
  fi

  return "$rc"
}

detect_os() {
  case "$(uname -s)" in
    Linux*)
      OS="linux"
      if [ -f /etc/os-release ]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        DISTRO="${ID:-unknown}"
      else
        DISTRO="unknown"
      fi
      ;;
    Darwin*)
      OS="macos"
      DISTRO="macos"
      ;;
    CYGWIN*|MINGW*|MSYS*)
      log_error "Windows detected. Use WSL2 and run the Linux install command there."
      exit 2
      ;;
    *)
      log_error "Unsupported platform: $(uname -s). Use Linux, macOS, or WSL2."
      exit 2
      ;;
  esac
}

check_prerequisites() {
  if ! has git; then
    log_error "git not found. Run: $(manual_install_hint git)"
    exit 2
  fi
  if ! has curl; then
    log_error "curl not found. Run: $(manual_install_hint curl)"
    exit 2
  fi

  if curl -fsSI --max-time 8 https://github.com/ >/dev/null 2>&1; then
    log_success "Network check: github.com reachable"
  else
    log_warn "Could not reach github.com during preflight; install may fail behind proxy/firewall."
  fi
}

detect_uv() {
  if has uv; then
    UV_CMD="$(command -v uv)"
    HAS_UV=true
  elif [ -x "$HOME/.local/bin/uv" ]; then
    UV_CMD="$HOME/.local/bin/uv"
    HAS_UV=true
  else
    UV_CMD="$HOME/.local/bin/uv"
    HAS_UV=false
  fi
}

detect_install_mode() {
  detect_uv
  if has docker && docker info >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    HAS_DOCKER=true
  else
    HAS_DOCKER=false
  fi

  case "$FORCE_MODE" in
    docker)
      if [ "$HAS_DOCKER" != true ]; then
        log_error "Docker mode requested, but Docker daemon or docker compose is unavailable."
        say "Run: $(manual_install_hint docker)"
        exit 2
      fi
      MODE="docker"
      ;;
    native)
      MODE="native"
      ;;
    *)
      if [ "$HAS_DOCKER" = true ]; then
        MODE="docker"
      else
        MODE="native"
      fi
      ;;
  esac
}

print_plan() {
  local git_version
  local docker_line
  local uv_line
  local mode_line
  local action
  local setup_line
  local step_count

  git_version="$(git --version | awk '{print $3}')"
  action="install"
  if [ "$MODE" = "docker" ] && [ -d "$SRC/.git" ]; then
    action="update"
  elif [ "$MODE" = "native" ] && [ "$HAS_UV" = true ] && "$UV_CMD" tool list 2>/dev/null | grep -q '^pilot-agent '; then
    action="update"
  fi

  if [ "$HAS_DOCKER" = true ]; then
    docker_line="${GREEN}${OK}${NC} docker $(docker --version | awk '{print $3}' | tr -d ',') found, daemon running"
  else
    docker_line="${YELLOW}${WARN}${NC} docker missing or daemon stopped ${ARROW} native install via uv"
  fi

  if [ "$HAS_UV" = true ]; then
    uv_line="${GREEN}${OK}${NC} uv found ($("$UV_CMD" --version 2>/dev/null | awk '{print $2}'))"
  else
    uv_line="${YELLOW}${WARN}${NC} uv missing ${ARROW} will install to ~/.local/bin (no sudo)"
  fi

  if [ "$MODE" = "docker" ]; then
    mode_line="docker sandbox (recommended)"
    step_count=3
  elif [ "$HAS_UV" = true ]; then
    mode_line="native uv tool"
    step_count=2
  else
    mode_line="native uv tool"
    step_count=3
  fi

  if [ "$RUN_SETUP" = true ]; then
    setup_line="${ARROW} setup wizard: starts automatically after install when a terminal is available"
  else
    setup_line="${ARROW} setup wizard: skipped by option"
  fi

  say "${CYAN}${BOLD}Pilot Agent installer${NC}"
  say "${GREEN}${OK}${NC} detected: $OS ($DISTRO)"
  say "${GREEN}${OK}${NC} git $git_version found"
  say "$docker_line"
  say "$uv_line"
  say "${CYAN}${ARROW}${NC} install mode: $mode_line"
  say "${CYAN}${ARROW}${NC} ${action} mode: $step_count steps, ~2 min"
  say "${CYAN}${setup_line}${NC}"
  say "${DIM}Log: $LOG${NC}"

  if ! prompt_yes_no "Continue?" "yes"; then
    exit 0
  fi
}

clone_or_update() {
  if [ -d "$SRC/.git" ]; then
    git -C "$SRC" remote set-url origin "$REPO_URL" >/dev/null 2>&1 || true
    git -C "$SRC" remote set-branches origin "$BRANCH" >/dev/null 2>&1 || true
    git -C "$SRC" fetch origin "$BRANCH"
    git -C "$SRC" checkout "$BRANCH"
    git -C "$SRC" pull --ff-only origin "$BRANCH"
  elif [ -e "$SRC" ]; then
    log_error "$SRC exists but is not a git checkout. Move it aside or pass --dir PATH."
    exit 2
  else
    local tmp
    tmp="${SRC}.tmp.$$"
    rm -rf "$tmp"
    git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$tmp"
    mv "$tmp" "$SRC"
  fi

  if [ -n "$INSTALL_COMMIT" ]; then
    if ! git -C "$SRC" cat-file -e "$INSTALL_COMMIT^{commit}" 2>/dev/null; then
      git -C "$SRC" fetch origin "$INSTALL_COMMIT" || true
    fi
    git -C "$SRC" checkout --detach "$INSTALL_COMMIT"
  fi
}

install_uv() {
  detect_uv
  if [ "$HAS_UV" = true ]; then
    return 0
  fi

  mkdir -p "$HOME/.local/bin"
  local installer
  installer="$(mktemp 2>/dev/null || echo "/tmp/pilot-agent-uv-installer.$$.sh")"
  curl -LsSf https://astral.sh/uv/install.sh -o "$installer"
  UV_UNMANAGED_INSTALL="$HOME/.local/bin" sh "$installer"
  rm -f "$installer"
  export PATH="$HOME/.local/bin:$PATH"
  detect_uv

  if [ "$HAS_UV" != true ]; then
    log_error "uv installer finished but uv was not found at $UV_CMD."
    exit 1
  fi
}

native_install_spec() {
  if [ -n "$INSTALL_COMMIT" ]; then
    printf 'git+%s@%s\n' "$REPO_URL" "$INSTALL_COMMIT"
  elif [ "$BRANCH" != "main" ]; then
    printf 'git+%s@%s\n' "$REPO_URL" "$BRANCH"
  else
    printf 'git+%s\n' "$REPO_URL"
  fi
}

install_native() {
  install_uv
  "$UV_CMD" tool install --force "$(native_install_spec)"
}

build_docker_image() {
  docker compose -f "$SRC/docker-compose.yml" build
}

install_command_wrapper() {
  mkdir -p "$BIN_DIR"
  cat > "$BIN_DIR/pilot-agent" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec docker compose -f "$SRC/docker-compose.yml" run --rm \\
  -v "\$PWD":/workspace \\
  -e TERM="\${TERM:-xterm-256color}" \\
  -e PILOT_AGENT_HOME=/home/agent/.pilot-agent \\
  pilot-agent "\$@"
EOF
  chmod +x "$BIN_DIR/pilot-agent"
}

pilot_agent_cmd() {
  if [ -x "$BIN_DIR/pilot-agent" ]; then
    printf '%s\n' "$BIN_DIR/pilot-agent"
    return 0
  fi
  if command -v pilot-agent >/dev/null 2>&1; then
    command -v pilot-agent
    return 0
  fi
  return 1
}

verify_command() {
  if pilot_agent_cmd >/dev/null 2>&1; then
    return 0
  fi

  log_warn "pilot-agent is installed, but $BIN_DIR is not on PATH yet."
  say "Add this to your shell rc, then restart the terminal:"
  say "  export PATH=\"\$HOME/.local/bin:\$PATH\""
}

run_setup_wizard() {
  if [ "$RUN_SETUP" != true ]; then
    log_warn "Setup skipped. Run: pilot-agent setup"
    return 0
  fi

  if ! (: </dev/tty) 2>/dev/null; then
    log_warn "Setup wizard skipped (no interactive terminal). Run: pilot-agent setup"
    return 0
  fi

  local cmd
  if ! cmd="$(pilot_agent_cmd)"; then
    log_warn "Setup wizard skipped because pilot-agent is not on PATH yet."
    say "Run after updating PATH: pilot-agent setup"
    return 0
  fi

  say ""
  log_info "Starting setup wizard..."
  say ""

  set +e
  "$cmd" setup --reconfigure < /dev/tty
  local rc=$?
  set -e

  if [ "$rc" -ne 0 ]; then
    log_warn "Setup wizard did not complete. Run: pilot-agent setup --reconfigure"
  fi
}

print_success() {
  say ""
  say "${GREEN}${BOLD}${BOX_TOP}"
  if [ "$OK" = "✓" ]; then
    say "│              ✓ Installation Complete!                   │"
  else
    say "|              + Installation Complete!                   |"
  fi
  say "${BOX_BOT}${NC}"
  say ""
  say "${CYAN}${BOLD}Your files:${NC}"
  if [ "$MODE" = "docker" ]; then
    say "  Config:       Docker volume pilot-agent-home:/home/agent/.pilot-agent/config.yaml"
    say "  API keys:     Docker volume pilot-agent-home:/home/agent/.pilot-agent/credentials.yaml"
    say "  Data:         Docker volume pilot-agent-home"
    say "  Code:         $SRC"
    say "  Command:      $BIN_DIR/pilot-agent"
  else
    say "  Config:       $PILOT_HOME/config.yaml"
    say "  API keys:     $PILOT_HOME/credentials.yaml"
    say "  Data:         $PILOT_HOME"
    say "  Command:      pilot-agent (uv tool)"
  fi
  say "  Log:          $LOG"
  say ""
  say "${CYAN}${BOLD}Commands:${NC}"
  say "  pilot-agent setup          Configure keys, provider, model, Vercel"
  say "  pilot-agent doctor         Diagnose config, credentials, tools"
  say "  pilot-agent update         Update Pilot Agent"
  say "  pilot-agent delete --all   Remove Pilot Agent files (Docker itself is untouched)"
  say ""
  say "${CYAN}${BOLD}Next:${NC}"
  say "  cd <project-folder>"
  say "  pilot-agent init && pilot-agent run"
  say ""

  if ! echo ":$PATH:" | grep -q ":$BIN_DIR:"; then
    log_warn "$BIN_DIR is not on PATH in this shell."
    say "Add it with: export PATH=\"\$HOME/.local/bin:\$PATH\""
  fi
}

main() {
  print_banner

  STEP_TITLE="Checking prerequisites"
  detect_os
  log_success "Detected: $OS ($DISTRO)"
  check_prerequisites
  detect_install_mode
  print_plan

  STEP_INDEX=0
  if [ "$MODE" = "docker" ]; then
    STEP_TOTAL=3
    run_step "Fetching Pilot Agent" clone_or_update
    run_step "Building sandbox image" build_docker_image
    run_step "Installing command" install_command_wrapper
  else
    if [ "$HAS_UV" = true ]; then
      STEP_TOTAL=2
    else
      STEP_TOTAL=3
      run_step "Installing uv" install_uv
    fi
    run_step "Installing Pilot Agent" install_native
    run_step "Checking command" verify_command
  fi

  verify_command
  run_setup_wizard
  print_success
}

main
