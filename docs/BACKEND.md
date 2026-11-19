# Backend

FastAPI (Python 3.13 di Pi), uvicorn + websockets. Entry: `backend/main.py` (`create_app()`).

## Modul
| Modul | Isi |
|---|---|
| `config.py` | `Settings` dari env `CS_*` / `coding_server.env`; membuat direktori; secret key otomatis (0600) |
| `dependencies.py` | Kontainer `Services`, dependency `current_user`, `require(*perms)`, `project_dir()`, `ws_user()` |
| `core/security.py` | scrypt hash, JWT HS256 (access/refresh/preview, `jti` untuk pencabutan), `RateLimiter` |
| `core/permissions.py` | Peran: admin, developer, runner, viewer, ai; izin read/write/delete/execute/build/terminal/admin |
| `core/sandbox.py` | Bungkus perintah dengan bubblewrap + `preexec` rlimit (CPU, FSIZE, CORE, AS opsional, nice) |
| `core/process_manager.py` | `run_step()`: subprocess async, streaming, timeout, watchdog RSS, cancel, kill pohon proses |
| `core/job_queue.py` | Semaphore job bersamaan, batas antrean, tunda/tolak saat RAM < `CS_MIN_FREE_MEMORY_MB` |
| `services/*` | Logika domain (lihat ARCHITECTURE.md) |
| `database/db.py` | Metadata SQLite (users, projects, executions, audit_log, file_history, http_requests, git_credentials, ai_proposals, …) |

## Format error
Semua error: `{"error": {"code": "...", "message": "...", "details": ...}}` dengan status HTTP sesuai
(400/401/403/404/409/422/429/503). Contoh kode: `bad_credentials`, `token_expired`, `permission_denied`,
`path_forbidden`, `write_conflict`, `confirmation_required`, `queue_full`, `low_memory`, `engine_unavailable`, `ssrf_blocked`.

## Logging
`logs/server.log` (request + event, berputar 5×5 MB), `logs/audit.log` (aksi penting), tabel `audit_log`.
Token/password disensor (`core/logging.redact`); access log uvicorn dimatikan agar `?token=` WebSocket tidak tercatat.

## Menjalankan untuk pengembangan
```bash
.venv/bin/python -m uvicorn backend.main:app --reload --port 8800
.venv/bin/python -m pytest -q backend/tests
```
