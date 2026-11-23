# Changelog

## 1.3.0 — 2026-11-23
### Ditambahkan
- **Language server (LSP)**: clangd 22 (C/C++) dan pyright (Python) di Pi, lewat WebSocket `/ws/lsp`, di dalam
  sandbox bubblewrap (proyek read-only, tanpa jaringan, path asli disamarkan). Editor: autocomplete dari LSP,
  error/peringatan saat mengetik, **Info simbol di kursor**, **Ke definisi** lintas file (membuka file tujuan).
  Sakelar di Pengaturan → Editor. Dipasang otomatis tanpa sudo oleh `install_runtimes.sh`.
- **Build C/C++ multi-file**: CMake (Ninja, compile_commands.json), Makefile (`make run` / executable terbaru),
  dan mode otomatis multi-file dengan deteksi `main()`.
- **AI mengubah file proyek**: proposal dari jawaban AI (file utuh atau SEARCH/REPLACE toleran spasi/indentasi),
  kartu diff Terapkan/Tolak/Batalkan di aplikasi, sakelar terapkan otomatis, tab editor dimuat ulang, proposal basi
  ditolak, editan bisa dibatalkan.
### Diperbaiki
- Pesan error job tampil sebagai `\n` literal di output.

## 1.2.0 — 2026-11-23 (Android)
### Ditambahkan
- **Pilihan tema aplikasi** (Pengaturan → Tampilan): mode Ikuti sistem / Gelap / Terang, 11 warna aksen (Biru, Teal,
  Hijau, Ungu, Nila, Oranye, Merah, Merah muda, Kuning, Abu-abu, **Dinamis** = Material You dari wallpaper, Android 12+),
  dan latar **hitam pekat AMOLED**. Ikon status bar menyesuaikan tema. Disimpan di DataStore.
- **Preset warna editor** di dialog Warna editor: One Dark, Dracula, Monokai, Nord, Solarized Gelap/Terang,
  GitHub Gelap/Terang, Hitam AMOLED, Kertas (sekaligus memilih editor gelap/terang).
- Unit test tema (`ThemeTest`).

## 1.1.1 — 2026-11-23
### Ditambahkan
- `scripts/uninstall.sh`: hapus service systemd (system/user) + cron autostart, hentikan proses tersisa, bersihkan
  `.venv`, log, cache, PID, `__pycache__`. Opsi `--purge` (hapus data setelah backup akhir terverifikasi),
  `--remove-runtimes`, `--remove-repo`, `--dry-run`, `-y`. Penghapusan dibatasi ke folder instalasi.
- `CS_SERVICE_NAME` untuk menjalankan instalasi kedua (mis. uji) berdampingan dengan nama service berbeda.
- `install_runtimes.sh` mencatat runtime yang dipasangnya (`deployment/configuration/.installed_runtimes`).
### Diperbaiki
- Skrip mengenali unit systemd hanya dari namanya: `stop.sh`/`start.sh` dari salinan lain bisa mematikan service
  utama, dan installer salinan bisa menimpa unit-nya. Kini unit dianggap milik instalasi ini hanya bila `ExecStart`
  menunjuk ke folder ini; installer menolak menimpa unit milik folder lain.
- Pembersihan cron hanya menghapus baris milik folder ini (sebelumnya semua baris ber-marker).
- `status.sh` tidak lagi membuat ulang folder `logs/`/`workspace/` dan memberi pesan jelas bila venv tidak ada.
- Versi backend (`/system/health`) masih 1.0.0 padahal rilis 1.1.0 → kini 1.1.1.

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
