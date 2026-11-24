# Tinjauan Keamanan — 24 Nov 2026

Melengkapi `docs/SECURITY.md` (daftar kontrol). Dokumen ini mencatat temuan, bukti, dan perbaikan.

## Diperbaiki

### S1 — Kebocoran isi file lewat symlink di pencarian (P0)
- **Masalah**: `FileService.search(content=True)` membaca setiap file teks dengan `read_text()`, yang mengikuti
  symlink. Terminal (sandbox) bisa membuat symlink ke path absolut di luar proyek; server (di luar sandbox) lalu
  membaca targetnya, mis. `~/.ssh/id_rsa`, dan mengembalikan barisnya di hasil pencarian.
- **Perbaikan**: pencarian isi melewati semua symlink. Pencarian nama tetap menampilkan symlink sebagai entri
  (`lstat`, tanpa membaca isi).
- **Uji**: `test_security_regressions.py::test_content_search_does_not_follow_symlink_outside_project`.

### S2 — DNS rebinding pada HTTP client (P0)
- **Masalah**: `check_destination` me-resolve DNS lalu httpx me-resolve ulang saat konek. Server DNS jahat bisa
  menjawab IP publik saat pemeriksaan lalu `127.0.0.1` saat koneksi → akses ke API lokal, llama-server, dsb.
- **Perbaikan**: `GuardedBackend` (backend jaringan httpcore) me-resolve sekali, memeriksa **semua** IP, lalu
  konek ke IP yang sudah diperiksa itu. SNI/Host tetap nama asli. Berlaku untuk setiap koneksi, termasuk tiap
  lompatan redirect. Bila internal httpx berubah dan backend tak bisa dipasang → request ditolak (fail-closed).
- **Uji**: `test_http_client_blocks_dns_rebinding` (resolusi ke-1 publik, ke-2 loopback → 403 `ssrf_blocked`).
  Tanpa perbaikan, uji yang sama gagal (request sampai ke server lokal).

### S3 — Klasifikasi IP tidak lengkap (P0)
- IPv4-mapped IPv6 (`::ffff:127.0.0.1`) dinilai sebagai IPv4-nya (Python 3.12 di CI tidak melakukannya sendiri),
  NAT64 `64:ff9b::/96`, 6to4, dan CGNAT `100.64.0.0/10` (diperlakukan privat), zona IPv6 (`%eth0`) dibuang.
- **Uji**: `test_ssrf_classify[...]`.

### S4 — Auto-apply AI tanpa batas risiko (P1)
- Perubahan AI kini diberi risiko LOW/MEDIUM/HIGH (`backend/services/ai_risk.py`). HIGH tidak pernah diterapkan
  otomatis (chat maupun agen) dan persetujuannya butuh `confirm_high_risk=true` (409
  `high_risk_confirmation_required` bila tidak). APK menampilkan alasan risiko dan dialog konfirmasi.
- **Uji**: `test_ai_risk.py`, `test_agent.py::test_agent_auto_apply_and_tool_errors`.

## Agen AI — batas keamanan
- Model tidak punya shell. Tool baca dibatasi ke proyek (path traversal & symlink lewat `FileService.resolve`).
- Tulis → proposal; hapus → tidak diizinkan untuk peran `ai`.
- Eksekusi lewat `ExecutionService` yang sama (sandbox fail-closed, antrean, batas RAM/CPU/waktu/output).
  Uji: tanpa bubblewrap & tanpa `CS_SANDBOX=none`, `run_tests` agen gagal dengan `sandbox_unavailable`, tidak
  berjalan di luar sandbox.
- Perintah uji disusun server dari hasil deteksi; argv dari model tidak pernah dieksekusi.
- Izin pemilik dibaca ulang dari DB setiap task berjalan/lanjut.

## Masih terbuka
| Temuan | Prioritas | Catatan |
|---|---|---|
| Pratinjau HTML satu origin dengan API (`connect-src *`) | P2 | Pindahkan ke origin/port terpisah atau sandbox iframe |
| Rate limiter API in-memory, kunci = 16 char terakhir token | P3 | Kunci per user id, batasi ukuran map |
| API key provider AI terenkripsi dengan kunci turunan secret server di disk yang sama | P3 | Wajar untuk satu Pi; dokumentasikan |
| Audit dependensi (pip-audit / gradle) belum di CI | P2 | Tambah job ringan terjadwal |
| Pemindaian secret di repo/CI belum ada | P2 | gitleaks di CI |
