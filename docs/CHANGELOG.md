# Changelog

## 1.0.0 — 2026-11-20
### Ditambahkan
- Backend FastAPI modular: auth (scrypt, JWT access/refresh rotasi, pencabutan, rate limit), izin berbasis peran, audit log.
- File & project manager aman (traversal/symlink), tulis atomik, deteksi konflik, riwayat versi & restore, favorit, file terakhir, pencarian.
- Execution manager: antrean, batas job bersamaan, cek RAM, timeout, watchdog RAM, rlimit, batas output, cancel, stdin, streaming WebSocket, riwayat.
- 11 engine: Python, Node.js, PHP, Go, C, C++, Java, C#, SQLite, HTML/CSS (pratinjau), Bash — semuanya lolos uji di Raspberry Pi 5 ARM64.
- Sandbox bubblewrap untuk eksekusi, terminal, dan Git.
- Terminal PTY multi-sesi lewat WebSocket.
- Database manager SQLite, Git manager (token terenkripsi), HTTP client anti-SSRF, system monitor, backup/restore terverifikasi + backup harian otomatis, fondasi AI agent.
- Web editor CodeMirror 6 + terminal xterm.js (bundel offline).
- Aplikasi Android (Compose) lengkap 12 halaman, update otomatis dari GitHub Releases, CI build APK + uji kontrak API.
- Skrip instalasi, systemd (system & user), health check, backup CLI, dokumentasi.

### Diperbaiki selama pengujian
- Terminal: `pty.fork()` di proses multi-thread → `subprocess` + `setsid --ctty`; `remove_reader` sebelum `close(fd)` (fd pidfd dicuri callback terminal sehingga eksekusi berikutnya menggantung).
- Engine memakai path asli executable (symlink di `~/.local/bin` tidak ada di sandbox).
- .NET: lock `~/.dotnet/corefx` writable & W^X dimatikan (SIGXFSZ).
- Pemisahan pernyataan SQL per karakter `;` (bukan per baris).
