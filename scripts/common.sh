#!/usr/bin/env bash
# Variabel bersama untuk skrip CODING_SERVER.
BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$BASE/.venv"
PY="$VENV/bin/python"
ENV_FILE="$BASE/deployment/configuration/coding_server.env"
PID_FILE="$BASE/workspace/coding_server.pid"
SERVICE=coding-server
if [ -f "$ENV_FILE" ]; then set -a; . "$ENV_FILE"; set +a; fi
CS_HOST="${CS_HOST:-0.0.0.0}"
CS_PORT="${CS_PORT:-8800}"
export PATH="$HOME/.local/bin:$HOME/.dotnet:/usr/local/go/bin:$PATH"
mkdir -p "$BASE/logs" "$BASE/workspace"

c_ok()   { printf '\033[32m[OK]\033[0m %s\n' "$*"; }
c_warn() { printf '\033[33m[!!]\033[0m %s\n' "$*"; }
c_err()  { printf '\033[31m[XX]\033[0m %s\n' "$*"; }
c_info() { printf '\033[36m[..]\033[0m %s\n' "$*"; }

USER_UNIT="$HOME/.config/systemd/user/$SERVICE.service"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
systemd_installed() { [ -f "/etc/systemd/system/$SERVICE.service" ]; }
user_systemd_installed() { [ -f "$USER_UNIT" ]; }
linger_enabled() { [ -f "/var/lib/systemd/linger/$(id -un)" ]; }
as_root() { if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo -n "$@"; fi; }
