# PROJECT_STATUS — CODING_SERVER 1.5.0 (rilis stabil)

Terakhir diperbarui: 28 Nov 2026. Status berdasarkan uji nyata di Raspberry Pi 5 (aarch64), CI GitHub, dan
pemakaian APK oleh pemilik proyek di HP.

**Status proyek: SELESAI (feature freeze).** Pengembangan berikutnya hanya perbaikan bug. Satu pekerjaan rumah
tercatat di bawah (uji panjang AI Agent dengan model asli).

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
| Editor (CodeMirror) + LSP clangd/pyright | ✅ | test_lsp (10× berturut-turut lulus setelah perbaikan) |
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
- **Backend di Pi 5**: 171 tes (pytest) lulus, termasuk uji sandbox bwrap asli dan LSP nyata.
- **CI GitHub**: Backend tests ✅, Android APK ✅ (rilis `android-latest`).
- **APK**: diuji pemilik seharian di HP — profil, foto, tema, editor, terminal, AI Agent, izin.

## Pekerjaan rumah (masa depan)
1. **Uji panjang AI Agent dengan model asli**: 1 model untuk semua peran, konteks 16K, ulangi task contoh
   "dasbor login/register/lupa sandi" sampai selesai. Butuh waktu lama di Pi (model lokal ±1–5 token/detik).
2. Secret `ANDROID_KEYSTORE_PASSWORD` di GitHub bila ingin tanda tangan rilis tetap (lihat docs/ANDROID.md).
3. Opsional: service sistem dengan user khusus (`sudo ./scripts/install_systemd.sh`), reverse proxy HTTPS / VPN
   untuk akses dari luar rumah.

## Catatan jujur
- Build APK lokal di Pi membutuhkan aapt2 ARM64 (`-Pandroid.aapt2FromMavenOverride=...`, lihat README); build resmi
  selalu dari CI.
- Model lokal kecil bisa gagal pada tugas besar; agent kini berhenti dengan aman (jeda/gagal dengan laporan) dan bisa
  dilanjutkan dengan **Ulangi** / **Lanjutkan**.
