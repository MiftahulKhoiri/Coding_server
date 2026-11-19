#!/usr/bin/env bash
# Instalasi CODING_SERVER di Raspberry Pi 5 (Raspberry Pi OS 64-bit).
set -uo pipefail
source "$(dirname "$0")/common.sh"
cd "$BASE"
echo "=== Instalasi CODING_SERVER ==="
[ "$(id -u)" -eq 0 ] && { c_err "Jangan jalankan install.sh sebagai root (pakai user biasa)."; exit 1; }

# 1. OS & arsitektur
[ "$(uname -s)" = "Linux" ] && c_ok "OS: $(. /etc/os-release && echo "$PRETTY_NAME")" || { c_err "Butuh Linux"; exit 1; }
ARCH=$(uname -m)
[ "$ARCH" = "aarch64" ] && c_ok "Arsitektur: ARM64 ($ARCH)" || c_warn "Arsitektur $ARCH (target utama ARM64)"
[ -r /proc/device-tree/model ] && c_info "Board: $(tr -d '\0' < /proc/device-tree/model)"

# 2. Python
command -v python3 >/dev/null || { c_err "python3 tidak ada: sudo apt install python3 python3-venv"; exit 1; }
PYV=$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' && c_ok "Python $PYV" || { c_err "Butuh Python >= 3.10"; exit 1; }

# 3. Dependensi sistem (hanya diperiksa; pemasangan apt butuh sudo)
MISSING=()
for c in git bwrap curl; do command -v $c >/dev/null && c_ok "$c tersedia" || { c_warn "$c belum ada"; MISSING+=($c); }; done
[ ${#MISSING[@]} -gt 0 ] && c_warn "Pasang dengan: sudo apt install ${MISSING[*]/bwrap/bubblewrap}"

# 4. Direktori & konfigurasi
mkdir -p workspace/{projects,database,metadata,history,data,cache} logs backups
chmod 700 workspace/metadata backups
if [ ! -f "$ENV_FILE" ]; then
  cp deployment/configuration/coding_server.env.example "$ENV_FILE"; chmod 600 "$ENV_FILE"
  c_ok "Konfigurasi dibuat: $ENV_FILE"
else
  c_ok "Konfigurasi sudah ada"
fi

# 5. Virtualenv & paket backend
if [ ! -x "$PY" ]; then python3 -m venv "$VENV" || { c_err "Gagal membuat venv (sudo apt install python3-venv)"; exit 1; }; fi
"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q -r requirements.txt && c_ok "Paket Python terpasang" || { c_err "pip install gagal"; exit 1; }

# 6. Runtime opsional tanpa sudo (.NET & PHP) bila belum ada
if [ "${CS_SKIP_RUNTIMES:-0}" != "1" ]; then
  "$BASE/scripts/install_runtimes.sh" || c_warn "Sebagian runtime opsional gagal dipasang (lihat di atas)"
fi

# 7. Uji engine (nyata)
echo "Status engine:"
"$PY" scripts/health_check.py --engines --url "" 2>/dev/null || true

# 8. Autostart
if systemd_installed; then
  c_ok "systemd service sudah terpasang"
elif sudo -n true 2>/dev/null; then
  sudo -n "$BASE/scripts/install_systemd.sh"
elif linger_enabled; then
  "$BASE/scripts/install_user_systemd.sh"
else
  ( crontab -l 2>/dev/null | grep -v coding_server_autostart; \
    echo "@reboot $BASE/scripts/start.sh >> $BASE/logs/autostart.log 2>&1 # coding_server_autostart" ) | crontab -
  c_warn "sudo tidak tersedia tanpa password: autostart memakai cron @reboot (supervisor, restart otomatis)."
  c_warn "Untuk systemd (disarankan): sudo $BASE/scripts/install_systemd.sh"
fi

# 9. Jalankan & health check
if user_systemd_installed || systemd_installed; then "$BASE/scripts/start.sh"; else "$BASE/scripts/restart.sh"; fi
if [ -f workspace/metadata/initial_admin_password.txt ]; then
  echo; c_info "Login awal (simpan lalu hapus file ini):"; cat workspace/metadata/initial_admin_password.txt
fi
