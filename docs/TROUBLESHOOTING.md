# Troubleshooting

| Gejala | Penyebab / solusi |
|---|---|
| APK: "Server tidak bisa dihubungi (offline?)" | Cek `./scripts/status.sh` di Pi; IP benar (`hostname -I`); HP & Pi di jaringan sama; port 8800 tidak diblokir firewall |
| Lupa password admin | `cat workspace/metadata/initial_admin_password.txt` (bila belum dihapus). Atau reset: `.venv/bin/python -c "from backend.config import build_settings;from backend.database.db import Database;from backend.services.auth_service import AuthService as A;s=build_settings();A(s,Database(s.metadata_dir/'coding_server.db')).update_user(1,password='PASSWORD-BARU')"` lalu restart |
| Engine `NOT_INSTALLED` | Pasang paket (`sudo apt install …` atau `scripts/install_runtimes.sh`), lalu Monitor → "Periksa ulang" |
| Job ditolak `low_memory` / `queue_full` | RAM bebas di bawah `CS_MIN_FREE_MEMORY_MB` atau antrean penuh; tunggu / turunkan beban / ubah konfigurasi |
| Program berhenti `TIMEOUT` | Naikkan `timeout` di request (≤ 10× `CS_RUN_TIMEOUT`) atau ubah `CS_RUN_TIMEOUT` |
| C# gagal exit 153 | `RLIMIT_FSIZE` vs W^X .NET — sudah diatasi (`DOTNET_EnableWriteXorExecute=0`); pastikan versi terbaru |
| C# "NuGet-Migrations" | Folder `~/.dotnet/corefx` harus ada & writable (dibuat otomatis oleh engine) |
| `sandbox:false` di health | bwrap tidak ada / user namespace dimatikan: `sudo apt install bubblewrap`; cek `sysctl kernel.unprivileged_userns_clone` |
| Service tidak jalan saat boot | Mode user: `loginctl show-user $USER -p Linger` harus `yes`; mode sistem: `sudo systemctl status coding-server` |
| `systemctl --user` error "Failed to connect to bus" | `export XDG_RUNTIME_DIR=/run/user/$(id -u)` (skrip melakukannya otomatis) |
| APK update gagal "tanda tangan beda" | Hapus aplikasi sekali, pasang APK dari Releases (terjadi saat pindah dari kunci debug ke kunci rilis) |
| Editor kosong di APK | Aset `assets/web/editor.html` tidak ada → build ulang `web_editor` (`npm run build`) |
| Log | `logs/server.log`, `logs/service.log`, `logs/audit.log`; `journalctl --user -u coding-server` |
