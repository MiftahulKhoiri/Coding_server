# Instalasi

## 1. Prasyarat di Raspberry Pi 5
```bash
sudo apt update
sudo apt install -y git python3 python3-venv bubblewrap curl gcc g++ default-jdk golang nodejs sqlite3
# opsional (bila tidak ingin PHP statis): sudo apt install -y php-cli
```
`.NET 8` dan `PHP` (bila belum ada) dipasang otomatis di `~/.dotnet` dan `~/.local/opt/php` oleh
`scripts/install_runtimes.sh` — tanpa sudo, binary resmi ARM64.

## 2. Pasang
```bash
git clone git@github.com:MiftahulKhoiri/Coding_server.git ~/Coding_server
cd ~/Coding_server
./scripts/install.sh
```
Langkah installer: cek OS → cek ARM64 → cek Python ≥ 3.10 → cek git/bwrap/curl → buat direktori
`workspace/ logs/ backups/` → buat `deployment/configuration/coding_server.env` (0600) → venv `.venv` +
`pip install -r requirements.txt` → pasang runtime opsional → uji semua engine → pasang autostart → start + health check.

## 3. Autostart (systemd)
- Dengan sudo (service sistem, berjalan sebagai user non-root):
  `sudo ./scripts/install_systemd.sh` (pakai `CS_SERVICE_USER=nama` untuk user khusus).
- Tanpa sudo (systemd user service): `./scripts/install_user_systemd.sh` — butuh *linger*
  (`sudo loginctl enable-linger $USER`, sekali saja). Di Pi 5 ini linger sudah aktif.
- Service: auto-start saat boot, `Restart=on-failure`, log terpisah `logs/service.log`, `NoNewPrivileges`, tidak pernah root.

## 4. Konfigurasi
Edit `deployment/configuration/coding_server.env` (lihat `.env.example` untuk semua kunci), lalu `./scripts/restart.sh`.
Penting: `CS_PORT` (8800), `CS_MAX_CONCURRENT_JOBS`, `CS_MEMORY_LIMIT_MB`, `CS_SANDBOX`, `CS_SANDBOX_NETWORK`,
`CS_HTTP_ALLOW_PRIVATE`, `CS_BACKUP_RETENTION`, `CS_AI_BASE_URL`.

## 5. Login pertama
Sandi admin utama: `./scripts/admin_password.sh` (membaca `CS_ADMIN_PASSWORD` atau
`workspace/metadata/initial_admin_password.txt`) → login di APK. **Jangan hapus file itu** kecuali memakai
`CS_ADMIN_PASSWORD`: sandi admin utama selalu disinkronkan dari sana setiap server start dan tidak bisa diubah
lewat aplikasi (akun pemulihan). Ganti sandinya dengan `./scripts/admin_password.sh --set`.
Lalu buat profil harian di APK → Pengaturan → Pengguna → ➕.

## 6. Update server
```bash
cd ~/Coding_server && git pull && .venv/bin/pip install -r requirements.txt && ./scripts/restart.sh
```

## 7. Uninstall
```bash
./scripts/uninstall.sh [--purge] [--remove-runtimes] [--remove-repo] [-y] [--dry-run]
```
| Langkah | Default | `--purge` |
|---|---|---|
| Backup akhir `~/coding_server_uninstall_<waktu>.tar.gz` (0600, diverifikasi) | – | ✔ (lewati: `--no-final-backup`, lokasi: `--backup-dir`) |
| Hentikan & hapus service systemd (system/user) dan cron `@reboot` milik folder ini | ✔ | ✔ |
| Hentikan proses tersisa (supervisor, uvicorn, terminal/sandbox) | ✔ | ✔ |
| Hapus `.venv/`, `logs/`, `workspace/cache/`, PID, `__pycache__`, `*.partial`, `web_editor/node_modules` | ✔ | ✔ |
| Hapus `workspace/` (proyek, database, metadata, riwayat), `backups/`, `coding_server.env` | – | ✔ |

- Tanpa opsi di terminal interaktif, skrip **menanyakan** apakah data ikut dihapus (default: dipertahankan).
  Tanpa terminal (mis. lewat SSH non-interaktif) wajib `-y`.
- Bila backup akhir gagal, data **tidak** dihapus.
- `--remove-runtimes`: hapus `~/.dotnet` dan `~/.local/opt/php` beserta symlink di `~/.local/bin` — hanya yang tercatat
  dipasang oleh `install_runtimes.sh` (`deployment/configuration/.installed_runtimes`), dikonfirmasi satu per satu.
- `--remove-repo`: hapus seluruh folder repo (memperingatkan bila ada perubahan yang belum di-commit/push).
- Tidak disentuh: *linger* systemd (bisa dipakai service lain), paket apt, aplikasi di HP.
- Service systemd **sistem** butuh sudo; bila sudo tidak tersedia skrip menampilkan perintah manualnya.
- Unit/cron hanya dianggap milik instalasi ini bila menunjuk ke folder ini, jadi uninstall salinan lain tidak bisa
  mematikan service utama. Instalasi kedua di Pi yang sama: set `CS_SERVICE_NAME` dan `CS_PORT` berbeda di `.env`.
