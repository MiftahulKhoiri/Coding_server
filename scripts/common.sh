#!/usr/bin/env bash
# Variabel bersama untuk skrip CODING_SERVER.
BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$BASE/.venv"
PY="$VENV/bin/python"
ENV_FILE="$BASE/deployment/configuration/coding_server.env"
PID_FILE="$BASE/workspace/coding_server.pid"
# Catatan runtime yang dipasang install_runtimes.sh (dipakai uninstall.sh --remove-runtimes)
RUNTIME_MANIFEST="$BASE/deployment/configuration/.installed_runtimes"
# Penanda baris crontab mode autostart tanpa systemd
CRON_MARK="coding_server_autostart"
if [ -f "$ENV_FILE" ]; then set -a; . "$ENV_FILE"; set +a; fi
CS_HOST="${CS_HOST:-0.0.0.0}"
CS_PORT="${CS_PORT:-8800}"
# Nama service bisa diganti (mis. instalasi uji kedua di Pi yang sama)
SERVICE="${CS_SERVICE_NAME:-coding-server}"
export PATH="$HOME/.local/bin:$HOME/.dotnet:/usr/local/go/bin:$PATH"
# uninstall.sh men-set CS_NO_MKDIR=1 agar folder yang baru dihapus tidak dibuat ulang
[ "${CS_NO_MKDIR:-0}" = "1" ] || mkdir -p "$BASE/logs" "$BASE/workspace"

c_ok()   { printf '\033[32m[OK]\033[0m %s\n' "$*"; }
c_warn() { printf '\033[33m[!!]\033[0m %s\n' "$*"; }
c_err()  { printf '\033[31m[XX]\033[0m %s\n' "$*"; }
c_info() { printf '\033[36m[..]\033[0m %s\n' "$*"; }

USER_UNIT="$HOME/.config/systemd/user/$SERVICE.service"
SYSTEM_UNIT="/etc/systemd/system/$SERVICE.service"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
# Unit dianggap milik instalasi INI hanya bila ExecStart-nya menunjuk ke folder ini.
# (Mencegah stop/uninstall dari salinan lain mematikan service dengan nama yang sama.)
unit_is_mine() { [ -f "$1" ] && grep -qF "$BASE/scripts/run_server.sh" "$1"; }
unit_foreign() { [ -f "$1" ] && ! unit_is_mine "$1"; }
systemd_installed() { unit_is_mine "$SYSTEM_UNIT"; }
user_systemd_installed() { unit_is_mine "$USER_UNIT"; }
linger_enabled() { [ -f "/var/lib/systemd/linger/$(id -un)" ]; }
as_root() { if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo -n "$@"; fi; }
# Baris crontab autostart milik instalasi INI (marker + path BASE), bukan instalasi lain
cron_lines_mine() { crontab -l 2>/dev/null | awk -v m="$CRON_MARK" -v b="$BASE/" 'index($0,m) && index($0,b)'; }
cron_remove_mine() {
  crontab -l >/dev/null 2>&1 || return 0
  crontab -l 2>/dev/null | awk -v m="$CRON_MARK" -v b="$BASE/" '!(index($0,m) && index($0,b))' | crontab -
}
