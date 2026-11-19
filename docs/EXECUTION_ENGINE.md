# Execution Engine

## Engine & versi aktual (diuji di Raspberry Pi 5, 20 Nov 2026)
| Engine | Ekstensi | Build | Run | Versi di Pi |
|---|---|---|---|---|
| python | .py | `py_compile` (cek sintaks) | `python3 -u file` | Python 3.13.5 |
| javascript | .js .mjs .cjs | `node --check` | `node --max-old-space-size=N file` | v26.13.1 |
| php | .php | `php -l` | `php -d memory_limit=N file` | PHP 8.3.14 (static, ~/.local/opt/php) |
| go | .go | `go build -o build/app` (modul `go.mod` bila ada) | binary | go1.24.4 linux/arm64 |
| c | .c | `gcc -std=c17 -O2 -Wall -Wextra -lm` | binary | gcc 14.2.0 |
| cpp | .cpp .cc .cxx | `g++ -std=c++17 -O2 -Wall -Wextra` | binary | g++ 14.2.0 |
| java | .java | `javac -d build/classes` | `java -Xmx… -XX:+UseSerialGC -cp … Main` (paket dideteksi) | OpenJDK 21.0.13 |
| csharp | .cs | csproj sementara + `dotnet build` | `dotnet app.dll` | .NET SDK 8.0.428 (~/.dotnet) |
| sql | .sql | cek kelengkapan pernyataan | jalankan ke `<nama>.db` (atau `--db path`) & cetak tabel | SQLite 3.46.1 |
| web | .html .htm .css | – | URL pratinjau | browser |
| shell | .sh .bash | `bash -n` | `bash file` | bash 5.2.37 |

Status `AVAILABLE` hanya diberikan setelah perintah versi benar-benar berhasil dijalankan
(`GET /api/v1/system/engines?refresh=true`, atau `scripts/health_check.py --engines`).

## Sumber daya & keamanan per job
- Antrean: `CS_MAX_CONCURRENT_JOBS` (2) berjalan bersamaan, `CS_MAX_QUEUED_JOBS` (20) menunggu; lebih dari itu → 503 `queue_full`.
- RAM bebas < `CS_MIN_FREE_MEMORY_MB` (512) → job ditunda hingga 30 dtk lalu ditolak (`low_memory`).
- Timeout run `CS_RUN_TIMEOUT` (60 dtk, bisa diminta hingga 10×), build `CS_BUILD_TIMEOUT` (300 dtk) → `TIMEOUT`.
- RAM per job `CS_MEMORY_LIMIT_MB` (1024): watchdog RSS seluruh pohon proses (+ `RLIMIT_AS` untuk C/C++/Python/PHP/SQL; `-Xmx`, `--max-old-space-size`, `GCHeapHardLimit` untuk JVM/Node/.NET).
- `RLIMIT_CPU`, `RLIMIT_FSIZE` (256 MB per file), core dump mati, `nice 10`.
- Output dibatasi `CS_OUTPUT_LIMIT_BYTES` (1 MB) lalu ditandai `truncated`.
- Perintah selalu berupa **daftar argumen** tervalidasi (tidak ada shell string). Path file divalidasi berada di proyek.
- Semua dijalankan di sandbox bubblewrap (lihat SECURITY.md). Artefak build di `workspace/cache/builds/<proyek>/<bahasa>/<nama>/`.

## Menambah bahasa
Buat `backend/engines/<x>_engine.py` turunan `BaseEngine`, isi `language_id`, `extensions`, `executables`,
`build_steps()`/`run_steps()`, daftarkan di `registry.py`, tambah template di `project_service.TEMPLATES`, dan tes di `tests/test_engines.py`.
