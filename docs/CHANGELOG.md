# Changelog

## 1.1.0 — 2026-11-20
### Ditambahkan
- **AI Chat & Model AI** (konsep seperti ai_asisten): koneksi **lokal** (llama-server mode router di Pi, Ollama, server
  OpenAI-compatible lain) dan **online** (OpenAI, OpenRouter, Groq, DeepSeek, Anthropic, Google Gemini, custom).
  Alur: pilih Lokal/Online → koneksi → model → **Terapkan**. Model lokal dimuat saat diterapkan, model lama dibongkar,
  dan dibongkar otomatis bila idle (default 15 menit). API key terenkripsi, tidak pernah dikirim ke HP.
- Chat streaming via WebSocket `/ws/ai/chat` (proses berpikir model ditampilkan terpisah), riwayat percakapan per
  pengguna, sertakan file yang terbuka di editor sebagai konteks, blok kode bisa disalin / disisipkan ke editor,
  tombol "Tanya AI tentang error ini" di Build Output.
- Info versi APK di header menu samping (selain di Pengaturan → Pembaruan aplikasi).
### Diperbaiki
- Editor tidak bisa mengetik di sebagian HP: CodeMirror di Android memakai API EditContext yang input keyboard-nya
  tidak sampai ke editor pada sebagian WebView/keyboard → dimatikan (pakai contenteditable). WebView editor/terminal
  kini memakai context Activity + fokus saat disentuh; konten diberi `imePadding` (Android 15 edge-to-edge) agar baris
  yang diketik tidak tertutup keyboard; editor tanpa file terbuka kini read-only dengan petunjuk + tombol **File baru**.


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
