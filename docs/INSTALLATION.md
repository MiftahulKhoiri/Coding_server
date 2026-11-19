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
Password admin acak: `cat workspace/metadata/initial_admin_password.txt` → login di APK → ganti password
(`POST /api/v1/auth/password`) → hapus file tersebut.

## 6. Update server
```bash
cd ~/Coding_server && git pull && .venv/bin/pip install -r requirements.txt && ./scripts/restart.sh
```
