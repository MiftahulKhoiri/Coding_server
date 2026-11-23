#!/usr/bin/env bash
# Uninstall CODING_SERVER dari Raspberry Pi dan bersihkan sisa-sisanya.
#
#   ./scripts/uninstall.sh                 hapus aplikasi, data DIPERTAHANKAN (ditanya bila interaktif)
#   ./scripts/uninstall.sh --purge -y      hapus aplikasi + semua data (backup akhir dibuat dulu)
#   ./scripts/uninstall.sh --dry-run       tampilkan apa yang akan dihapus, tanpa menghapus
#
# Selalu dihapus : service systemd (system/user), autostart cron, proses server & sandbox,
#                  .venv, logs/, cache build, PID, __pycache__, node_modules web_editor.
# --purge        : + workspace/ (proyek, database, metadata, riwayat, token Git terenkripsi),
#                  backups/, dan konfigurasi coding_server.env.
# Tidak pernah disentuh: linger systemd (bisa dipakai service lain), paket apt (gcc, java, go, ...),
#                  aplikasi Android di HP (hapus manual dari HP).
set -uo pipefail

usage() {
  cat <<'EOF'
Pemakaian: ./scripts/uninstall.sh [opsi]

  --purge             Hapus juga DATA: workspace/ (semua proyek & database), backups/, konfigurasi .env
  --keep-data         Pertahankan data tanpa bertanya (kebalikan --purge)
  --no-final-backup   Jangan buat arsip backup akhir sebelum --purge menghapus data
  --backup-dir DIR    Lokasi arsip backup akhir (default: $HOME)
  --remove-runtimes   Hapus juga .NET (~/.dotnet) & PHP statis (~/.local/opt/php) yang dipasang install_runtimes.sh
  --remove-repo       Hapus seluruh folder repo setelah selesai (otomatis --purge)
  -y, --yes           Jangan minta konfirmasi
  -n, --dry-run       Hanya tampilkan langkah, tidak menghapus apa pun
  -h, --help          Tampilkan bantuan ini
EOF
}

PURGE=""; FINAL_BACKUP=1; BACKUP_DIR="$HOME"; REMOVE_RUNTIMES=0; REMOVE_REPO=0; YES=0; DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --purge) PURGE=1 ;;
    --keep-data) PURGE=0 ;;
    --no-final-backup) FINAL_BACKUP=0 ;;
    --backup-dir) shift; BACKUP_DIR="${1:?--backup-dir butuh nilai}" ;;
    --remove-runtimes) REMOVE_RUNTIMES=1 ;;
    --remove-repo) REMOVE_REPO=1; PURGE=1 ;;
    -y|--yes) YES=1 ;;
    -n|--dry-run) DRY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Opsi tidak dikenal: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

export CS_NO_MKDIR=1
source "$(dirname "$0")/common.sh"

FAILED=()
run() { if [ "$DRY" = 1 ]; then echo "    [dry-run] $*"; else "$@"; fi; }
# Seperti run, tapi keluaran perintah asli dibuang (keluaran dry-run tetap tampil)
runq() { if [ "$DRY" = 1 ]; then echo "    [dry-run] $*"; else "$@" >/dev/null 2>&1; fi; }
fail() { c_err "$*"; FAILED+=("$*"); }
is_tty() { [ -t 0 ] && [ -t 1 ]; }
confirm() {  # confirm "pertanyaan" -> 0 bila ya
  [ "$YES" = 1 ] && return 0
  is_tty || return 1
  local a; read -r -p "$1 [y/N] " a; [[ "$a" =~ ^[yYoO] ]]
}
# Jalankan perintah root: sudo tanpa password, atau sudo interaktif bila ada terminal
root_do() {
  if [ "$(id -u)" -eq 0 ]; then "$@"
  elif sudo -n true 2>/dev/null; then sudo -n "$@"
  elif is_tty; then sudo "$@"
  else return 1; fi
}

# Penghapusan aman: hanya path di dalam BASE (atau path runtime yang diizinkan), tidak pernah BASE/HOME/'/'
safe_rm() {
  local p="$1" real
  [ -e "$p" ] || [ -L "$p" ] || return 0
  real="$(readlink -f -- "$p" 2>/dev/null || echo "$p")"
  case "$real" in
    ""|/|"$HOME"|"$BASE") fail "Menolak menghapus path berbahaya: $p"; return 1 ;;
  esac
  local allowed=0
  case "$real" in "$BASE"/*) allowed=1 ;; esac
  # symlink di dalam BASE yang menunjuk ke luar: hapus link-nya saja
  if [ "$allowed" = 0 ] && [ -L "$p" ]; then case "$p" in "$BASE"/*) run rm -f -- "$p"; return ;; esac; fi
  for extra in "${SAFE_EXTRA[@]:-}"; do [ -n "$extra" ] && [ "$real" = "$extra" ] && allowed=1; done
  [ "$allowed" = 1 ] || { fail "Di luar folder instalasi, dilewati: $p"; return 1; }
  run rm -rf -- "$p" && { [ "$DRY" = 1 ] || c_ok "Dihapus: ${p/#$HOME/~}"; }
}
SAFE_EXTRA=()

main() {
  # --- Pemeriksaan keamanan dasar ---
  [ "$(id -u)" -eq 0 ] && { c_err "Jangan jalankan sebagai root. Pakai user pemilik instalasi (sudo diminta bila perlu)."; exit 1; }
  if [ ! -f "$BASE/backend/main.py" ] || [ ! -f "$BASE/scripts/common.sh" ]; then
    c_err "Folder $BASE bukan instalasi CODING_SERVER — dibatalkan."; exit 1
  fi

  # --- Tentukan nasib data ---
  if [ -z "$PURGE" ]; then
    if [ "$YES" = 0 ] && is_tty; then
      echo "Data CODING_SERVER: proyek & database di workspace/, backup di backups/, konfigurasi .env"
      confirm "Hapus juga SEMUA DATA tersebut? (default: dipertahankan)" && PURGE=1 || PURGE=0
    else
      PURGE=0
    fi
  fi

  echo "=== Uninstall CODING_SERVER ==="
  echo "  Folder      : $BASE"
  echo "  Service     : $SERVICE"
  echo "  Data        : $([ "$PURGE" = 1 ] && echo "DIHAPUS$([ "$FINAL_BACKUP" = 1 ] && echo " (backup akhir ke $BACKUP_DIR)")" || echo "dipertahankan")"
  echo "  Runtime     : $([ "$REMOVE_RUNTIMES" = 1 ] && echo "dihapus (.NET / PHP milik CODING_SERVER)" || echo "dipertahankan")"
  echo "  Folder repo : $([ "$REMOVE_REPO" = 1 ] && echo "DIHAPUS" || echo "dipertahankan")"
  [ "$DRY" = 1 ] && c_info "Mode dry-run: tidak ada yang diubah."
  if [ "$DRY" = 0 ] && ! confirm "Lanjutkan uninstall?"; then
    is_tty || c_err "Tidak ada terminal untuk konfirmasi: tambahkan -y"
    echo "Dibatalkan."; exit 1
  fi

  # --- 1. Backup akhir (sebelum apa pun dihentikan/dihapus) ---
  if [ "$PURGE" = 1 ] && [ "$FINAL_BACKUP" = 1 ]; then
    local items=() ts arc
    for d in workspace backups deployment/configuration/coding_server.env; do [ -e "$BASE/$d" ] && items+=("$d"); done
    if [ ${#items[@]} -gt 0 ]; then
      ts="$(date +%Y%m%d-%H%M%S)"; arc="$BACKUP_DIR/coding_server_uninstall_$ts.tar.gz"
      c_info "Membuat backup akhir: $arc"
      if [ "$DRY" = 1 ]; then echo "    [dry-run] tar czf $arc ${items[*]}"
      else
        mkdir -p "$BACKUP_DIR"
        # Server bisa sedang menulis; database diambil apa adanya — server dihentikan setelah ini.
        if ( umask 077; tar czf "$arc.partial" -C "$BASE" --exclude=workspace/cache \
               --exclude=workspace/coding_server.pid "${items[@]}" ) && tar tzf "$arc.partial" >/dev/null \
           && mv "$arc.partial" "$arc"; then
          c_ok "Backup akhir terverifikasi ($(du -h "$arc" | cut -f1)): $arc"
        else
          rm -f "$arc.partial"
          c_err "Backup akhir GAGAL — data tidak akan dihapus."
          PURGE=0; REMOVE_REPO=0; FAILED+=("backup akhir gagal; data dipertahankan")
        fi
      fi
    fi
  fi

  # --- 2. Hentikan & hapus service / autostart ---
  echo "-- Service & autostart"
  if systemd_installed; then
    if root_do true 2>/dev/null; then
      runq root_do systemctl disable --now "$SERVICE"
      run root_do rm -f "$SYSTEM_UNIT"
      run root_do systemctl daemon-reload
      runq root_do systemctl reset-failed "$SERVICE"
      c_ok "systemd service $SERVICE dihapus"
    else
      fail "Service sistem $SYSTEM_UNIT butuh sudo. Jalankan: sudo systemctl disable --now $SERVICE && sudo rm $SYSTEM_UNIT && sudo systemctl daemon-reload"
    fi
  fi
  if user_systemd_installed; then
    runq systemctl --user disable --now "$SERVICE"
    run rm -f "$USER_UNIT"
    run systemctl --user daemon-reload
    runq systemctl --user reset-failed "$SERVICE"
    c_ok "systemd --user service $SERVICE dihapus (linger dibiarkan: dipakai service lain)"
  fi
  if [ -n "$(cron_lines_mine)" ]; then
    run cron_remove_mine && c_ok "Autostart cron @reboot dihapus"
  fi

  # --- 3. Hentikan proses yang tersisa (mode supervisor, uvicorn, terminal/sandbox) ---
  echo "-- Proses"
  if [ -f "$PID_FILE" ]; then
    local pid; pid="$(cat "$PID_FILE" 2>/dev/null)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      run kill -TERM -- "-$pid" 2>/dev/null || run kill -TERM "$pid" 2>/dev/null
    fi
  fi
  local pats=("$BASE/scripts/run_server.sh" "$VENV/bin/python" "$VENV/bin/uvicorn")
  for p in "${pats[@]}"; do runq pkill -TERM -f -- "$p"; done
  if [ "$DRY" = 0 ]; then
    for _ in $(seq 1 15); do
      local alive=0; for p in "${pats[@]}"; do pgrep -f -- "$p" >/dev/null && alive=1; done
      [ "$alive" = 0 ] && break; sleep 1
    done
    for p in "${pats[@]}"; do pkill -KILL -f -- "$p" 2>/dev/null; done
    if pgrep -f -- "$VENV/bin/" >/dev/null; then fail "Masih ada proses CODING_SERVER berjalan: $(pgrep -f -- "$VENV/bin/" | tr '\n' ' ')"
    else c_ok "Tidak ada proses CODING_SERVER yang berjalan"; fi
    if command -v ss >/dev/null && ss -ltn 2>/dev/null | awk '{print $4}' | grep -q ":$CS_PORT\$"; then
      c_warn "Port $CS_PORT masih dipakai proses lain (bukan dari folder ini?)"
    fi
  fi

  # --- 4. Hapus komponen aplikasi ---
  echo "-- Berkas aplikasi"
  safe_rm "$VENV"
  safe_rm "$BASE/logs"
  safe_rm "$BASE/workspace/cache"
  safe_rm "$PID_FILE"
  safe_rm "$BASE/web_editor/node_modules"
  safe_rm "$BASE/.pytest_cache"
  if [ "$DRY" = 1 ]; then echo "    [dry-run] hapus semua __pycache__ dan *.partial"
  else
    find "$BASE" -path "$BASE/.git" -prune -o -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null
    find "$BASE" -path "$BASE/.git" -prune -o -type f -name '*.partial' -exec rm -f {} + 2>/dev/null
    c_ok "Cache Python & file sementara dibersihkan"
  fi

  # --- 5. Data ---
  if [ "$PURGE" = 1 ]; then
    echo "-- Data"
    safe_rm "$BASE/workspace"
    safe_rm "$BASE/backups"
    safe_rm "$ENV_FILE"
  else
    c_info "Data dipertahankan: workspace/, backups/, $(basename "$ENV_FILE") (hapus nanti dengan --purge)"
  fi

  # --- 6. Runtime opsional ---
  if [ "$REMOVE_RUNTIMES" = 1 ]; then
    echo "-- Runtime"
    local rts=()
    if [ -f "$RUNTIME_MANIFEST" ]; then mapfile -t rts < "$RUNTIME_MANIFEST"
    else
      # Instalasi lama tanpa catatan: kenali dari symlink yang dibuat install_runtimes.sh
      [ "$(readlink "$HOME/.local/bin/dotnet" 2>/dev/null)" = "$HOME/.dotnet/dotnet" ] && rts+=(dotnet)
      [ "$(readlink "$HOME/.local/bin/php" 2>/dev/null)" = "$HOME/.local/opt/php/php" ] && rts+=(php)
      [ ${#rts[@]} -gt 0 ] && c_warn "Tidak ada catatan runtime; terdeteksi dari symlink: ${rts[*]}"
    fi
    for rt in "${rts[@]}"; do
      case "$rt" in
        dotnet)
          if confirm "Hapus .NET SDK di ~/.dotnet? (pastikan tidak dipakai aplikasi lain)"; then
            SAFE_EXTRA=("$HOME/.dotnet"); safe_rm "$HOME/.dotnet"
            [ "$(readlink "$HOME/.local/bin/dotnet" 2>/dev/null)" = "$HOME/.dotnet/dotnet" ] && run rm -f "$HOME/.local/bin/dotnet"
          else c_info ".NET dipertahankan"; fi ;;
        php)
          if confirm "Hapus PHP statis di ~/.local/opt/php?"; then
            SAFE_EXTRA=("$HOME/.local/opt/php"); safe_rm "$HOME/.local/opt/php"
            [ "$(readlink "$HOME/.local/bin/php" 2>/dev/null)" = "$HOME/.local/opt/php/php" ] && run rm -f "$HOME/.local/bin/php"
          else c_info "PHP dipertahankan"; fi ;;
      esac
    done
    SAFE_EXTRA=()
    [ ${#rts[@]} -eq 0 ] && c_info "Tidak ada runtime yang dipasang oleh CODING_SERVER"
    safe_rm "$RUNTIME_MANIFEST"
  fi

  # --- 7. Folder repo ---
  if [ "$REMOVE_REPO" = 1 ]; then
    echo "-- Folder repo"
    if [ -n "$(git -C "$BASE" status --porcelain 2>/dev/null)" ] || \
       [ -n "$(git -C "$BASE" log --branches --not --remotes --oneline 2>/dev/null)" ]; then
      c_warn "Repo punya perubahan yang belum di-commit / belum di-push."
      confirm "Tetap hapus folder repo $BASE?" || { c_info "Folder repo dipertahankan"; REMOVE_REPO=0; }
    fi
    if [ "$REMOVE_REPO" = 1 ]; then
      case "$BASE" in /|"$HOME"|"") fail "Menolak menghapus $BASE" ;;
        *) cd / && run rm -rf -- "$BASE" && c_ok "Folder repo dihapus: $BASE" ;;
      esac
    fi
  fi

  # --- Ringkasan ---
  echo
  if [ ${#FAILED[@]} -eq 0 ]; then
    c_ok "Uninstall CODING_SERVER selesai$([ "$DRY" = 1 ] && echo " (dry-run)")."
  else
    c_warn "Uninstall selesai dengan ${#FAILED[@]} masalah:"; for f in "${FAILED[@]}"; do echo "   - $f"; done
  fi
  echo "Catatan:"
  echo "  - Hapus aplikasi CODING_SERVER di HP Android secara manual (Setelan → Aplikasi)."
  echo "  - Paket apt (gcc, g++, default-jdk, golang, nodejs, sqlite3, bubblewrap) tidak disentuh."
  [ "$REMOVE_REPO" = 0 ] && [ "$DRY" = 0 ] && echo "  - Pasang ulang kapan saja: $BASE/scripts/install.sh"
  [ ${#FAILED[@]} -eq 0 ]
}

# Seluruh skrip dibaca dulu sebelum dijalankan (aman walau folder repo ikut dihapus)
main; exit $?
