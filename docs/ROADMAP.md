# Roadmap

Diperbarui 24 Nov 2026. Urutan mengikuti dampak dan ketergantungan. Lihat `PROJECT_AUDIT.md` untuk temuan.

## Milestone 1 — Stabilisasi ✅ (sesi ini)
- [x] Audit kode (`PROJECT_AUDIT.md`, `SECURITY_REVIEW.md`, `FEATURE_STATUS.md`)
- [x] P0: kebocoran symlink di pencarian isi, DNS rebinding & klasifikasi IP di HTTP client (+ uji regresi)
- [x] Dokumentasi sandbox diselaraskan dengan perilaku fail-closed

## Milestone 2 — Fondasi AI Agent ✅ (sesi ini)
- [x] Task persisten (`agent_tasks`, `agent_events`), checkpoint, pemulihan saat restart
- [x] Tool registry dengan skema, validasi, izin, timeout
- [x] Rencana terstruktur, cancel/pause/resume/retry, batas langkah & waktu, satu task aktif (RAM)
- [x] Approval Center: risiko LOW/MEDIUM/HIGH, konfirmasi HIGH, auto-apply terbatas
- [x] APK: layar Agent Tasks, label risiko + dialog konfirmasi di AI Chat, navigasi berkelompok

## Milestone 3 — Agen otonom (lanjutan)
- [ ] **Uji agen dengan model asli di Pi 5** (llama-server) dan catat tingkat keberhasilan per model
- [ ] Streaming log agen lewat WebSocket (ganti polling)
- [ ] Indeks simbol ringan (ctags/regex) + ringkasan file tersimpan untuk proyek besar
- [ ] Review diri: agen membaca `git diff` semua proposal sebelum finish
- [ ] Setujui sebagian (per hunk)

## Milestone 4 — IDE profesional
- [ ] Testing Center (UI di atas `test_detect` + `submit_command`, riwayat hasil)
- [ ] Global search: regex, case-sensitive, eksklusi, lintas proyek
- [ ] Run profiles per proyek (args, env, cwd, timeout)
- [ ] Project Analyzer (dependensi, entry point, TODO/FIXME, temuan terkonfirmasi vs hipotesis)
- [ ] LSP opsional tambahan (gopls, typescript-language-server) setelah ukur RAM di Pi

## Milestone 5 — Manajemen server
- [ ] Riwayat monitor ringan + ambang alarm
- [ ] Security Center (status sandbox, audit log, konfigurasi)
- [ ] Backup per proyek & enkripsi
- [ ] Deployment Manager (hanya systemd user service yang terdeteksi)

## Milestone 6 — Polish
- [ ] pip-audit + gitleaks di CI
- [ ] Pratinjau HTML di origin terpisah
- [ ] Uji UI Compose (navigasi, layar agen)

## Langkah berikutnya yang tepat
Pasang APK baru di HP, terapkan model di menu Model AI, buat task agen kecil pada proyek Python
(mis. "perbaiki bug dan jalankan test"), lalu catat hasil & masalahnya — itu menentukan prioritas Milestone 3.
