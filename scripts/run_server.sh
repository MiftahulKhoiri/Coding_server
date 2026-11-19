#!/usr/bin/env bash
# Menjalankan uvicorn. --foreground dipakai systemd; tanpa itu dipakai sebagai supervisor
# sederhana (restart otomatis bila crash) untuk mode tanpa systemd.
source "$(dirname "$0")/common.sh"
cd "$BASE"
if [ "$(id -u)" -eq 0 ]; then echo "Jangan jalankan CODING_SERVER sebagai root" >&2; exit 1; fi
run() {
  exec "$PY" -m uvicorn backend.main:app --host "$CS_HOST" --port "$CS_PORT" \
    --no-access-log --ws websockets --timeout-graceful-shutdown 10
}
if [ "${1:-}" = "--foreground" ]; then run; fi
# Mode supervisor
trap 'kill $child 2>/dev/null; exit 0' TERM INT
while true; do
  "$PY" -m uvicorn backend.main:app --host "$CS_HOST" --port "$CS_PORT" --no-access-log --ws websockets \
    --timeout-graceful-shutdown 10 >> "$BASE/logs/service.log" 2>&1 &
  child=$!
  wait $child
  code=$?
  echo "$(date '+%F %T') server berhenti (exit $code), restart dalam 5 detik" >> "$BASE/logs/service.log"
  sleep 5
done
