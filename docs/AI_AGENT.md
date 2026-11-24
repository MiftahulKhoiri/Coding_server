# AI Coding Agent

Agen mengubah AI dari chatbot menjadi pekerja yang menyelesaikan tugas di proyek nyata, di bawah izin dan
persetujuan pengguna. Kode: `backend/services/agent_service.py`, `agent_tools.py`, `ai_risk.py`,
`test_detect.py`, API `backend/api/agent.py`, Android `ui/agent/AgentScreen.kt`.

## Alur
```
POST /agent/tasks {project_id, description, auto_apply?}
 └─ AgentService.create → baris agent_tasks (PENDING) → asyncio task (semaphore CS_AGENT_MAX_CONCURRENT=1)
    └─ loop: kirim percakapan ke model aktif → balasan JSON {"thought","tool","args"} (+ blok kode opsional)
       → validasi skema & izin tool → jalankan → simpan event + checkpoint → hasil tool kembali ke model
       Tahap: PLANNING (update_plan) · INSPECTING (baca/cari) · EXECUTING/FIXING (proposal edit)
              BUILDING/TESTING (eksekusi di sandbox) · REVIEWING (git) · finish → laporan
```
Format JSON sengaja tidak bergantung pada fitur "tool calling" penyedia, sehingga model lokal kecil di
llama-server juga bisa. Isi file boleh ditulis di blok kode setelah JSON agar model tidak perlu meng-escape kode.

## Tool
| Tool | Izin | Keterangan |
|---|---|---|
| project_info, list_dir, read_file, search, list_tests | read | Inspeksi. `read_file` memberi nomor baris, maks 400 baris/panggilan |
| update_plan | read | Rencana: id, deskripsi, file, dependensi, risiko, verifikasi, status |
| write_file, edit_file | write | Selalu menjadi **proposal** di Approval Center (dengan diff & risiko) |
| delete_file | delete | Peran `ai` tidak punya `delete` → selalu ditolak untuk agen |
| build_file, run_file | build / execute | Lewat `ExecutionService.submit` (antrean, sandbox fail-closed, batas RAM/CPU/waktu) |
| run_tests | execute | Perintah uji **disusun server** dari deteksi (pytest/unittest, go test, npm test, make test); model hanya memilih `id` |
| git_status, git_diff | read | Baca saja |
| finish | read | Ringkasan, keterbatasan, sisa pekerjaan |

Izin agen = irisan hak pemilik task ∩ peran `ai`, dibaca ulang dari DB setiap kali task berjalan (izin yang dicabut
langsung berlaku). Hasil tool dipotong (12 000 karakter) sebelum dikirim ke model.

## Persetujuan
- Tanpa auto-apply: setiap editan menunggu persetujuan. Saat agen ingin build/run/test sementara masih ada proposal
  pending, task berstatus **WAITING_APPROVAL** dan berhenti; setelah semua proposal diputuskan (setujui/tolak),
  task **lanjut otomatis** dari checkpoint.
- Auto-apply: editan LOW/MEDIUM langsung diterapkan (tercatat, bisa dibatalkan); **HIGH tidak pernah otomatis**.
- Risiko (`ai_risk.py`): HIGH untuk hapus file, skrip shell, Dockerfile/systemd/.env, folder `.github`/`migrations`/
  `deployment`, path terkait auth/izin/secret, dan baris baru yang memanggil shell/proses, jaringan, SQL destruktif,
  `eval`/`pickle`. LOW untuk dokumentasi atau perubahan spasi saja. Selain itu MEDIUM.
  Menyetujui HIGH butuh `confirm_high_risk: true` (APK menampilkan dialog konfirmasi).

## Persistensi & pemulihan
- `agent_tasks` (status, tahap, progres, rencana, laporan, checkpoint percakapan) dan `agent_events` (log).
- Restart server: task yang sedang berjalan menjadi **PAUSED** (tidak hilang) dan bisa dilanjutkan dari checkpoint.
- Batas: `max_steps` per task (default 30, maks `CS_AGENT_MAX_STEPS`=60), `CS_AGENT_MODEL_TIMEOUT` (600 dtk per jawaban),
  `CS_AGENT_TASK_TIMEOUT` (7200 dtk per sesi). 3 balasan berturut-turut tanpa JSON valid → FAILED.
- Batalkan: tugas asyncio dibatalkan; job eksekusi yang sedang berjalan ikut dihentikan.
- Konteks: hasil tool lama dipangkas bila percakapan > 48 000 karakter; file asli tetap sumber kebenaran (agen
  diminta membaca ulang).

## Laporan
`report.verified` dihitung server dari data nyata (proposal per task, hasil eksekusi & uji dengan exit code).
`report.ai_generated` adalah ringkasan dari model dan ditandai demikian di APK ("belum tentu akurat").

## API
| Method | Path | Izin |
|---|---|---|
| GET | /agent/tools | login — daftar tool + `allowed` |
| POST | /agent/tasks | execute (+ akses proyek, model harus siap) |
| GET | /agent/tasks?project_id=&status= | read |
| GET | /agent/tasks/{id} | read (pemilik/admin) |
| GET | /agent/tasks/{id}/events?after= | read — polling log |
| GET | /agent/tasks/{id}/proposals | read |
| POST | /agent/tasks/{id}/pause · /resume · /cancel | execute |
| DELETE | /agent/tasks/{id} | execute (task tidak aktif) |

## Keterbatasan
- Kualitas hasil bergantung pada model; model lokal kecil sering perlu langkah lebih banyak.
- Satu task aktif sekaligus secara default (RAM Pi + model lokal).
- `run_tests` butuh framework uji terpasang di runtime sistem (mis. `pytest` di `python3` sistem); bila tidak,
  `unittest` dipakai.
- Belum ada streaming WebSocket untuk log agen (APK melakukan polling 2–4 detik selama task aktif).
