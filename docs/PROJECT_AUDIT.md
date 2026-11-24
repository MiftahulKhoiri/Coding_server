# Audit Proyek CODING_SERVER

Tanggal: 24 Nov 2026 · Basis: commit `d30bd67` (v1.3.0) · Dibuat dari pembacaan kode, bukan dari dokumentasi.

Prioritas: **P0** kritis (keamanan/data/inti rusak) · **P1** penting untuk platform matang · **P2** produktivitas/UX ·
**P3** opsional.

## Cakupan audit sesi ini
Dibaca menyeluruh: `backend/main.py`, `config.py`, `dependencies.py`, `core/` (security, sandbox, permissions,
job_queue), `database/db.py`, `services/` (execution, file, http, ai_service, ai_edits, ai_providers, git — sebagian),
`api/` (execution, preview, backup, terminal, ai, files, http_client), Android `MainActivity`, layar AI Chat,
model & klien API, workflow CI. **Belum diaudit ulang secara mendalam** (dipercaya dari uji yang ada): terminal_service,
lsp_service, database_service, backup_service, monitor_service, skrip instalasi, web_editor.

Baseline uji sebelum perubahan: `67 passed, 6 skipped` (pytest, `CS_SANDBOX=none` di mesin tanpa bubblewrap).

## Temuan

| # | Subsistem | Temuan | Prioritas | Status |
|---|---|---|---|---|
| 1 | File search | Pencarian isi (`/files/search?content=true`) membaca file **lewat symlink**. Symlink yang dibuat dari terminal (`ln -s ~/.ssh/id_rsa x.py`) membocorkan isi file di luar proyek ke hasil pencarian. Terbukti dengan uji regresi. | P0 | **Diperbaiki** |
| 2 | HTTP client | Perlindungan SSRF hanya "cek lalu sambung": DNS di-resolve saat validasi lalu di-resolve lagi oleh httpx → **DNS rebinding** ke 127.0.0.1 lolos. Terbukti dengan uji (tanpa perbaikan request sampai ke server lokal). | P0 | **Diperbaiki** |
| 3 | HTTP client | `classify()` tidak menangani IPv4-mapped IPv6 di Python < 3.13 (CI memakai 3.12), NAT64 (`64:ff9b::/96`), 6to4, dan CGNAT `100.64.0.0/10`. | P0 | **Diperbaiki** |
| 4 | AI proposal | Tidak ada klasifikasi risiko; auto-apply menerapkan apa saja (skrip shell, workflow CI, file auth) tanpa konfirmasi. | P1 | **Diperbaiki** (LOW/MEDIUM/HIGH, HIGH tak pernah auto-apply & butuh `confirm_high_risk`) |
| 5 | AI | Hanya chat + proposal; **tidak ada agen** yang bisa merencanakan, memeriksa proyek, menjalankan uji, memperbaiki berulang, dan melapor. Tidak ada task persisten. | P1 | **Diimplementasikan** (lihat `docs/AI_AGENT.md`) |
| 6 | Dokumentasi | `docs/SECURITY.md` menyatakan `CS_SANDBOX=auto` jatuh ke mode tanpa sandbox; kode sebenarnya **fail-closed** (`require_sandbox` di eksekusi, terminal, git, LSP). | P2 | **Diperbaiki** |
| 7 | Android navigasi | 14 menu datar tanpa pengelompokan. | P2 | **Diperbaiki** (seksi WORKSPACE / DEVELOPMENT / AI DEVELOPMENT / PROJECT TOOLS / SERVER / SYSTEM) |
| 8 | Eksekusi | Tidak ada jalur menjalankan perintah uji proyek (pytest, go test, …) selain lewat terminal. | P1 | **Sebagian**: `ExecutionService.submit_command` + deteksi uji (dipakai agen). Testing Center UI belum. |
| 9 | Preview | Pratinjau HTML disajikan dari origin yang sama dengan API, CSP `connect-src *`. Token API tidak bisa dibaca halaman (disimpan di app), jadi risikonya rendah, tetapi origin terpisah lebih aman. | P2 | Terbuka |
| 10 | Rate limit | Limiter API dikunci dengan 16 karakter terakhir token, disimpan di memori (hilang saat restart, tidak dibatasi ukurannya). | P3 | Terbuka |
| 11 | Global search | Pencarian hanya per proyek, tanpa regex/case-sensitive/eksklusi, tanpa melewati file biner berdasarkan isi. | P2 | Terbuka |
| 12 | Run & Debug | Tidak ada profil eksekusi, env var per proyek, maupun debugger nyata. | P2 | Terbuka |
| 13 | Monitoring | Snapshot saja; tidak ada riwayat/ambang alarm. | P2 | Terbuka |
| 14 | Database | Skema bermigrasi lewat ALTER kolom idempoten; tidak ada backup otomatis sebelum migrasi. Migrasi v2→v3 sesi ini hanya menambah kolom/tabel (aman, diuji pada DB lama). | P2 | Terbuka |
| 15 | APK | Belum diuji di perangkat fisik dari sesi ini; build & unit test diverifikasi lewat CI. | P1 | Butuh verifikasi manual |

## Yang sudah baik (diverifikasi di kode)
- Sandbox bubblewrap fail-closed untuk eksekusi, terminal, git, LSP; `$HOME` tmpfs, jaringan diputus default.
- Path: normalisasi, tolak `..`, cek setiap komponen symlink, tulis atomik `O_NOFOLLOW`, deteksi konflik SHA-256.
- Backup restore memakai `tarfile` `filter="data"` + verifikasi manifest.
- Token: refresh sekali pakai, `jti` bisa dicabut, scrypt untuk password.
- AI: hak = irisan hak pengguna ∩ peran `ai`; proposal basi ditolak; revert memeriksa SHA.
