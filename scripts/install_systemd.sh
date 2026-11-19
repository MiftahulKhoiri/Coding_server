#!/usr/bin/env bash
# Pasang CODING_SERVER sebagai systemd service (butuh sudo). Service berjalan sebagai user
# yang memanggil sudo (bukan root). Contoh: sudo ./scripts/install_systemd.sh
set -euo pipefail
source "$(dirname "$0")/common.sh"
if [ "$(id -u)" -ne 0 ]; then echo "Jalankan dengan sudo: sudo $0" >&2; exit 1; fi
RUN_USER="${CS_SERVICE_USER:-${SUDO_USER:-}}"
if [ -z "$RUN_USER" ] || [ "$RUN_USER" = "root" ]; then echo "Tentukan user non-root: CS_SERVICE_USER=nama sudo -E $0" >&2; exit 1; fi
RUN_GROUP="$(id -gn "$RUN_USER")"
RUN_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"
sed -e "s|@USER@|$RUN_USER|g" -e "s|@GROUP@|$RUN_GROUP|g" -e "s|@BASE@|$BASE|g" -e "s|@HOME@|$RUN_HOME|g" \
  "$BASE/deployment/systemd/coding-server.service.template" > /etc/systemd/system/coding-server.service
# Hentikan mode supervisor/cron bila ada
sudo -u "$RUN_USER" "$BASE/scripts/stop.sh" >/dev/null 2>&1 || true
sudo -u "$RUN_USER" bash -c "crontab -l 2>/dev/null | grep -v 'coding_server_autostart' | crontab -" || true
systemctl daemon-reload
systemctl enable --now coding-server
sleep 3
systemctl --no-pager status coding-server | head -5
c_ok "Service coding-server aktif, auto-start saat boot, berjalan sebagai $RUN_USER"
