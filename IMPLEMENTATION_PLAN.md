# Rencana Implementasi CODING_SERVER

| Phase | Isi | Status |
|---|---|---|
| 0 Analisis | Cek Pi 5: Debian 13 trixie aarch64, 16 GB RAM, NVMe 468 GB, Python 3.13.5, gcc/g++ 14.2, OpenJDK 21, Go 1.24.4, Node 26, SQLite 3.46, git, bubblewrap 0.12, Docker; PHP & .NET belum ada, sudo butuh password, linger aktif | Selesai |
| 1 Fondasi server | struktur folder, FastAPI, config, logging, auth (scrypt+JWT), metadata SQLite, systemd | Selesai |
| 2 File & proyek | workspace, CRUD, folder, proyek + template, pencarian, keamanan path/symlink, riwayat | Selesai |
| 3 Framework eksekusi | BaseEngine, registry, process manager, job queue, streaming, timeout, cancel, sandbox bwrap | Selesai |
| 4 Bahasa | Python, JS, PHP (static ARM64), Go, C, C++, Java, C# (.NET 8 ARM64), SQLite, HTML/CSS, Bash | Selesai, semua diuji di Pi |
| 5 Terminal | WebSocket, PTY, multi-sesi, sandbox, idle cleanup | Selesai |
| 6 Web editor | CodeMirror 6 (+ xterm.js) dibundel offline | Selesai |
| 7 Android | Compose, auth, koneksi, explorer, editor, terminal, output, DB, Git, HTTP, monitor, settings, auto-update | Selesai (build + uji kontrak); uji manual di HP oleh pengguna |
| 8 Layanan lanjutan | Git, HTTP client, DB manager, monitor, backup/restore, fondasi AI | Selesai |
| 9 Integrasi & uji | pytest (Pi & CI), uji sandbox, uji kontrak Android↔backend, uji performa | Selesai |
| 10 Deployment | installer, systemd user service aktif, CI APK + Release, dokumentasi | Selesai |
