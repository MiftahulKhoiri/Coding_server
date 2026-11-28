# PROJECT_STATUS — CODING_SERVER 1.6.0

Terakhir diperbarui: 28 Nov 2026. Status berdasarkan uji nyata di Raspberry Pi 5 (aarch64), CI GitHub, dan
pemakaian APK oleh pemilik proyek di HP.

**Status proyek: SELESAI.** 1.6.0 menyempurnakan fungsi utama aplikasi: **Code Editor sebagai IDE** (lihat
docs/CHANGELOG.md). Pengembangan berikutnya hanya perbaikan bug. Pekerjaan rumah tercatat di bawah.

## Lingkungan server aktual
Raspberry Pi 5 Model B · Debian 13 (trixie) aarch64 · kernel 6.18 · 16 GB RAM · NVMe ·
Python 3.13 · service `coding-server` (systemd **user**, linger aktif → auto-start saat boot) · port **8800** ·
sandbox **bubblewrap aktif** · `llama-server` (systemd sistem, mode router, `--models-preset`, port 8080).

## Definition of Done
| Kriteria | Status | Bukti |
|---|---|---|
| Backend berjalan di Pi 5 & otomatis saat boot | ✅ | `scripts/status.sh`; service user enabled + linger |
| APK dibangun & dipasang di HP | ✅ | CI → Release `android-latest`; dipakai & diuji pemilik di HP |
| Login, profil, admin utama terkunci | ✅ | test_auth, test_profiles; uji manual di APK |
| Izin per kelompok & menu tersembunyi | ✅ | test_profiles::test_permission_groups, test_extra_perms_guard; build APK CI |
| Project & file manager | ✅ | test_files + uji kontrak |
| Editor (CodeMirror) — tombol ekstra, simpan otomatis, tab dipulihkan, snippet, penanda Git, masalah | ✅ | web_editor/test (15 kasus di Chromium headless, juga di CI) + UnitTests Android |
| LSP 11 bahasa (C/C++, Python, JS/TS, Go, PHP, HTML, CSS, JSON, Bash): diagnostik, completion, definisi, referensi, rename, signature | ✅ | test_lsp (server asli di Pi) |
| Format kode (clang-format, ruff, prettier, gofmt) | ✅ | test_format |
| Cari & ganti seluruh proyek, buka file cepat, isi HEAD Git | ✅ | test_files::test_grep_and_replace_all, test_list_files_for_quick_open, test_services::test_git_head_file |
| Terminal interaktif, output real-time | ✅ | test_terminal_*, test_output_streaming_ws |
| 11 engine bahasa, build C/C++ multi-file | ✅ | test_run_language, test_engines |
| Instal dependensi di sandbox | ✅ | test_deps_install; uji di Pi (pip ke `.venv`) |
| Git, SQLite, HTTP client (anti-SSRF), monitor | ✅ | test_git_flow, test_database_manager, test_http_ssrf_blocked, test_system_monitor |
| Backup & restore | ✅ | test_backup_and_restore, test_backup_includes_avatars_and_root_password |
| Keamanan workspace & sandbox | ✅ | traversal, symlink, isolasi user, uji sandbox bwrap |
| AI Chat + proposal perubahan file | ✅ | test_ai, test_ai_edits, test_ai_risk; dipakai di APK |
| Model AI: konteks, lepas/paksa lepas, Uji Model, profil | ✅ | test_llama_context, test_agent::test_force_unload_all_pauses_running_agent_task, test_agent_models |
| AI Agent (loop, jeda/lanjut, checkpoint, cek otomatis, gerbang finish) | ✅* | test_agent (model palsu, 22 skenario); task nyata di Pi berjalan & berhenti dengan benar |
| Dokumentasi | ✅ | README.md (final) + docs/ (18 file) + CHANGELOG 1.5.0 |

`*` = mekanisme agent teruji; keberhasilan menyelesaikan tugas besar bergantung pada kemampuan model lokal.

## Hasil uji aktual (28 Nov 2026)
- **1.6.0 di Pi 5**: 189 tes backend lulus (termasuk 13 uji LSP dengan server asli dan uji format), 15 uji editor di
  Chromium headless, unit test Android; CI Backend tests ✅ & Android APK ✅ untuk setiap paket.
- **Backend di Pi 5 (1.5.0)**: 171 tes (pytest) lulus, termasuk uji sandbox bwrap asli dan LSP nyata.
- **CI GitHub**: Backend tests ✅, Android APK ✅ (rilis `android-latest`).
- **APK**: diuji pemilik seharian di HP — profil, foto, tema, editor, terminal, AI Agent, izin.
- **Install → pakai → uninstall bersih (28 Nov 2026, Pi 5)** dari clone baru GitHub v1.5.0 di folder terpisah
  (`CS_PORT=8811`, `CS_SERVICE_NAME=coding-server-test`), server utama tetap berjalan:
  - `./scripts/install.sh` selesai 54 dtk, exit 0: cek OS/Python/git/bwrap, venv + paket, runtime (.NET, PHP,
    clangd, pyright), 11 engine AVAILABLE, sandbox AVAILABLE, systemd --user enabled + linger, health OK,
    sandi admin utama ditampilkan.
  - Uji fungsi: health 1.5.0 sandbox=True, login admin, buat proyek, jalankan Python di sandbox
    (COMPLETED, exit 0, output benar), buat akun Developer (izin sesuai), backup terverifikasi.
  - Skrip kontrol: `status`, `stop`, `start`, `restart`, `admin_password.sh` berfungsi; proses dibunuh paksa
    (`kill -9`) → systemd menghidupkan lagi otomatis.
  - `./scripts/uninstall.sh --purge --dry-run` menampilkan langkah tanpa mengubah apa pun;
    `./scripts/uninstall.sh --remove-repo -y`: backup akhir terverifikasi di `~`, service + unit + symlink autostart
    dihapus, proses berhenti, venv/log/cache/data/.env dihapus, folder repo hilang. Sesudahnya: port 8811 bebas,
    tidak ada proses/unit tersisa, crontab & unit lain (gameserver, coding-server utama) tidak berubah.

## Pekerjaan rumah (masa depan)
0. **Coba fitur IDE 1.6.0 di HP** (tombol ekstra, format, rename, cari di proyek, penanda Git): sudah diuji otomatis
   (backend, Chromium headless, kompilasi & unit test Android), belum disentuh langsung di layar HP.
1. **Uji panjang AI Agent dengan model asli**: 1 model untuk semua peran, konteks 16K, ulangi task contoh
   "dasbor login/register/lupa sandi" sampai selesai. Butuh waktu lama di Pi (model lokal ±1–5 token/detik).
2. Opsional: service sistem dengan user khusus (`sudo ./scripts/install_systemd.sh`), reverse proxy HTTPS / VPN
   untuk akses dari luar rumah.

## Kunci tanda tangan APK (jangan dibuat baru)
APK resmi **sudah** ditandatangani kunci rilis tetap (CI: `SIGNING: release`), alias `codingserver`, berlaku sampai
2081, SHA-256 `1F:09:AC:44:E1:2C:E9:BB:F1:BD:0E:8D:69:F8:19:B1:D7:3F:0D:22:2C:E7:72:4E:85:B7:DB:C5:A4:83:5C:92`.
- Kunci terenkripsi di repo: `android/signing/release.jks.enc`; dibuka CI dengan secret `ANDROID_KEYSTORE_PASSWORD`.
- Salinan asli di Pi: `~/.coding_server_signing/release.jks` + `ANDROID_KEYSTORE_PASSWORD` (izin 0600).
- Pengembangan berikutnya cukup push ke `main`; APK baru otomatis bisa memperbarui yang terpasang.
- Kunci baru = Android menolak update ("tanda tangan beda") dan aplikasi harus dihapus dulu (data lokal hilang).
- Simpan salinan cadangan sandi kunci di luar Pi (pengelola sandi). Bila sandi & file hilang, kunci tidak bisa dipulihkan.

## Catatan jujur
- Build APK lokal di Pi membutuhkan aapt2 ARM64 (`-Pandroid.aapt2FromMavenOverride=...`, lihat README); build resmi
  selalu dari CI.
- Model lokal kecil bisa gagal pada tugas besar; agent kini berhenti dengan aman (jeda/gagal dengan laporan) dan bisa
  dilanjutkan dengan **Ulangi** / **Lanjutkan**.
