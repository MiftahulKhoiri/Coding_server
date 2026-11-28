# Referensi API

Basis: `http://<pi>:8800`. Semua endpoint REST berprefix **`/api/v1`**. Kontrak lengkap (request/response
schema) tersedia sebagai **OpenAPI**: `GET /openapi.json`, UI: `/docs`. Android memakai kontrak yang sama
(`android/.../data/api/CodingApi.kt`, diuji otomatis terhadap backend asli di CI).

Autentikasi: header `Authorization: Bearer <access_token>`; WebSocket: query `?token=<access_token>`.
Error: `{"error":{"code","message","details"}}`.

| Method | Path | Izin | Keterangan |
|---|---|---|---|
| POST | /auth/login | publik (rate limit) | → access_token, refresh_token, user |
| POST | /auth/refresh | publik (rate limit) | refresh token sekali pakai (rotasi) |
| POST | /auth/logout | login | cabut access (+refresh) token |
| GET | /auth/me | login | user, izin & profil (`display_name`, `email`, `bio`, `is_root`, `last_login_at`) |
| PATCH | /auth/me | login | ubah profil sendiri (`display_name`, `email`, `bio`) |
| POST | /auth/password | login | ganti password sendiri (admin utama: 403 `root_protected`, ganti di server) |
| GET/POST/PATCH/DELETE | /auth/users[/{id}] | admin | kelola user & peran; admin utama dilindungi (403 `root_protected`); hanya admin utama yang boleh mengelola akun berperan admin; DELETE memindahkan proyek ke admin utama |
| GET | /system/health | publik | status backend, sandbox, db |
| GET | /system/info · /system/resources · /system/engines[?refresh=true] | login | data aktual Pi |
| GET | /system/processes · /system/audit | admin | proses teratas, audit log |
| GET | /monitor/dashboard | login | ringkasan untuk Dashboard APK |
| GET/POST | /projects | read / write | daftar / buat (`language` → template) |
| GET | /projects/templates | login | bahasa template |
| GET/PUT/DELETE | /projects/{project_id} | read / write / delete | |
| GET | /files/tree?project_id&path&depth | read | pohon folder |
| GET | /files/read?project_id&path | read | isi + sha256 (biner ditandai) |
| GET | /files/info · /files/search?q&content | read | |
| GET | /files/list?project_id | read | semua path file proyek (Buka file cepat; tanpa .git/node_modules/.venv) |
| POST | /files/grep `{project_id, query, regex, case_sensitive, whole_word}` | read | cari di seluruh proyek (maks. 1000) |
| POST | /files/replace `{… , replacement, paths?}` | write | ganti semua; tiap file tercatat di riwayat |
| POST | /files/format `{project_id, path, content, tab_size}` · GET /files/format/status | write / login | format kode di sandbox; mengembalikan teks |
| POST | /files/create | write | file/folder |
| PUT | /files/write | write | atomik; `expected_sha256` → 409 `write_conflict` bila berubah |
| POST | /files/rename · /files/copy · /files/move | write | |
| DELETE | /files/delete?recursive | delete | folder tidak kosong butuh `recursive=true` |
| GET | /files/history[/{id}] · POST /files/restore | read / write | riwayat versi & undo |
| GET/POST/DELETE | /files/favorites · GET /files/recent | login | |
| POST | /execution/run · /execution/build | execute / build | → 202 Job (`process_id`) |
| GET | /execution/install?project_id= | read | rencana instal dependensi yang terdeteksi + `.venv` proyek |
| POST | /execution/install | execute + write | `{project_id, kind?, packages?}` → 202 Job; pip → `.venv`, npm, go, composer; internet hanya untuk langkah ini (`CS_INSTALL_NETWORK`) |
| GET | /execution[?project_id] · /execution/{process_id} | login | riwayat / detail |
| POST | /execution/{process_id}/stop · /stdin | execute | batalkan / kirim input |
| GET/DELETE | /execution/artifacts/{project_id} | read / build | artefak build / bersihkan |
| POST | /preview/token?project_id&path | read | URL pratinjau HTML (1 jam) |
| POST/GET | /terminal/sessions | terminal | buat / daftar sesi |
| DELETE | /terminal/sessions/{session_id} | terminal | tutup sesi |
| GET | /database/list · /database/schema · /database/export | read | |
| POST | /database/create · /database/import | write | |
| POST | /database/query | read atau write | `mode`, `confirm` untuk destruktif |
| POST | /database/backup | read | salinan terverifikasi |
| GET | /git/status · /git/log · /git/branches · /git/diff | read | |
| GET | /git/head-file?project_id&path | read | isi file di HEAD (penanda baris berubah di editor) |
| GET | /auth/oauth/providers · GET/PUT /auth/oauth/config | login · system | penyedia login yang aktif / Client ID (root) |
| POST | /auth/identities/{github\|google}/link `{allow_push}` → `{flow_id, user_code, verification_uri}` | login | mulai device flow |
| GET | /auth/identities/flows/{flow_id} · GET /auth/identities · DELETE /auth/identities/{provider} | login | status, daftar, lepas |
| POST | /git/init · /git/add · /git/commit · /git/branch · /git/checkout · /git/remote · /git/pull · /git/push · /git/clone | write | |
| GET/POST/DELETE | /git/credentials | write | token terenkripsi |
| POST | /http/request | execute | anti-SSRF |
| GET/POST/DELETE | /http/collections[/{id}] | login / write | |
| GET/POST | /backup · GET /backup/{name}/verify · POST /backup/restore | admin | |
| GET | /ai/status | login | status model (idle/loading/ready/error), koneksi, parameter |
| GET | /ai/presets · /ai/connections | login | templat & koneksi (API key tidak pernah dikirim) |
| POST/PUT/DELETE | /ai/connections[/{id}] | admin | kelola koneksi lokal/online |
| GET | /ai/connections/{id}/models | execute | daftar model (status muat untuk llama-server) |
| POST | /ai/apply {connection_id, model, wait?} · /ai/unload | admin | terapkan / bongkar model |
| PUT | /ai/settings | admin | system prompt, temperature, max_tokens, idle_unload_minutes, history_messages |
| GET/POST/PATCH/DELETE | /ai/conversations[/{id}] | read | riwayat chat per pengguna |
| POST | /ai/chat | execute | chat tanpa streaming |
| POST/GET | /ai/proposals · /ai/proposals/{id}/decide | read / write | proposal perubahan file oleh AI |

## WebSocket
- `/ws/ai/chat?token=` — klien: `{type:"send", content, conversation_id?, project_id?, files?, editor_text?, editor_name?}`,
  `{type:"stop"}`; server: `{type:"conversation",id}`, `{type:"start",model}`, `{type:"reasoning",text}`,
  `{type:"delta",text}`, `{type:"done",message_id,seconds}`, `{type:"error",code,message}`, `{type:"stopped"}`.
- `/ws/execution/{process_id}?token=` — server: `{type:"status",status}`, `{type:"phase",phase,argv}`,
  `{type:"stdout"|"stderr",data}`, `{type:"end",job}`; klien: `{type:"stdin",data,eof?}`, `{type:"stop"}`.
- `/ws/terminal/{session_id}?token=` — klien: `{type:"input",data}`, `{type:"resize",cols,rows}`,
  `{type:"signal",signal:"SIGINT"}`, `{type:"ping"}`; server: `{type:"output",data}`, `{type:"exit",exit_code}`.

## Language server (LSP)
- `GET /api/v1/lsp/status` → ketersediaan per bahasa (`c`, `cpp` → clangd; `python` → pyright; `javascript`,
  `typescript` → typescript-language-server; `go` → gopls; `php` → intelephense; `html`, `css`, `json` →
  vscode-*-language-server; `shell` → bash-language-server) + sesi aktif (maks. `CS_LSP_MAX_SESSIONS`, bawaan 6).
- `WS /ws/lsp?project_id=&language=<bahasa di atas>&token=` — satu pesan WS = satu pesan JSON-RPC LSP.
  URI file memakai akar virtual `file:///workspace/<path>`; path asli server tidak pernah dikirim ke klien.
  Server mengirim `cs/ready` setelah language server berjalan, `cs/error` (`lsp_unavailable`, `lsp_busy`,
  `low_memory`, `permission_denied`) atau `cs/exit`. Butuh izin `read` + `execute`. Proses berjalan di sandbox
  bubblewrap (proyek read-only, tanpa jaringan), maks. `CS_LSP_MAX_SESSIONS` (default 4), ditutup bila idle 20 menit.

## AI: editan file
- Chat WS `/ws/ai/chat` dengan `project_id` → model diberi protokol edit; jawaban berisi blok
  ```` ```lang file=PATH ```` (isi lengkap) atau ```` ```edit file=PATH ```` (SEARCH/REPLACE) menghasilkan event
  `{type:"edits", message_id, items:[{id, path, status, diff, additions, deletions, new_file, error}]}`.
  `auto_apply: true` langsung menerapkan (butuh izin `write`).
- Setiap proposal punya `risk` (LOW/MEDIUM/HIGH), `risk_reasons`, `task_id`. Auto-apply tidak pernah menerapkan HIGH.
- `GET /api/v1/ai/proposals?project_id=&conversation_id=&task_id=` · `POST /api/v1/ai/proposals/{id}/decide {project_id, approve, confirm_high_risk?}`
  (409 `high_risk_confirmation_required` bila menyetujui HIGH tanpa `confirm_high_risk=true`)
  (409 `proposal_stale` bila file berubah sejak usulan dibuat) · `POST /api/v1/ai/proposals/{id}/revert {project_id}`
  (kembalikan isi lama / hapus file baru; 409 bila file sudah diubah lagi).

## AI Agent
Lihat `docs/AI_AGENT.md`. Ringkas: `POST /agent/tasks {project_id, description, title?, auto_apply?, max_steps?}` →
task berjalan di server; `GET /agent/tasks[?project_id=&status=]`, `GET /agent/tasks/{id}` (rencana & laporan),
`GET /agent/tasks/{id}/events?after=` (log, polling), `GET /agent/tasks/{id}/proposals`,
`POST /agent/tasks/{id}/pause|resume|cancel`, `DELETE /agent/tasks/{id}`, `GET /agent/tools`.
Status: PENDING, PLANNING, INSPECTING, EXECUTING, WAITING_APPROVAL, BUILDING, TESTING, REVIEWING, FIXING,
COMPLETED, FAILED, CANCELLED, PAUSED.
