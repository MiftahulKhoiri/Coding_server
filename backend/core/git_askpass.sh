#!/bin/sh
# Dipanggil git untuk meminta kredensial. Nilai diambil dari environment (tidak pernah di argumen/log).
case "$1" in
  Username*) printf '%s\n' "$CS_GIT_USERNAME" ;;
  *) printf '%s\n' "$CS_GIT_PASSWORD" ;;
esac
