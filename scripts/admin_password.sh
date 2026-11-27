#!/usr/bin/env bash
# Kelola sandi akun admin utama (root) — HANYA dari server.
#
# Akun admin utama tidak bisa diubah sandinya lewat aplikasi; ini akun pemulihan bila sandi
# akun lain terlupa. Sumber sandinya (urutan prioritas):
#   1. CS_ADMIN_PASSWORD di deployment/configuration/coding_server.env
#   2. workspace/metadata/initial_admin_password.txt
# Setiap server start, sandi root disinkronkan ke sumber tersebut.
#
# Pemakaian:
#   scripts/admin_password.sh            tampilkan username & sandi admin utama
#   scripts/admin_password.sh --set      minta sandi baru (diketik, tidak tampil), lalu terapkan
#   scripts/admin_password.sh --random   buat sandi acak baru, lalu terapkan
set -euo pipefail
source "$(dirname "$0")/common.sh"
[ -x "$PY" ] || { c_err "Virtualenv tidak ada ($VENV)"; exit 1; }

mode="${1:-show}"
new=""
case "$mode" in
  show|--show) ;;
  --set)
    read -rsp "Sandi baru admin utama (min 8 karakter): " new; echo
    read -rsp "Ulangi sandi: " again; echo
    [ "$new" = "$again" ] || { c_err "Sandi tidak sama"; exit 1; }
    ;;
  --random) new="$("$PY" -c 'import secrets;print(secrets.token_urlsafe(12))')" ;;
  -h|--help) sed -n 2,14p "$0"; exit 0 ;;
  *) c_err "Opsi tidak dikenal: $mode (pakai --set, --random, atau tanpa opsi)"; exit 1 ;;
esac

if [ -n "$new" ] && [ -n "${CS_ADMIN_PASSWORD:-}" ]; then
  c_warn "CS_ADMIN_PASSWORD diisi di $ENV_FILE dan selalu diutamakan."
  c_warn "Ubah nilai CS_ADMIN_PASSWORD di file itu lalu jalankan: scripts/restart.sh"
  exit 1
fi

cd "$BASE"
NEW_PASSWORD="$new" "$PY" - <<'PY'
import os, sys
from backend.config import build_settings
from backend.database.db import Database
from backend.services.auth_service import AuthService

s = build_settings()
auth = AuthService(s, Database(s.metadata_dir / "coding_server.db"))
new = os.environ.get("NEW_PASSWORD", "")
if new:
    if len(new) < 8:
        sys.exit("[XX] Sandi minimal 8 karakter")
    root = auth.root() or auth.ensure_root()
    auth._write_root_file(root["username"], new)
    root = auth.ensure_root()  # sinkronkan hash di database ke sandi baru
    print(f"[OK] Sandi admin utama '{root['username']}' diganti.")
    print(f"     username: {root['username']}\n     password: {new}")
    print("     Sesi yang sudah login tetap berlaku sampai logout/kedaluwarsa.")
else:
    root = auth.ensure_root()
    pw = auth.stored_root_password()
    src = "CS_ADMIN_PASSWORD (coding_server.env)" if s.admin_password else str(auth._root_file())
    print(f"username: {root['username']}")
    print(f"password: {pw}" if pw else "password: (tidak tersimpan di server — jalankan dengan --set atau --random)")
    if pw:
        print(f"sumber  : {src}")
PY
