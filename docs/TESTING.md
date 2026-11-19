# Pengujian

## Backend (pytest) — `backend/tests/`
| File | Cakupan |
|---|---|
| test_auth.py | health publik, token wajib, login salah, me/refresh(rotasi)/logout(pencabutan), izin viewer, scrypt, rate limiter |
| test_files.py | CRUD proyek, CRUD file, konflik SHA, riwayat & restore, rename/copy/move, cari nama/isi, hapus rekursif, favorit, **path traversal**, **symlink escape**, isolasi proyek antar user |
| test_engines.py | status engine nyata; **run 10 bahasa** (Python, JS, PHP, Go, C, C++, Java, C#, SQL, Bash) dengan cek exit code & stdout; **error kompilasi** 6 bahasa; stdin & argumen; **timeout**; **pembatalan**; **batas RAM**; streaming WebSocket; pratinjau HTML & traversal di pratinjau |
| test_services.py | terminal PTY via WebSocket, database (read/write/konfirmasi/skema/CSV/backup/ATTACH ditolak), Git (init/commit/log/branch/diff/validasi/remote/kredensial terenkripsi), **SSRF** (6 URL terlarang), koleksi HTTP, monitor, **backup + restore**, deteksi backup korup, proposal AI, kontrak OpenAPI |
| test_sandbox.py | (butuh bwrap) program tidak melihat `~/.ssh`, tidak bisa baca `/etc/shadow`, tidak ada jaringan, tidak bisa menulis di luar proyek; terminal tidak melihat `~/.ssh` |

Jalankan: `.venv/bin/python -m pytest -q -p no:logging backend/tests`

## Hasil aktual
- **Raspberry Pi 5 (ARM64, bwrap aktif)**: `52 passed` (50 test + 2 test sandbox) — semua 11 engine `AVAILABLE`.
- Cloud CI (`.github/workflows/backend.yml`, Ubuntu x86_64): dijalankan di setiap push.

## Android — `android/app/src/test/`
- `UnitTests.kt`: normalisasi URL server, parsing nomor build rilis, parser error compiler (gcc, Python traceback, javac, Go), decode `Job`.
- `BackendIntegrationTest.kt`: **uji kontrak API** terhadap backend asli (login, engines, dashboard, proyek, tree/read/write/search,
  run Python + polling, riwayat eksekusi, terminal, database, git, koleksi HTTP, AI status, backup, riwayat file). Dijalankan
  di CI (backend dinyalakan di runner) dan di Pi (`CS_SERVER_URL=http://127.0.0.1:8800`).

## Uji manual di HP (belum bisa diotomatisasi dari sini)
Alur: pasang APK → tambah server → login → buka proyek → edit `main.py` → simpan → ▶ → lihat output → Stop.
Ulangi untuk bahasa lain; terminal; Git push dengan token. Hasilnya dicatat di PROJECT_STATUS.md.
