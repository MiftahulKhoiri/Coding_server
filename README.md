# CODING_SERVER

Server pengembangan multi-bahasa untuk **Raspberry Pi 5** dengan **aplikasi Android** sebagai remote IDE.
Raspberry Pi adalah server utama & mesin eksekusi (file, compiler, runtime, terminal, Git, database);
HP Android hanya antarmuka (editor, explorer, terminal, output, monitor).

```
Android APK (Kotlin/Compose + WebView CodeMirror 6/xterm.js)
        │  REST /api/v1  +  WebSocket /ws/...
        ▼
Raspberry Pi 5 — FastAPI (Python 3)
  ├─ API layer      : auth, projects, files, execution, terminal, database, git, http, system, backup, ai
  ├─ Service layer  : FileService, ProjectService, ExecutionService, TerminalService, ...
  ├─ Engine layer   : BaseEngine → Python, Node.js, PHP, Go, C, C++, Java, C#, SQLite, HTML/CSS, Bash
  ├─ Sandbox        : bubblewrap (namespace) + rlimit + watchdog RAM + timeout + antrean job
  └─ Storage        : workspace/ (proyek, database, metadata SQLite, riwayat), logs/, backups/
```

## Fitur
- **Multi-bahasa (11 engine)**: Python 3, JavaScript (Node.js), PHP, Go, C (GCC), C++ (G++), Java (JDK), C# (.NET 8), SQL (SQLite), HTML/CSS (pratinjau), Bash. Status setiap engine diperiksa nyata (`AVAILABLE` / `NOT_INSTALLED` / `ERROR`).
- **Execution manager**: antrean job, batas job bersamaan, tolak/tunda saat RAM hampir habis, timeout, batas RAM (watchdog RSS + RLIMIT_AS), batas CPU & ukuran file, batas output, pembatalan, stdin interaktif, streaming output via WebSocket, riwayat eksekusi. Status: `QUEUED → STARTING → RUNNING → COMPLETED/FAILED/TIMEOUT/CANCELLED`.
- **Sandbox nyata** (bubblewrap): sistem read-only, `$HOME` diganti tmpfs (kunci SSH/token tidak terlihat), hanya folder proyek yang bisa ditulis, jaringan diputus (bisa diaktifkan), PID/IPC terpisah.
- **Instal dependensi** (`POST /execution/install`, tombol ⬇ di Explorer, tool agen `install_deps`): pip → `.venv`
  proyek (otomatis dipakai saat Jalankan & uji), `npm install`, `go mod download`, `composer install`. Hanya langkah
  instal yang mendapat internet (`CS_INSTALL_NETWORK`, bawaan aktif); program biasa tetap tanpa jaringan.
- **Profil & pengguna**: nama tampilan, email, bio, ganti sandi sendiri; admin mengelola akun (peran, reset sandi,
  nonaktif, hapus — proyeknya pindah ke admin utama).
- **Terminal interaktif** (PTY + WebSocket), banyak sesi, di dalam sandbox, idle timeout.
- **File manager** aman: CRUD, rename/copy/move, cari nama & isi, favorit, file terakhir, tulis atomik, deteksi konflik (SHA-256), riwayat versi + undo/restore, proteksi path traversal & symlink.
- **Editor CodeMirror 6** di WebView: syntax highlighting 18+ bahasa, nomor baris, auto indent, bracket matching, find/replace, banyak tab, undo/redo, code folding, word wrap, ukuran font, tema gelap/terang, autocomplete, diagnostics dari output compiler, simbol dokumen.
- **Language server (LSP)**: clangd (C/C++) dan pyright (Python) di server, di dalam sandbox — autocomplete pintar, error/peringatan saat mengetik, info simbol, go-to-definition lintas file. Bahasa lain memakai pola regex.
- **Build C/C++ multi-file**: CMake, Makefile, atau otomatis (semua sumber di folder + subfolder; folder latihan dengan banyak `main()` tetap jalan per file).
- **AI coding agent**: chat dengan model lokal (llama-server) / online; bila proyek terbuka, AI mengubah file lewat blok `file=` / SEARCH-REPLACE → kartu diff **Terapkan / Tolak / Batalkan**, atau diterapkan otomatis. Semua perubahan tercatat di riwayat file & bisa dibatalkan.
- **AI Agent Tasks**: beri tugas ("perbaiki bug X dan pastikan test lulus") → agen memeriksa proyek, membuat rencana,
  mengusulkan perubahan (risiko LOW/MEDIUM/HIGH, butuh persetujuanmu), menjalankan build/test di sandbox, memperbaiki
  bila gagal, lalu memberi laporan. Task tersimpan dan bisa dijeda/dilanjutkan. Lihat `docs/AI_AGENT.md`.
- **Database manager SQLite**, **Git manager**, **HTTP client/API tester** (anti-SSRF), **System monitor**, **Backup & restore** terverifikasi.
- **Aplikasi Android** dibangun otomatis oleh GitHub Actions dan bisa memperbarui dirinya sendiri dari GitHub Releases.

## Persyaratan
- Raspberry Pi 5 (diuji: 16 GB, Raspberry Pi OS / Debian 13 trixie, aarch64), Python ≥ 3.10.
- Paket sistem: `git bubblewrap curl` (+ compiler yang ingin dipakai: `gcc g++ default-jdk golang nodejs sqlite3 php-cli`).
- .NET SDK 8, PHP, clangd (LSP C/C++, dari PyPI) dan pyright (LSP Python, npm) dipasang otomatis tanpa sudo oleh
  `scripts/install_runtimes.sh` bila belum ada. Untuk build C/C++ proyek: `make cmake ninja-build`.

## Instalasi
```bash
git clone git@github.com:MiftahulKhoiri/Coding_server.git ~/Coding_server
cd ~/Coding_server
./scripts/install.sh
```
Installer memeriksa OS/ARM64/Python/dependensi, membuat venv, memasang paket, memasang runtime opsional,
menguji setiap engine, membuat konfigurasi, memasang **systemd service** (`coding-server`), lalu health check.
Password admin awal ditampilkan dan tersimpan di `workspace/metadata/initial_admin_password.txt`.
Akun `admin` adalah **admin utama (root)**: akun pemulihan yang tidak bisa dihapus, dinonaktifkan, atau diubah
perannya, dan sandinya hanya diatur dari server — lihat/ganti dengan `scripts/admin_password.sh`
(`--set` / `--random`), atau isi `CS_ADMIN_PASSWORD`. Untuk pemakaian harian, buat profil sendiri di
APK → Pengaturan → Pengguna; bila sandinya lupa, login sebagai admin utama lalu reset.

Mode autostart yang dipilih otomatis:
1. `sudo` tanpa password tersedia → systemd **system** service (`scripts/install_systemd.sh`).
2. *linger* aktif → systemd **user** service (tanpa sudo) — mode yang terpasang di Pi 5 saat ini.
3. Selain itu → cron `@reboot` + supervisor (restart otomatis).

## Menjalankan server
```bash
./scripts/start.sh     ./scripts/stop.sh     ./scripts/restart.sh     ./scripts/status.sh
```

## Uninstall
```bash
./scripts/uninstall.sh                # hapus aplikasi (service, autostart, proses, venv, log, cache); data dipertahankan
./scripts/uninstall.sh --purge        # + hapus data (proyek, database, backup, .env) — backup akhir dibuat dulu di ~
./scripts/uninstall.sh --dry-run      # lihat apa yang akan dihapus tanpa menghapus
```
Opsi lain: `--remove-runtimes` (.NET/PHP yang dipasang installer), `--remove-repo` (hapus folder repo), `-y` (tanpa
konfirmasi). Linger systemd dan paket apt tidak disentuh; aplikasi Android dihapus manual dari HP.
API: `http://<IP-PI>:8800/api/v1`, dokumentasi interaktif OpenAPI: `http://<IP-PI>:8800/docs`.

## Menghubungkan APK
1. Unduh **CodingServer.apk** dari [GitHub Releases → android-latest](https://github.com/MiftahulKhoiri/Coding_server/releases/tag/android-latest) dan pasang.
2. Buka aplikasi → **Tambah server** → isi `IP-PI:8800` → **Tes koneksi** → **Hubungkan**.
3. Login dengan akun admin. Selanjutnya: Proyek → Project Explorer → buka file → ▶ Jalankan.
4. Pembaruan: Pengaturan → **Periksa pembaruan** (APK baru dibuat otomatis setiap push ke `main`).

## Menggunakan compiler
Buka file lalu tekan ▶ (run) atau 🔨 (build/cek sintaks). Server memilih engine dari ekstensi file:
`.py .js .php .go .c .cpp/.cc .java .cs .sql .html/.css .sh`. Lihat [docs/EXECUTION_ENGINE.md](docs/EXECUTION_ENGINE.md).

## Dokumentasi
[ARCHITECTURE](docs/ARCHITECTURE.md) · [INSTALLATION](docs/INSTALLATION.md) · [BACKEND](docs/BACKEND.md) ·
[ANDROID](docs/ANDROID.md) · [API_REFERENCE](docs/API_REFERENCE.md) · [EXECUTION_ENGINE](docs/EXECUTION_ENGINE.md) ·
[TERMINAL](docs/TERMINAL.md) · [SECURITY](docs/SECURITY.md) · [DATABASE](docs/DATABASE.md) · [GIT](docs/GIT.md) ·
[TESTING](docs/TESTING.md) · [TROUBLESHOOTING](docs/TROUBLESHOOTING.md) · [CHANGELOG](docs/CHANGELOG.md) ·
[PROJECT_STATUS](PROJECT_STATUS.md)

## Troubleshooting singkat
- `./scripts/status.sh` → status service + health. Log: `logs/server.log`, `logs/service.log`, `logs/audit.log`.
- Engine `NOT_INSTALLED` → pasang paketnya lalu `GET /api/v1/system/engines?refresh=true`.
- APK tidak bisa update ("tanda tangan beda") → hapus aplikasi lama sekali, pasang APK dari Releases.
- Selengkapnya: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

Lisensi: lihat [LICENSE](LICENSE).
