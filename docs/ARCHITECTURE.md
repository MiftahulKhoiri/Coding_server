# Arsitektur

Prinsip utama: **Raspberry Pi = server utama & mesin eksekusi; Android = klien**. Proyek, compiler,
runtime, database, Git, terminal dan log semuanya di Pi. APK tidak menyimpan proyek.

## Lapisan
| Lapisan | Lokasi | Tanggung jawab |
|---|---|---|
| Server layer | `backend/main.py`, `backend/api/*`, `backend/middleware/*` | Routing REST `/api/v1`, WebSocket `/ws/*`, validasi (Pydantic), autentikasi, format error seragam, OpenAPI |
| Service layer | `backend/services/*` | Logika: file, proyek, eksekusi, terminal, build, database, git, http, monitor, backup, ai, auth |
| Engine layer | `backend/engines/*` | Satu kelas per bahasa, turunan `BaseEngine` (`language_id`, `extensions`, `validate_environment()`, `get_version()`, `detect_project()`, `build_steps()`, `run_steps()`, `get_status()`), didaftarkan di `registry.py` |
| Core | `backend/core/*` | Keamanan (scrypt, JWT, rate limit), izin, sandbox (bwrap + rlimit), process manager (timeout, watchdog RAM, cancel), job queue, logging |
| Storage | `workspace/`, `logs/`, `backups/` | Data proyek, DB pengguna, metadata SQLite, riwayat file, cache compiler |
| Android client | `android/` | Kotlin + Jetpack Compose; editor & terminal di WebView (CodeMirror 6, xterm.js dari `web_editor/`) |

## Alur eksekusi (contoh `main.py`)
```
APK  POST /api/v1/execution/run {project_id, path}
 └─ API: validasi token & izin 'execute' → cek proyek milik user
    └─ ExecutionService.submit: validasi path di workspace → pilih engine → cek status engine
       → buat Job (QUEUED, tersimpan di DB) → task asyncio
          └─ JobQueue.acquire (batas job bersamaan, cek RAM bebas)
             → untuk tiap step (build lalu run): sandbox.wrap(bwrap) + rlimit → process_manager.run_step
                → output di-stream ke subscriber WebSocket /ws/execution/{id} + disimpan (dibatasi)
          → status akhir COMPLETED/FAILED/TIMEOUT/CANCELLED, exit_code, durasi → DB
APK  WS /ws/execution/{id}?token=...  ← {type: status|phase|stdout|stderr|end}
```

## Struktur direktori aktual
```
coding_server/
├── backend/            main.py, config.py, dependencies.py
│   ├── api/            auth, system, monitor, projects, files, execution, terminal, database, git,
│   │                   http_client, backup, ai, preview
│   ├── core/           security, permissions, exceptions, logging, process_manager, job_queue, sandbox, git_askpass.sh
│   ├── services/       file, project, execution, terminal, build, database, git, http, monitor, backup, ai, auth, secret_store
│   ├── engines/        base_engine, registry, python, javascript, php, go, c, cpp, java, csharp, sql (+sql_runner), web, shell
│   ├── schemas/        models.py (kontrak request/response)
│   ├── database/       db.py (metadata SQLite, WAL)
│   ├── middleware/     request_log.py
│   └── tests/          pytest (auth, files, engines, services, sandbox)
├── android/            aplikasi Android (Gradle, Compose)
├── web_editor/         sumber CodeMirror 6 & xterm.js → dist/*.html (juga disalin ke aset Android)
├── workspace/          projects/, database/, metadata/, history/, data/, cache/   (runtime, tidak di-commit)
├── logs/  backups/     (runtime)
├── scripts/            install, start, stop, restart, status, health_check.py, backup.py, install_systemd.sh,
│                       install_user_systemd.sh, install_runtimes.sh, run_server.sh, common.sh
├── deployment/         systemd/coding-server.service.template, configuration/coding_server.env.example
├── docs/               dokumentasi ini
└── .github/workflows/  backend.yml (pytest), android.yml (APK + GitHub Release)
```

## Keputusan teknis
- **SQLite tanpa ORM** untuk metadata: ringan untuk Pi, WAL mode, satu file mudah di-backup.
- **bubblewrap** sebagai sandbox: tersedia di Debian ARM64, tidak butuh root/daemon, overhead kecil (lebih ringan dari container per eksekusi).
- **Watchdog RSS** selain `RLIMIT_AS`: JVM, V8, Go dan .NET memesan ruang alamat virtual sangat besar sehingga `RLIMIT_AS` membuat mereka gagal start; batas RAM untuk runtime tersebut ditegakkan watchdog (dan `-Xmx`, `--max-old-space-size`, `GCHeapHardLimit`).
- **CodeMirror 6** (bukan Monaco) karena jauh lebih ringan di WebView Android.
