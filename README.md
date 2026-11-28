# CODING_SERVER

**Server pengembangan multi-bahasa untuk Raspberry Pi 5, dengan aplikasi Android sebagai remote IDE.**

Raspberry Pi menjadi server dan mesin eksekusi: file, compiler, runtime, terminal, Git, database, dan AI.
HP Android hanya antarmuka (editor, explorer, terminal, output, monitor, AI). Kamu bisa menulis, menjalankan,
menguji, dan memperbaiki kode dari HP. Kodenya tersimpan dan dijalankan di Pi, di dalam sandbox yang aman.

| | |
|---|---|
| Versi server | **1.5.0** — rilis stabil (FastAPI, Python 3) |
| Aplikasi | Android 8.0+ (Kotlin + Jetpack Compose), dibangun otomatis oleh GitHub Actions |
| Platform uji | Raspberry Pi 5 16 GB · Debian 13 (trixie) aarch64 · kernel 6.x · NVMe |
| Port bawaan | `8800` · API `/api/v1` · dokumentasi interaktif `/docs` |
| Lisensi | lihat [LICENSE](LICENSE) |

---

## Daftar isi
1. [Gambaran arsitektur](#gambaran-arsitektur)
2. [Fitur](#fitur)
3. [Persyaratan](#persyaratan)
4. [Instalasi](#instalasi)
5. [Akun, profil & admin utama](#akun-profil--admin-utama)
6. [Menghubungkan aplikasi Android](#menghubungkan-aplikasi-android)
7. [Cara pakai sehari-hari](#cara-pakai-sehari-hari)
8. [AI: chat, model lokal & AI Agent](#ai-chat-model-lokal--ai-agent)
9. [Sandbox & instal dependensi](#sandbox--instal-dependensi)
10. [Konfigurasi](#konfigurasi)
11. [Mengelola server](#mengelola-server)
12. [Struktur proyek](#struktur-proyek)
13. [Pengembangan & pengujian](#pengembangan--pengujian)
14. [Keamanan](#keamanan)
15. [Troubleshooting](#troubleshooting)
16. [Dokumentasi lengkap](#dokumentasi-lengkap)

---

## Gambaran arsitektur
```
 HP Android (APK)                                   Raspberry Pi 5
┌─────────────────────────────┐   REST /api/v1   ┌──────────────────────────────────────────────┐
│ Compose UI                  │ ───────────────▶ │ FastAPI                                      │
│  • Editor  (CodeMirror 6)   │   WebSocket /ws  │  ├─ API      auth · projects · files · exec   │
│  • Terminal (xterm.js)      │ ◀─────────────── │  │           terminal · db · git · http · ai  │
│  • Explorer, Output, Git,   │                  │  │           agent · lsp · monitor · backup   │
│    DB, HTTP, Monitor, AI    │                  │  ├─ Service  logika bisnis per fitur          │
│ Token terenkripsi (Keystore)│                  │  ├─ Engine   11 bahasa (BaseEngine)            │
└─────────────────────────────┘                  │  ├─ Sandbox  bubblewrap + rlimit + watchdog    │
                                                 │  ├─ Antrean  job + batas RAM/CPU/waktu        │
                         llama-server (opsional) │  └─ Storage  SQLite (WAL) + workspace/        │
                         model AI lokal  ◀────── │                                              │
                                                 └──────────────────────────────────────────────┘
```
Setiap program yang kamu jalankan masuk antrean, lalu dijalankan di sandbox **bubblewrap**: sistem read-only, `$HOME`
kosong, tanpa jaringan, dan hanya folder proyek yang bisa ditulis. Output dikirim real-time lewat WebSocket ke HP.

---

## Fitur

### Pengembangan
- **11 engine bahasa**: Python 3, JavaScript (Node.js), PHP, Go, C (GCC), C++ (G++), Java (JDK), C# (.NET 8),
  SQL (SQLite), HTML/CSS (pratinjau), dan Bash. Status tiap engine diperiksa sungguhan (`AVAILABLE` / `NOT_INSTALLED` / `ERROR`).
- **Build C/C++ multi-file**: CMake, Makefile, atau otomatis (semua sumber di folder). Folder latihan yang berisi banyak
  `main()` tetap bisa dijalankan per file.
- **Execution manager**: antrean job, batas job bersamaan, penolakan saat RAM hampir habis, timeout, batas RAM
  (watchdog RSS + `RLIMIT_AS`), batas CPU, ukuran file, dan output, pembatalan, stdin interaktif, streaming output,
  dan riwayat. Status job: `QUEUED → STARTING → RUNNING → COMPLETED / FAILED / TIMEOUT / CANCELLED`.
- **Instal dependensi** dengan satu tombol: pip ke `.venv` proyek, `npm install`, `go mod download`, `composer install`.
  Langkah instal mendapat internet, tetapi program biasa tetap tanpa internet ([detail](#sandbox--instal-dependensi)).
- **Editor CodeMirror 6**: syntax highlighting 18+ bahasa, banyak tab, cari & ganti, lompat ke baris, code folding,
  autocomplete, diagnostics dari output compiler, simbol dokumen, riwayat versi & restore, serta tema dan warna sendiri.
- **Language server (LSP)** di server dan di dalam sandbox: clangd (C/C++) dan pyright (Python) untuk autocomplete
  pintar, error saat mengetik, info simbol, dan go-to-definition lintas file.
- **Terminal interaktif** (PTY + WebSocket, xterm.js): banyak sesi, tombol ESC/TAB/Ctrl, dan idle timeout.
- **File manager aman**: CRUD, rename/copy/move, cari nama & isi, favorit, file terakhir, tulis atomik,
  deteksi konflik SHA-256, riwayat versi + undo, serta perlindungan path traversal & symlink.

### Alat
- **Git manager**: init, status, commit, diff, branch, checkout, remote, pull, push, clone, dan token Git yang
  disimpan terenkripsi di server.
- **Database manager SQLite**: buat DB, skema, query mode baca/tulis, ekspor CSV, dan konfirmasi untuk operasi destruktif.
- **HTTP client / API tester**: header, query, dan body json/form/raw, plus koleksi tersimpan. Ada perlindungan anti-SSRF.
- **System monitor**: CPU per core, RAM, disk, suhu, jaringan, job aktif, versi compiler, dan proses teratas.
- **Backup & restore** terverifikasi (otomatis harian, retensi bisa diatur).

### AI
- **AI Chat** dengan model lokal (llama-server) atau online (API kompatibel OpenAI): streaming, "Berpikir…", dan riwayat.
  Kamu bisa menyertakan file yang sedang dibuka. Perubahan kode muncul sebagai kartu diff **Terapkan / Tolak / Batalkan**.
- **AI Agent Tasks**: beri tugas seperti "buat halaman login dan pastikan jalan". Agen memeriksa proyek, membuat rencana,
  mengusulkan perubahan (risiko LOW/MEDIUM/HIGH), menginstal dependensi, menjalankan build/test di sandbox, memperbaiki
  bila gagal, lalu membuat laporan. Agen punya peran Perencana, Pelaksana, dan Peninjau, dan modelnya bisa berbeda per peran.
- **Model AI**: kelola koneksi, muat/bongkar model, **profil model** dan **Uji Model** (kalibrasi otomatis parameter
  yang paling cocok untuk tiap model).
- **Konteks model**: ukuran konteks bawaan & per model diatur dari APK (disimpan sebagai preset llama-server, dimuat
  ulang tanpa restart).
- **Lepas semua model dari RAM**: versi aman melewati model yang sedang dipakai; **Paksa lepas** untuk Pi yang macet —
  task AI Agent dijeda dari checkpoint (lanjutkan kapan saja), Uji Model dihentikan, semua model dibongkar.
- **AI Agent tahan banting**: batas langkah per task diatur dari APK, jeda langsung berhenti dan aman dilanjutkan,
  konteks model otomatis dipadatkan bila penuh, cek otomatis file kode (sintaks & fungsi ganda) setelah ditulis, dan
  task tidak bisa "selesai" bila kodenya masih rusak.

### Akun & tampilan
- **Profil pengguna**: foto profil, nama tampilan, email, bio, dan ganti sandi sendiri. Profil aktif tampil di Dashboard
  dan menu samping.
- **Kelola pengguna** (admin): tambah akun, ubah peran, reset sandi, nonaktifkan, dan hapus akun (proyeknya dipindah ke admin utama).
- **Izin per kelompok**: menu dan tombol yang tidak boleh dipakai sebuah peran **disembunyikan** di aplikasi (bukan
  sekadar ditolak server), jadi tiap pengguna hanya melihat yang bisa ia gunakan.
- **Admin utama terkunci**: akun pemulihan yang tidak bisa dihapus atau diubah dari aplikasi ([detail](#akun-profil--admin-utama)).
- **Tema aplikasi**: mode Ikuti sistem / Gelap / Terang, 11 warna aksen (termasuk Dinamis dari wallpaper, Android 12+),
  **7 warna latar tampilan** (Netral, Ikut aksen, Biru malam, Hijau hutan, Ungu anggur, Sepia, Abu batu), dan hitam pekat AMOLED.
- **Pembaruan otomatis**: aplikasi mengecek APK baru di GitHub Releases, lalu mengunduh dan memasangnya
  (tanda tangan diverifikasi).
- **Mode offline jujur**: bila server tidak terjangkau, muncul banner OFFLINE. Aplikasi tidak menampilkan data palsu.

---

## Persyaratan
**Server (Raspberry Pi 5 atau Linux ARM64/x86_64 lain)**
- Raspberry Pi OS / Debian 12–13, Python ≥ 3.10, RAM ≥ 4 GB (16 GB disarankan bila memakai model AI lokal).
- Paket wajib: `git bubblewrap curl python3-venv`.
- Compiler sesuai kebutuhan: `gcc g++ make cmake ninja-build default-jdk golang nodejs npm sqlite3 php-cli`.
- .NET SDK 8, PHP, clangd, dan pyright dipasang otomatis tanpa sudo oleh `scripts/install_runtimes.sh` bila belum ada.
- Opsional: [llama.cpp](https://github.com/ggml-org/llama.cpp) `llama-server` + model `.gguf` untuk AI lokal.

**HP**
- Android 8.0 (API 26) atau lebih baru, di jaringan yang sama dengan Pi (atau lewat VPN seperti Tailscale/WireGuard).

---

## Instalasi
```bash
sudo apt install -y git bubblewrap curl python3-venv     # minimal
git clone https://github.com/MiftahulKhoiri/Coding_server.git ~/Coding_server
cd ~/Coding_server
./scripts/install.sh
```
Installer akan:
1. Memeriksa OS, arsitektur, Python, dan paket.
2. Membuat virtualenv `.venv` dan memasang dependensi Python.
3. Memasang runtime opsional, lalu menguji setiap engine.
4. Membuat `deployment/configuration/coding_server.env` dari contoh.
5. Memasang autostart dengan mode terbaik yang tersedia:
   - `sudo` tanpa password → systemd **system** service;
   - *linger* aktif → systemd **user** service (tanpa sudo). Mode ini yang dipakai di Pi 5;
   - selain itu → cron `@reboot` + supervisor dengan restart otomatis.
6. Menjalankan server dan health check, lalu menampilkan **sandi admin utama**.

Cek hasilnya:
```bash
./scripts/status.sh                       # status service + health
curl http://127.0.0.1:8800/api/v1/system/health
```

---

## Akun, profil & admin utama
**Admin utama (root)** adalah akun `admin` yang dibuat saat instalasi. Akun ini adalah **akun pemulihan**:
- tidak bisa dihapus, dinonaktifkan, atau diubah perannya, oleh siapa pun;
- **sandinya tidak bisa diubah dari aplikasi**. Sumbernya selalu di server, dan disinkronkan setiap server start:
  1. `CS_ADMIN_PASSWORD` di `deployment/configuration/coding_server.env`, atau bila kosong
  2. `workspace/metadata/initial_admin_password.txt` (dibuat acak saat instalasi, **jangan dihapus**);
- hanya admin utama yang boleh membuat, mengubah, atau menghapus akun lain berperan Admin.

Kelola sandi admin utama dari Pi:
```bash
./scripts/admin_password.sh            # tampilkan username & sandi
./scripts/admin_password.sh --set      # ganti (diketik, tidak tampil)
./scripts/admin_password.sh --random   # buat sandi acak baru
```

**Alur yang disarankan**
1. Login di APK dengan akun `admin`.
2. **Pengaturan → Pengguna → ➕**: buat profil harianmu (mis. peran Developer), lalu login dengan akun itu.
3. **Pengaturan → Akun & profil → Ubah profil**: pasang foto profil, nama tampilan, email, dan bio.
4. Bila sandi akun mana pun lupa, login sebagai `admin` lalu buka **Pengguna → ⋮ → Reset sandi**.

**Peran & izin**

| Peran | Hak | Yang tidak tampil di aplikasi |
|---|---|---|
| **Admin utama (root)** | semua, termasuk backup/restore, proses server & audit, kelola admin | – |
| Admin | semua proyek, kelola pengguna non-admin, pengaturan AI (model, konteks, lepas model, Uji Model, profil) | Backup, daftar proses server |
| Developer | proyek sendiri: baca, tulis, hapus, jalankan, build, terminal, AI Chat & AI Agent | Kelola pengguna, pengaturan Model AI (hanya Ringkasan), backup |
| Runner | baca, jalankan, build | + Terminal, Git, tombol tulis/hapus/simpan/file baru |
| Viewer | hanya melihat | + AI Chat, AI Agent, HTTP Client, tombol Jalankan/Build/Instal |
| AI | peran internal agen (baca, tulis, jalankan, build; tanpa terminal/hapus/admin) | – |

Izin di server: `read write delete execute build terminal` + `admin` (lihat semua proyek), `users` (kelola pengguna),
`ai_manage` (pengaturan AI), `system` (khusus root). Hak tambahan `admin`/`users` hanya bisa diberikan admin utama.
Setiap pengguna hanya melihat proyek miliknya sendiri, kecuali admin. Disarankan memakai akun **Developer** untuk
kerja harian dan `admin` hanya untuk pemulihan.

---

## Menghubungkan aplikasi Android
1. Unduh **CodingServer.apk** dari
   [GitHub Releases → android-latest](https://github.com/MiftahulKhoiri/Coding_server/releases/tag/android-latest)
   lalu pasang (izinkan "instal dari sumber ini").
2. Buka aplikasi → **Tambah server** → isi `IP-PI:8800` (lihat IP dengan `hostname -I`) → **Tes koneksi** → **Hubungkan**.
3. Login. Dashboard menampilkan profil aktif, status server, sumber daya, aktivitas, dan proyek terbaru.
4. Pembaruan berikutnya datang otomatis: banner biru muncul saat ada APK baru (dibuat CI setiap push ke `main`).

> APK resmi ditandatangani oleh CI. Bila muncul pesan "tanda tangan beda", hapus aplikasi lama sekali lalu pasang dari Releases.

---

## Cara pakai sehari-hari
| Tujuan | Langkah di aplikasi |
|---|---|
| Buat proyek | Proyek → ➕ → pilih template bahasa (atau clone dari Git) |
| Tulis & jalankan | Explorer → buka file → ▶ Jalankan / 🔨 Build; output real-time di layar Output (stdin, Stop, error bisa diklik) |
| Pasang library | Explorer → ⬇ **Instal dependensi** (baca `requirements.txt`, `package.json`, `go.mod`, `composer.json`, atau ketik nama paket) |
| Terminal | menu Terminal → sesi baru (shell di sandbox proyek) |
| Git | menu Git → status, commit, push/pull, branch |
| Database | menu Database → pilih/buat DB → query |
| Uji API | menu HTTP Client |
| Ubah tampilan | Pengaturan → Tampilan → mode, warna aksen, **warna latar**, AMOLED |
| Backup | Pengaturan → Backup server (admin utama) |
| Pi macet karena model AI | Model AI → AI Agent → ⛔ **Paksa lepas** → lanjutkan task agent nanti dengan **Lanjutkan** |

Ekstensi yang dikenali: `.py .js .mjs .php .go .c .cpp .cc .java .cs .sql .html .css .sh`. Detail ada di
[docs/EXECUTION_ENGINE.md](docs/EXECUTION_ENGINE.md).

---

## AI: chat, model lokal & AI Agent
**Menyiapkan model lokal** (llama.cpp mode router di Pi — banyak model `.gguf` dalam satu folder):
```bash
~/llama.cpp/build/bin/llama-server --models-preset ~/models/coding_server_presets.ini \
  --models-dir ~/models --no-models-autoload --jinja --host 0.0.0.0 --port 8080
```
Jangan memberi `-c`/`--ctx-size` di perintah ini: konteks diatur dari APK (**Model AI → AI Agent → Konteks model**) lewat
file preset. Bila service lama masih memakai `-c`, aplikasi menampilkan perintah `sudo` sekali-jalan untuk
memperbaikinya.

Di APK: **Model AI → Lokal → tambah koneksi** `http://127.0.0.1:8080` → pilih model → **Terapkan**. Model online
(API kompatibel OpenAI) juga bisa ditambahkan beserta API key-nya (disimpan terenkripsi di server).

**Saran model**: di Pi 5 16 GB, satu model untuk semua peran agent (mis. Qwen3.5-9B atau Qwen2.5-Coder-7B) dengan
konteks 16K lebih stabil daripada beberapa model yang bergantian dimuat.

**AI Agent** (menu AI Agent):
1. Pilih proyek, lalu tulis tugasnya. Contoh: *"buat dashboard dengan halaman login lengkap memakai Flask"*.
2. Agen bekerja dalam tahap PLANNING → INSPECTING → EXECUTING → BUILDING/TESTING → REVIEWING.
3. Perubahan file menjadi **proposal**. Mode izin: *manual* (kamu menyetujui setiap proposal), *otomatis*
   (LOW/MEDIUM langsung diterapkan), atau *penuh* (semua diterapkan, tetap tercatat dan bisa dibatalkan).
4. Library dipasang agen lewat tool `install_deps`, tidak lewat skrip installer.
5. Laporan akhir memisahkan **hasil terverifikasi server** (exit code build/test) dari **ringkasan AI**.

Task tersimpan di database dengan checkpoint. **Jeda** langsung berhenti (juga saat model sedang berpikir) dan
**Lanjutkan** mengulang langkah terakhir dari checkpoint tanpa merusak file. Bila langkah habis, **Ulangi** memberi
tambahan langkah. Bila server restart, task dijeda dan bisa dilanjutkan. Proses agen juga bisa dipantau dari
notifikasi Android. Model lokal kecil di Pi cukup lambat (±1–5 token/detik), jadi task besar bisa memakan
puluhan menit. Detail ada di [docs/AI_AGENT.md](docs/AI_AGENT.md).

---

## Sandbox & instal dependensi
Program pengguna, terminal, Git, dan LSP berjalan di **bubblewrap**:
- `/usr` dan `/etc` read-only, `$HOME` dan `/tmp` berupa tmpfs kosong (kunci SSH dan token di Pi tidak terlihat);
- hanya folder proyek dan cache server yang bisa ditulis;
- namespace terpisah (user, pid, ipc, uts, net), proses mati bersama induknya;
- **tanpa jaringan** untuk program biasa (`CS_SANDBOX_NETWORK=false`).

Karena program biasa tanpa jaringan, perintah `pip install` di dalam program **pasti gagal**. Untuk memasang paket,
gunakan fitur **Instal dependensi** (`POST /api/v1/execution/install`, tombol ⬇, atau tool agen `install_deps`):

| Proyek | Perintah yang disusun server |
|---|---|
| `requirements.txt` / `pyproject.toml` | `python3 -m venv .venv` → `.venv/bin/python -m pip install -r requirements.txt` |
| `package.json` | `npm install --no-audit --no-fund` |
| `go.mod` | `go mod download` |
| `composer.json` | `composer install` |

- Hanya langkah instal yang mendapat internet (`CS_INSTALL_NETWORK=true`). Langkah ini tetap di sandbox dan tetap
  hanya bisa menulis ke folder proyek.
- Perintahnya **disusun server**, dan nama paket divalidasi (tidak bisa disisipi opsi seperti `--index-url` atau path).
- Setelah `.venv` ada, ▶ Jalankan dan uji Python **otomatis memakai `.venv` proyek**.

Bila kernel tidak mendukung user namespace, server **menolak** menjalankan kode (`503 sandbox_unavailable`).
Mode tanpa sandbox hanya bisa dipilih eksplisit (`CS_SANDBOX=none`, tidak disarankan).

---

## Konfigurasi
Semua kunci ada di `deployment/configuration/coding_server.env`
(contoh lengkap: [`coding_server.env.example`](deployment/configuration/coding_server.env.example)).
Setelah mengubah file ini, jalankan `./scripts/restart.sh`.

| Kunci | Bawaan | Keterangan |
|---|---|---|
| `CS_HOST` / `CS_PORT` | `0.0.0.0` / `8800` | alamat server |
| `CS_ADMIN_USERNAME` / `CS_ADMIN_PASSWORD` | `admin` / kosong | admin utama; sandi kosong = dari `initial_admin_password.txt` |
| `CS_ACCESS_TOKEN_MINUTES` / `CS_REFRESH_TOKEN_DAYS` | 720 / 30 | masa berlaku token |
| `CS_MAX_CONCURRENT_JOBS` / `CS_MAX_QUEUED_JOBS` | 2 / 20 | antrean eksekusi |
| `CS_RUN_TIMEOUT` / `CS_BUILD_TIMEOUT` | 60 / 300 dtk | batas waktu run/build |
| `CS_MEMORY_LIMIT_MB` / `CS_MIN_FREE_MEMORY_MB` | 1024 / 512 | batas RAM per job / RAM bebas minimum |
| `CS_SANDBOX` | `auto` | `auto` · `bwrap` · `none` |
| `CS_SANDBOX_NETWORK` | `false` | internet untuk program pengguna |
| `CS_INSTALL_NETWORK` / `CS_INSTALL_TIMEOUT` | `true` / 900 | internet & batas waktu untuk instal dependensi |
| `CS_TERMINAL_NETWORK` | `true` | internet di terminal |
| `CS_HTTP_ALLOW_PRIVATE` | `false` | HTTP client boleh ke IP lokal (192.168.x.x) |
| `CS_BACKUP_RETENTION` | 7 | jumlah backup harian yang disimpan |
| `CS_AI_BASE_URL` / `CS_AI_MODEL` | – | koneksi AI awal (opsional, bisa diatur dari APK) |
| `CS_AGENT_MAX_STEPS` / `CS_AGENT_TASK_TIMEOUT` | 100 / 21600 dtk | batas atas langkah per task (nilai bawaan diatur di APK) & waktu agen (6 jam) |
| `CS_LLAMA_PRESETS_FILE` | `~/models/coding_server_presets.ini` | file preset konteks llama-server yang ditulis dari APK |

---

## Mengelola server
```bash
./scripts/start.sh | stop.sh | restart.sh | status.sh    # kontrol service
./scripts/admin_password.sh [--set|--random]             # sandi admin utama
.venv/bin/python scripts/backup.py create|list|verify|restore NAMA
./scripts/install_runtimes.sh                            # pasang/ulang .NET, PHP, clangd, pyright
```
**Update server**
```bash
cd ~/Coding_server && git pull && .venv/bin/pip install -r requirements.txt && ./scripts/restart.sh
```
Migrasi database berjalan otomatis saat start (idempoten).

**Uninstall**
```bash
./scripts/uninstall.sh              # hapus service, autostart, proses, venv, log, cache; DATA dipertahankan
./scripts/uninstall.sh --purge      # + hapus data (backup akhir dibuat dulu di ~)
./scripts/uninstall.sh --dry-run    # lihat apa yang akan dihapus
```
Opsi lain: `--remove-runtimes`, `--remove-repo`, dan `-y` (tanpa konfirmasi).

**Log**: `logs/server.log`, `logs/service.log`, dan `logs/audit.log` (login, eksekusi, perubahan pengguna, dsb).

---

## Struktur proyek
```
Coding_server/
├── backend/                 FastAPI
│   ├── api/                 router REST & WebSocket (auth, files, execution, agent, ai, git, …)
│   ├── services/            logika: auth, file, project, execution, deps_install, terminal, git, http,
│   │                        database, backup, monitor, ai, agent_service, agent_tools, model_bench, lsp, …
│   ├── engines/             BaseEngine + python, javascript, php, go, c, cpp, java, csharp, sql, web, shell
│   ├── core/                sandbox (bwrap), process_manager, job_queue, security, permissions, logging
│   ├── database/db.py       SQLite metadata (WAL) + migrasi ringan
│   ├── schemas/models.py    kontrak request/response (Pydantic)
│   └── tests/               pytest (auth, profil, file, engine, sandbox, install, AI, agent, keamanan)
├── android/                 aplikasi Android (Gradle, Kotlin, Compose)
│   └── app/src/main/java/id/codingserver/android/
│       ├── data/            api (Retrofit/WebSocket), settings (DataStore), update (pembaruan APK)
│       ├── ui/              dashboard, projects, editor, terminal, output, ai, agent, git, database,
│       │                    http, monitor, settings, theme, common
│       └── agent/           layanan notifikasi pemantau AI Agent
├── web_editor/              sumber CodeMirror 6 & xterm.js → dibundel ke aset Android
├── model_profiles/          profil parameter per model AI (hasil Uji Model)
├── scripts/                 install, start/stop/restart/status, admin_password, backup, uninstall, runtime
├── deployment/              template systemd & contoh konfigurasi .env
├── docs/                    dokumentasi teknis
├── workspace/               (runtime) projects/, database/, metadata/, history/, cache/
├── logs/  backups/          (runtime)
└── .github/workflows/       backend.yml (pytest) · android.yml (build APK + GitHub Release)
```

---

## Pengembangan & pengujian
**Backend**
```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q backend/tests          # di Pi: termasuk uji sandbox bwrap asli
CS_SANDBOX=none python -m pytest -q backend/tests    # mesin tanpa bwrap (uji sandbox dilewati)
```
Server dev: `.venv/bin/uvicorn backend.main:app --reload --port 8800`.

**Android** (build lokal ARM64 di Pi):
```bash
cd android && echo "sdk.dir=$HOME/android-sdk" > local.properties
./gradlew -Pcodingserver.localArm64 -Pcodingserver.allowDebugSigning \
  -Pandroid.aapt2FromMavenOverride=$HOME/android-sdk/aapt2-arm64/aapt2 testDebugUnitTest assembleDebug
```
APK resmi (API 35, tanda tangan rilis) dibuat oleh GitHub Actions setiap push ke `main` lalu diterbitkan sebagai
`android-latest`. Detail ada di [docs/ANDROID.md](docs/ANDROID.md) dan [docs/TESTING.md](docs/TESTING.md).

---

## Keamanan
- Sandi di-hash dengan **scrypt**. Token JWT terdiri dari access token (12 jam) dan refresh token (30 hari,
  **sekali pakai**). Logout mencabut token.
- Rate limit login dan API, izin berbasis peran, dan isolasi proyek per pengguna.
- Sandbox bubblewrap untuk semua kode pengguna. Perintah sistem (uji, instal) disusun server, tidak pernah dari input mentah.
- Git: hooks dimatikan, hanya `https://`, token terenkripsi (Fernet) dan diberikan via `GIT_ASKPASS`.
- HTTP client anti-SSRF: menolak loopback, metadata cloud, dan jaringan privat, dicek ulang saat koneksi dan redirect.
- AI tidak pernah punya hak melebihi pemiliknya. Perubahan AI berupa proposal yang tercatat dan bisa dibatalkan.
- Audit log untuk aksi penting. Token dan sandi disensor dari log.
- Android: token disimpan di EncryptedSharedPreferences (Android Keystore). APK update diverifikasi SHA-256 dan
  tanda tangannya.

> Server memakai HTTP biasa untuk jaringan rumah. **Jangan buka port 8800 ke internet.** Untuk akses dari luar, gunakan
> VPN (Tailscale/WireGuard) atau reverse proxy HTTPS. Detail ada di [docs/SECURITY.md](docs/SECURITY.md).

---

## Troubleshooting
| Gejala | Solusi |
|---|---|
| APK "Server tidak bisa dihubungi" | `./scripts/status.sh`; cek IP (`hostname -I`), HP & Pi satu jaringan, port 8800 |
| Lupa sandi admin utama | `./scripts/admin_password.sh` (tampilkan) / `--set` (ganti) |
| Lupa sandi akun lain | login sebagai admin utama → Pengaturan → Pengguna → ⋮ → Reset sandi |
| `pip install` gagal ("name resolution" / "externally-managed-environment") | pakai ⬇ Instal dependensi / tool `install_deps`; pastikan `CS_INSTALL_NETWORK=true` |
| `503 sandbox_unavailable` | pasang `bubblewrap`, pastikan user namespace aktif (`unshare -U true`) |
| Engine `NOT_INSTALLED` | pasang paketnya (`sudo apt install …` / `scripts/install_runtimes.sh`) → Monitor → Periksa ulang |
| Job ditolak `low_memory` / `queue_full` | tunggu job lain, bongkar model AI, atau naikkan batas di `.env` |
| Program `TIMEOUT` | naikkan `CS_RUN_TIMEOUT` atau timeout di request |
| APK tidak mau update ("tanda tangan beda") | hapus aplikasi sekali, pasang APK dari Releases |
| Agen AI sangat lambat | wajar untuk model lokal di Pi; pakai model lebih kecil atau model online untuk peran Perencana |
| Pi macet / RAM penuh saat agen berjalan | Model AI → AI Agent → ⛔ Paksa lepas; kurangi "Model lokal termuat bersamaan" ke 1 |
| Agen gagal "konteks terlampaui" | naikkan konteks di Model AI → AI Agent → Konteks model (mis. 16K); jalankan perintah sudo yang ditampilkan bila diminta |
| Menu tidak ada (mis. Terminal, Backup) | peran akun tidak punya izinnya — minta admin mengubah peran |

Selengkapnya ada di [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

---

## Dokumentasi lengkap
| Dokumen | Isi |
|---|---|
| [ARCHITECTURE](docs/ARCHITECTURE.md) | lapisan, alur eksekusi, keputusan teknis |
| [INSTALLATION](docs/INSTALLATION.md) | instalasi rinci, autostart, login pertama |
| [BACKEND](docs/BACKEND.md) · [API_REFERENCE](docs/API_REFERENCE.md) | layanan backend & seluruh endpoint |
| [ANDROID](docs/ANDROID.md) | halaman aplikasi, build, rilis, penandatanganan |
| [EXECUTION_ENGINE](docs/EXECUTION_ENGINE.md) · [TERMINAL](docs/TERMINAL.md) | engine bahasa & terminal |
| [AI_AGENT](docs/AI_AGENT.md) | alur agen, tool, persetujuan, laporan |
| [DATABASE](docs/DATABASE.md) · [GIT](docs/GIT.md) | database manager & Git manager |
| [SECURITY](docs/SECURITY.md) · [SECURITY_REVIEW](docs/SECURITY_REVIEW.md) | kontrol keamanan & tinjauan |
| [TESTING](docs/TESTING.md) · [TROUBLESHOOTING](docs/TROUBLESHOOTING.md) | pengujian & pemecahan masalah |
| [CHANGELOG](docs/CHANGELOG.md) · [ROADMAP](docs/ROADMAP.md) · [PROJECT_STATUS](PROJECT_STATUS.md) | riwayat, rencana, status |
