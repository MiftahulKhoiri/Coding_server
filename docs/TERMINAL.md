# Terminal

- `POST /api/v1/terminal/sessions {project_id, cwd, cols, rows}` → `session_id`; lalu WebSocket `/ws/terminal/{session_id}?token=…`.
- Shell `bash` interaktif di **PTY** (`pty.openpty` + `setsid --ctty`), dijalankan lewat `subprocess` (tanpa `fork()` manual di proses multi-thread).
- Sesi punya `session_id, owner_id, project_id, working_directory, created_at, last_activity, status, history`.
- Banyak sesi per user (maks `CS_MAX_TERMINAL_SESSIONS`, default 6); scrollback 200 KB dikirim ulang saat reconnect.
- **Keamanan**: butuh izin `terminal` (viewer/runner/ai tidak punya); shell berjalan di sandbox bwrap: `$HOME` kosong (tmpfs),
  sistem read-only, hanya folder proyek + cache compiler yang bisa ditulis; jaringan mengikuti `CS_TERMINAL_NETWORK`
  (default aktif agar `pip`/`go get` bisa); batas ukuran file 1 GB, CPU 24 jam, `nice 5`.
- Idle timeout `CS_TERMINAL_IDLE_TIMEOUT` (1800 dtk, hanya bila tidak ada klien terhubung), pembersihan sesi otomatis tiap 30 dtk.
- Catatan jujur: terminal adalah shell sungguhan di dalam sandbox — pengguna dengan izin `terminal` bisa menjalankan
  apa pun yang diizinkan sandbox. Jangan beri izin itu ke akun yang tidak dipercaya.
