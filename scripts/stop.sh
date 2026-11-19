#!/usr/bin/env bash
source "$(dirname "$0")/common.sh"
if systemd_installed; then
  as_root systemctl stop "$SERVICE" && c_ok "Service $SERVICE dihentikan"
fi
if user_systemd_installed; then
  systemctl --user stop "$SERVICE" && c_ok "Service $SERVICE dihentikan (systemd --user)"
fi
if [ -f "$PID_FILE" ]; then
  pid=$(cat "$PID_FILE")
  if kill -0 "$pid" 2>/dev/null; then
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid"
    for i in $(seq 1 15); do kill -0 "$pid" 2>/dev/null || break; sleep 1; done
    kill -KILL -- "-$pid" 2>/dev/null || true
    c_ok "Server (PID $pid) dihentikan"
  fi
  rm -f "$PID_FILE"
fi
