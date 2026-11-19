#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
echo "== CODING_SERVER =="
if systemd_installed; then
  echo "Mode: systemd ($(systemctl is-enabled $SERVICE 2>/dev/null), $(systemctl is-active $SERVICE 2>/dev/null))"
elif [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Mode: supervisor, PID $(cat "$PID_FILE")"
else
  echo "Mode: tidak berjalan"
fi
crontab -l 2>/dev/null | grep -q "Coding_server\|coding_server" && echo "Autostart: cron @reboot aktif"
"$PY" "$BASE/scripts/health_check.py" --url "http://127.0.0.1:$CS_PORT"
