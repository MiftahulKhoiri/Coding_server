# Status Fitur (diverifikasi dari kode & uji, 24 Nov 2026)

✅ berfungsi & teruji · 🟡 sebagian · ❌ belum ada. "Uji" = uji otomatis yang menutupinya.

| Area | Fitur | Status | Bukti / catatan |
|---|---|---|---|
| Workspace | Proyek CRUD, explorer, file CRUD, riwayat & restore | ✅ | `test_files.py` |
| Workspace | Pencarian nama/isi per proyek | 🟡 | Aman terhadap symlink (S1). Belum regex, case-sensitive, eksklusi, lintas proyek |
| Workspace | Editor CodeMirror 6, LSP clangd/pyright | ✅ | `test_lsp.py`; LSP lain belum |
| Development | Run/build 11 bahasa di sandbox, stdin, stop, streaming | ✅ | `test_engines.py`, `test_sandbox.py` (butuh bwrap) |
| Development | Terminal PTY multi-sesi | ✅ | `test_services.py` |
| Development | Profil eksekusi (args/env/cwd per proyek) | ❌ | |
| Development | Debugger (breakpoint, step) | ❌ | Tidak ada; tidak disimulasikan |
| Development | Testing Center (UI) | ❌ | Fondasi ada: `test_detect.py` + `ExecutionService.submit_command` |
| Development | Project Analyzer | 🟡 | Hanya `project_info` agen (bahasa, file build, perintah uji) |
| AI | Chat streaming, riwayat, model lokal/online, load/unload, idle unload | ✅ | `test_ai.py` |
| AI | Proposal edit dari chat, terapkan/tolak/batalkan | ✅ | `test_ai_edits.py` |
| AI | Risiko proposal LOW/MEDIUM/HIGH, konfirmasi HIGH | ✅ | `test_ai_risk.py` · APK: label & dialog |
| AI | **Agent Tasks**: rencana, tool ber-izin, edit via proposal, build/run/test di sandbox, perbaikan berulang, laporan | ✅ | `test_agent.py` (model palsu). Dengan model asli di Pi: **belum diuji** |
| AI | Task persisten, pause/resume, cancel, retry, pemulihan restart | ✅ | `test_agent.py` |
| AI | Konteks: pangkas hasil lama, file sebagai sumber kebenaran | 🟡 | Tanpa ringkasan/indeks simbol |
| Project tools | Git status/diff/log/branch/commit/checkout/pull/push/clone | ✅ | `test_services.py` |
| Project tools | Git stash, konflik, blame, AI commit message | ❌ | |
| Project tools | Database SQLite manager | ✅ | `test_services.py` |
| Project tools | HTTP client + koleksi, anti-SSRF termasuk DNS rebinding | ✅ | `test_security_regressions.py` |
| Project tools | Deployment Manager | ❌ | |
| Server | Monitor (CPU/RAM/disk/suhu/proses) | 🟡 | Snapshot; tanpa riwayat/alarm |
| Server | Backup & restore terverifikasi, retensi, jadwal | ✅ | `test_services.py` |
| Server | Security Center (UI) | ❌ | |
| System | Login, user & peran, token rotasi | ✅ | `test_auth.py` |
| Android | Navigasi berkelompok, tema gelap/terang/AMOLED | ✅ | Build & unit test di CI; uji layar di HP: pengguna |
| Android | Layar Agent Tasks (daftar, buat, rencana, log, perubahan + approve, laporan, jeda/lanjut/batal) | ✅ | Kompilasi & uji decode di CI; belum diuji di HP fisik dari sesi ini |
| Android | Auto-update dari GitHub Releases | ✅ | CI |
