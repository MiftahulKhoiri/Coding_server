# PROJECT_STATUS — CODING_SERVER 1.1.1

Terakhir diperbarui: 23 Nov 2026. Semua status di bawah berdasarkan uji nyata di Raspberry Pi 5 (aarch64) dan CI GitHub.

## Lingkungan server aktual
Raspberry Pi 5 Model B Rev 1.1 · Debian 13 (trixie) aarch64 · kernel 6.18 · 16 GB RAM · NVMe 468 GB ·
Python 3.13.5 · service `coding-server` (systemd **user**, linger aktif → auto-start saat boot) · port **8800** ·
sandbox **bubblewrap aktif**.

## Definition of Done
| Kriteria | Status | Bukti |
|---|---|---|
| Backend berjalan di Raspberry Pi 5 | ✅ | `scripts/status.sh` → `Backend: ok, sandbox=True` |
| Backend berjalan otomatis saat boot | ✅ | `systemctl --user is-enabled coding-server` = enabled, linger = yes, `Restart=on-failure` |
| Android dapat terhubung ke server | ✅* | Uji kontrak `BackendIntegrationTest` (klien Retrofit/DTO aplikasi) lulus terhadap server di Pi & di CI |
| Login dan autentikasi | ✅ | test_auth (login, refresh rotasi, logout/pencabutan, izin) |
| Project manager | ✅ | test_files::test_project_crud + uji kontrak |
| File manager | ✅ | test_files (CRUD, rename/copy/move, search, history/restore, konflik) |
| Editor membuka & menyimpan file | ✅* | Editor CodeMirror diuji di Chrome headless (tab, isi, dirty, undo, diagnostics); simpan via `/files/write` diuji kontrak |
| Syntax highlighting | ✅ | Tangkapan layar uji editor (C, Python) |
| Terminal interaktif | ✅ | test_terminal_session (PTY via WebSocket) + test_terminal_sandboxed di Pi |
| Output real-time | ✅ | test_output_streaming_ws |
| Process manager | ✅ | test_timeout, test_cancel, test_memory_limit, antrean (uji performa 7 job bersamaan) |
| Python / JavaScript / PHP / Go dijalankan | ✅ | test_run_language di Pi |
| C / C++ dikompilasi | ✅ | test_run_language + test_compile_error |
| Java / C# dijalankan | ✅ | test_run_language di Pi (.NET 8.0.428, OpenJDK 21) |
| SQLite menjalankan query | ✅ | test_run_language[sql] + test_database_manager |
| HTTP Client | ✅ | test_http_ssrf_blocked (6 kasus), koleksi; request keluar via httpx |
| Git | ✅ | test_git_flow + uji kontrak (init/commit/log) |
| System Monitor | ✅ | test_system_monitor; data dari psutil & /sys (suhu nyata 40–43 °C) |
| Backup dan restore diuji | ✅ | test_backup_and_restore, test_backup_corruption_detected |
| Keamanan workspace diuji | ✅ | traversal, symlink escape, isolasi antar user, uji sandbox (ssh/shadow/net/tulis luar) |
| Proses dapat dihentikan | ✅ | test_cancel (status CANCELLED) |
| APK berhasil dibangun | ✅ | build lokal Pi (`assembleDebug`, unit test) + CI GitHub Actions → Release `android-latest` |
| APK dipasang di HP | ⏳ | Belum bisa dilakukan dari server — perlu dipasang oleh pengguna |
| Integrasi Android ↔ Raspberry Pi diuji | ✅* | Uji kontrak API dari kode klien Android ke server Pi (lulus). Uji UI di perangkat fisik belum |
| Dokumentasi lengkap | ✅ | README.md + docs/ (13 file) |

`*` = diuji pada level kode klien/kontrak, bukan sentuhan layar di HP fisik.

## Hasil uji aktual
- **Backend di Pi 5**: `52 passed` (pytest, termasuk 2 uji sandbox). CI Ubuntu: lulus.
- **Uninstall (23 Nov 2026, Pi 5)**: instalasi uji kedua (`CS_SERVICE_NAME=coding-server-test`, port 8811) dipasang
  lalu di-uninstall: default (service+cron+proses+venv+log+cache hilang, data tetap), `--purge` (backup akhir 0600
  terverifikasi lalu data hilang), `--dry-run`, opsi tak dikenal, tanpa `-y` non-interaktif (batal). Cron milik folder
  lain dan service utama tidak tersentuh. `--remove-repo` dan `--remove-runtimes` hanya diuji lewat `--dry-run`.
- **Backend di Pi 5 (23 Nov)**: `61 passed`.
- **Backend (24 Nov, sesi cloud tanpa bubblewrap, `CS_SANDBOX=none`)**: `97 passed, 6 skipped`. Uji sandbox berjalan di CI.
- **Android**: 6 unit test + 1 uji kontrak end-to-end lulus (di Pi dan di CI).
- **Performa (Pi 5, live)**: health p50 1.1 ms / p95 1.3 ms; baca file p50 3.5 ms.
  Run (termasuk compile, sandbox): Python 0.16 s, C 0.06 s, PHP 0.31 s, Java 0.72 s, Node 0.87 s,
  Go 5.3 s pertama (cache build dingin) lalu 0.15 s, C# ~4 s (dotnet build). 7 job bersamaan dengan
  `max_concurrent=2` selesai dalam 5.0 s total, semua COMPLETED; RAM 35 %, CPU idle 2 %, suhu 43 °C.

## Belum selesai / catatan jujur
1. **Pemasangan & uji APK di HP fisik** belum dilakukan (tidak ada perangkat Android yang bisa dikendalikan dari sini).
2. **Secret `ANDROID_KEYSTORE_PASSWORD`** belum diisi di GitHub (tidak bisa diatur dari sesi ini). APK saat ini
   ditandatangani kunci debug. Isi secret dengan isi `~/.coding_server_signing/ANDROID_KEYSTORE_PASSWORD` (di Pi),
   lalu hapus aplikasi sekali & pasang ulang.
3. **Service sistem dengan user khusus**: butuh sudo (`sudo ./scripts/install_systemd.sh`). Saat ini berjalan sebagai
   systemd user service milik `pi5` (non-root) — memenuhi auto-start & restart, tetapi bukan user terpisah.
4. **Language server (LSP)** belum diintegrasikan; autocomplete dasar (kata di dokumen + bahasa), simbol & go-to-definition
   memakai pola regex per bahasa.
5. Build C/C++ satu file per eksekusi (belum Makefile/CMake multi-file otomatis — bisa lewat terminal).
6. AI agent (v1.4.0): loop agen otomatis + layar Agent Tasks sudah ada (lihat docs/AI_AGENT.md); diuji dengan
   model palsu di pytest, **belum diuji dengan model asli di Pi**.

## Rekomendasi berikutnya
Isi secret signing → pasang APK → uji alur di HP; aktifkan systemd sistem dengan sudo; pasang reverse proxy HTTPS
bila diakses dari luar rumah; integrasi LSP (pyright/clangd) lewat WebSocket; UI chat AI memakai llama-server di Pi.
