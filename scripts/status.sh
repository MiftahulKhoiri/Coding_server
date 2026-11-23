#!/usr/bin/env bash
export CS_NO_MKDIR=1
source "$(dirname "$0")/common.sh"
echo "== CODING_SERVER =="
if systemd_installed; then
  echo "Mode: systemd ($(systemctl is-enabled $SERVICE 2>/dev/null), $(systemctl is-active $SERVICE 2>/dev/null))"
elif user_systemd_installed; then
  echo "Mode: systemd --user ($(systemctl --user is-enabled $SERVICE 2>/dev/null), $(systemctl --user is-active $SERVICE 2>/dev/null)), linger: $(linger_enabled && echo ya || echo TIDAK)"
elif [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Mode: supervisor, PID $(cat "$PID_FILE")"
else
  echo "Mode: tidak berjalan"
fi
[ -n "$(cron_lines_mine)" ] && echo "Autostart: cron @reboot aktif"
[ -x "$PY" ] || { c_err "Virtualenv tidak ada ($VENV) — belum terpasang atau sudah di-uninstall"; exit 1; }
"$PY" "$BASE/scripts/health_check.py" --url "http://127.0.0.1:$CS_PORT"
