#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
if systemd_installed; then
  as_root systemctl start "$SERVICE" && c_ok "Service $SERVICE dijalankan (systemd)" || { c_err "Gagal: butuh sudo"; exit 1; }
else
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    c_warn "Server sudah berjalan (PID $(cat "$PID_FILE"))"; exit 0
  fi
  setsid nohup "$BASE/scripts/run_server.sh" >/dev/null 2>&1 < /dev/null &
  echo $! > "$PID_FILE"
  c_ok "Server dijalankan (mode supervisor, PID $!)"
fi
for i in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:$CS_PORT/api/v1/system/health" >/dev/null 2>&1; then
    c_ok "Health OK: http://$(hostname -I 2>/dev/null | awk '{print $1}'):$CS_PORT"; exit 0
  fi
  sleep 1
done
c_err "Server belum menjawab health check. Lihat $BASE/logs/service.log"; exit 1
