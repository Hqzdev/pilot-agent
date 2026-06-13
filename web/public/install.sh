#!/usr/bin/env bash
set -euo pipefail

INSTALL_URL="https://raw.githubusercontent.com/Hqzdev/pilot-agent/main/install.sh"

if command -v curl >/dev/null 2>&1; then
  curl -fsSL "$INSTALL_URL" | bash -s -- "$@"
elif command -v wget >/dev/null 2>&1; then
  wget -qO- "$INSTALL_URL" | bash -s -- "$@"
else
  echo "pilot-agent installer requires curl or wget." >&2
  exit 1
fi
