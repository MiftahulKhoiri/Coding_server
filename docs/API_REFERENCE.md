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
| GET | /auth/me | login | user & izin |
| POST | /auth/password | login | ganti password |
| GET/POST/PATCH | /auth/users[/{id}] | admin | kelola user & peran |
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
| POST | /files/create | write | file/folder |
| PUT | /files/write | write | atomik; `expected_sha256` → 409 `write_conflict` bila berubah |
| POST | /files/rename · /files/copy · /files/move | write | |
| DELETE | /files/delete?recursive | delete | folder tidak kosong butuh `recursive=true` |
| GET | /files/history[/{id}] · POST /files/restore | read / write | riwayat versi & undo |
| GET/POST/DELETE | /files/favorites · GET /files/recent | login | |
| POST | /execution/run · /execution/build | execute / build | → 202 Job (`process_id`) |
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
| POST | /git/init · /git/add · /git/commit · /git/branch · /git/checkout · /git/remote · /git/pull · /git/push · /git/clone | write | |
| GET/POST/DELETE | /git/credentials | write | token terenkripsi |
| POST | /http/request | execute | anti-SSRF |
| GET/POST/DELETE | /http/collections[/{id}] | login / write | |
| GET/POST | /backup · GET /backup/{name}/verify · POST /backup/restore | admin | |
| GET | /ai/status · POST /ai/chat · /ai/proposals · /ai/proposals/{id}/decide | read / write | fondasi AI |

## WebSocket
- `/ws/execution/{process_id}?token=` — server: `{type:"status",status}`, `{type:"phase",phase,argv}`,
  `{type:"stdout"|"stderr",data}`, `{type:"end",job}`; klien: `{type:"stdin",data,eof?}`, `{type:"stop"}`.
- `/ws/terminal/{session_id}?token=` — klien: `{type:"input",data}`, `{type:"resize",cols,rows}`,
  `{type:"signal",signal:"SIGINT"}`, `{type:"ping"}`; server: `{type:"output",data}`, `{type:"exit",exit_code}`.
