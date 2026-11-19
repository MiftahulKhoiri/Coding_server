#!/usr/bin/env bash
# Pasang CODING_SERVER sebagai systemd *user* service (tanpa sudo). Auto-start saat boot
# membutuhkan "linger" aktif untuk user ini (sudo loginctl enable-linger $USER, sekali saja).
set -euo pipefail
source "$(dirname "$0")/common.sh"
[ "$(id -u)" -eq 0 ] && { c_err "Jalankan sebagai user biasa"; exit 1; }
mkdir -p "$(dirname "$USER_UNIT")"
sed -e '/^User=/d' -e '/^Group=/d' -e "s|@BASE@|$BASE|g" -e "s|@HOME@|$HOME|g" \
    -e 's|WantedBy=multi-user.target|WantedBy=default.target|' \
    -e '/^ProtectSystem=/d' -e '/^ProtectControlGroups=/d' -e '/^ProtectKernelModules=/d' -e '/^PrivateTmp=/d' \
    "$BASE/deployment/systemd/coding-server.service.template" > "$USER_UNIT"
# Matikan mode supervisor/cron lama bila ada
if [ -f "$PID_FILE" ]; then
  pid=$(cat "$PID_FILE"); kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  sleep 2; rm -f "$PID_FILE"
fi
( crontab -l 2>/dev/null | grep -v coding_server_autostart ) | crontab - 2>/dev/null || true
systemctl --user daemon-reload
systemctl --user enable "$SERVICE" >/dev/null
systemctl --user restart "$SERVICE"
sleep 3
systemctl --user --no-pager status "$SERVICE" | head -4 || true
linger_enabled && c_ok "Linger aktif: service otomatis jalan saat boot" \
  || c_warn "Linger belum aktif. Jalankan sekali: sudo loginctl enable-linger $(id -un)"
