# Changelog

## 1.7.2 — 2026-11-29
### Diubah
- Menu **"Model AI" → "AI Pengaturan"**, urutan: AI Chat · AI Agent · AI Pengaturan (ikon tetap).
- Jenis & ukuran huruf **kode** kini diatur di tempatnya: Code Editor → ⋮ → Pengaturan editor, dan Terminal → ⚙.
- Pengaturan → **Font** = huruf **tampilan aplikasi**: Bawaan (Roboto), Inter, Poppins, Nunito, Open Sans, Lato,
  Serif (TTF dibundel, SIL OFL) dan ukuran teks Kecil / Normal / Besar / Sangat besar.

## 1.7.1 — 2026-11-29
### Diubah
- **Pengaturan disusun ulang**: hanya 1 · Profil, 2 · Manajer akun, 3 · Pembaruan aplikasi, 4 · Font, 5 · Warna.
  Perilaku editor pindah ke Code Editor → ⋮ → **Pengaturan editor**; kartu AI dihapus (ada di Model AI);
  **Backup** pindah ke Server Monitor.
- **Profil**: latar profil di belakang foto (10 gradasi atau warna tema, disimpan di server `users.cover`),
  **ketuk foto = tampilan penuh** (cubit untuk memperbesar).
### Ditambahkan
- **Jenis huruf** Code Editor & Terminal: JetBrains Mono, Fira Code (ligatur), Source Code Pro, Ubuntu Mono,
  Roboto Mono, IBM Plex Mono (dibundel, lisensi SIL OFL), atau bawaan sistem — Pengaturan → Font.
- Pengaturan → Warna: tema aplikasi, preset warna Code Editor, tema Terminal di satu tempat.
### Diperbaiki
- **Terminal susah digeser**: gulir satu jari kini ditangani sendiri dengan momentum (xterm.js hampir tidak punya
  gulir sentuh di Android); di less/vim/top geser = tombol ↑/↓.
- Akun tertaut: pesan jelas bila Client ID belum diisi ("admin utama (akun @admin) harus mengisi Client ID").

## 1.7.0 — 2026-11-28
### Ditambahkan
- **Akun tertaut GitHub & Google** (Pengaturan → Akun tertaut), lewat OAuth *device flow* (tanpa domain publik):
  aplikasi menampilkan kode → buka github.com/login/device atau google.com/device → setujui.
  `POST /auth/identities/{github|google}/link`, `GET /auth/identities/flows/{id}`, `GET/DELETE /auth/identities…`.
- **Email profil = email aktif**: hanya boleh salah satu email terverifikasi dari akun tertaut (✓ terverifikasi);
  email ketikan ditolak (`email_unverified`). Email lama tetap tersimpan, ditandai "belum terverifikasi".
- **GitHub untuk push**: opsi "Izinkan push" menyimpan token (terenkripsi) sebagai kredensial Git github.com —
  Commit semua → Push langsung jalan tanpa token manual. Lepas tautan ikut menghapus token itu.
- **Commit atas nama sendiri**: nama tampilan & email terverifikasi dipakai sebagai author/committer Git
  (sebelumnya `username@coding-server.local`), sehingga commit tampil di profil GitHub.
- Admin utama mengisi Client ID GitHub OAuth App (Enable Device Flow) dan Client ID+secret Google
  ("TVs and Limited Input devices") di aplikasi (`PUT /auth/oauth/config`, secret terenkripsi) atau lewat env
  `CS_GITHUB_CLIENT_ID`, `CS_GOOGLE_CLIENT_ID`, `CS_GOOGLE_CLIENT_SECRET`.
### Database
- Tabel `user_identities`, kolom `users.email_verified` (migrasi otomatis).

## 1.6.2 — 2026-11-28
### Ditambahkan
- Project Explorer: **Buka di terminal** (ikon terminal di toolbar = akar proyek; menu ⋮ folder/file = folder itu).
  Tab sesi menampilkan nama foldernya.
- Terminal: `pip install …` otomatis memakai `.venv` di akar proyek (dibuat saat pertama dipakai) — pip sistem
  Debian menolak instal ("externally-managed-environment"); perintah **`deps`** memasang semua dependensi folder
  (requirements.txt / pyproject.toml, package.json, go.mod, composer.json). `npm`, `go get` langsung bisa.
### Keamanan
- File rc terminal ditulis server di folder yang hanya-baca di sandbox (tidak bisa diubah pengguna lain).

## 1.6.1 — 2026-11-28
### Ditambahkan
- Code Editor: tombol **⌨ buka/tutup keyboard** (toolbar & baris tombol ekstra) dan pengaturan **"Ketuk kode =
  keyboard muncul"** (Pengaturan → Editor / menu ⋮). Mati: ketukan hanya memindah kursor untuk membaca kode.
### Diperbaiki
- Menggeser kode untuk membaca tidak lagi memunculkan keyboard.
- **AI Chat tidak berhenti saat aplikasi ditutup / HP mati / layar terkunci**: jawaban dibuat di server sebagai
  pekerjaan tersendiri, disimpan ke percakapan, dan aplikasi menyambung lagi otomatis (⏳ di daftar percakapan).
  Sebelumnya jawaban dibatalkan, dan bila HP mati mendadak model lokal bisa tetap sibuk sehingga pertanyaan
  berikutnya tampak macet. Satu jawaban berjalan per pengguna; Stop dan "Paksa lepas" tetap menghentikannya.

## 1.6.0 — 2026-11-28 (IDE)
Fokus: Code Editor menjadi IDE yang lengkap untuk HP.
### Ditambahkan
- **Baris tombol ekstra** di atas keyboard: Tab/Shift-Tab, kurung & simbol (berpasangan otomatis), panah, Home/End,
  komentar, saran kode, duplikat & hapus baris.
- **Simpan otomatis** 2 dtk setelah berhenti mengetik; **tab terbuka dipulihkan** saat aplikasi dibuka lagi;
  **Buka file cepat** (`GET /files/list`, urutan nama → path → fuzzy).
- **Format kode** (`POST /files/format`): clang-format (C/C++/Java/C#), ruff (Python), prettier
  (JS/TS/CSS/HTML/JSON/YAML/Markdown), gofmt — di sandbox, menghormati `.clang-format`, `.prettierrc`, `pyproject.toml`.
- **Ganti nama simbol** & **cari semua referensi** lintas file (LSP; C/C++ menganalisis file proyek dulu),
  **petunjuk parameter** saat mengetik `(`/`,`, **panel Masalah** (penghitung ⛔/⚠ + daftar, lompat ke baris).
- **Language server baru**: JavaScript/TypeScript, Go (gopls), PHP (intelephense), HTML, CSS, JSON, Bash —
  selain C/C++ (clangd) dan Python (pyright). Semua di sandbox, dipasang `install_runtimes.sh`.
- **Cari & ganti di seluruh proyek** (`POST /files/grep`, `POST /files/replace`): teks/regex, huruf besar-kecil,
  kata utuh; tiap file yang diganti tercatat di riwayat versi.
- **Penanda baris Git** (ditambah/diubah/dihapus vs HEAD, termasuk perubahan belum disimpan; `GET /git/head-file`).
- **Outline** bersarang dari LSP + **breadcrumb** fungsi/kelas di kursor; **snippet** per bahasa (saran & menu).
- Uji editor di Chromium headless (`web_editor/test`, juga di CI).
### Diperbaiki
- Riwayat versi file dibatasi 50 versi per file (sebelumnya tumbuh tanpa batas).
- `install_runtimes.sh` memasang ulang clangd setiap kali dijalankan.
- Bundel editor: teks `</script>` di dalam kode tidak lagi memutus tag `<script>` inline.

## 1.5.0 — 2026-11-28 (rilis stabil)
### Ditambahkan
- **Profil pengguna**: foto profil (lama dihapus saat diganti), nama tampilan, email, bio; profil aktif di Dashboard
  & menu samping. **Admin utama (root) terkunci** sebagai akun pemulihan; sandinya hanya dari server.
- **Izin per kelompok**: hak baru `users`, `ai_manage`, `system` (khusus root). Admin biasa tanpa backup/proses/audit;
  hak tambahan `admin`/`users` hanya bisa diberi root. APK **menyembunyikan** menu, tab, dan tombol yang tidak diizinkan
  (drawer, Model AI, Backup, proses server, Explorer, Proyek, Editor).
- **Instal dependensi di sandbox** (pip ke `.venv` proyek, npm, go, composer) + tool agen `install_deps`.
- **Konteks model** llama-server (bawaan & per model) dari APK lewat file preset, tanpa restart.
- **Paksa lepas semua model dari RAM**: menjeda task AI Agent dari checkpoint dan menghentikan Uji Model.
- **Batas langkah per task** AI Agent diatur dari APK.
- Warna latar tampilan (7 pilihan), README ditulis ulang.
### Diperbaiki
- AI Agent: isi `write_file` yang rusak dipulihkan; konteks penuh → riwayat dipadatkan & diulang; galat berulang
  memicu eskalasi; jeda langsung berhenti walau model sedang berpikir; task lanjutan memakai prompt terbaru;
  cek otomatis sintaks & fungsi ganda setelah menulis kode; `finish` ditolak bila kode masih rusak.
- APK: upload foto profil selalu gagal; detail AI Agent tidak bisa digulir; log terbaru kini di atas.
- Backup menyertakan foto profil & sandi admin utama (izin 0600 saat restore).
- Tes LSP kadang gagal `CancelledError` (penutupan WebSocket kini rapi).

## 1.4.0 — 2026-11-24
### Keamanan
- **P0** Pencarian isi file tidak lagi membaca lewat symlink (sebelumnya symlink ke `~/.ssh/...` membocorkan isi).
- **P0** HTTP client: IP diperiksa saat koneksi TCP dibuat (anti DNS rebinding); klasifikasi IPv4-mapped IPv6, NAT64,
  6to4, CGNAT. Uji regresi di `test_security_regressions.py`.
### Ditambahkan
- **AI Coding Agent** (`/api/v1/agent/*`, layar **Agent Tasks** di APK): task persisten dengan rencana, tool
  ber-izin (baca/cari/edit via proposal/build/run/test/git), menunggu persetujuan sebelum menjalankan kode,
  perbaikan berulang, laporan (fakta terverifikasi server vs ringkasan AI), jeda/lanjut/batal/ulangi, pulih saat
  server restart. Lihat `docs/AI_AGENT.md`.
- **Risiko proposal AI** LOW/MEDIUM/HIGH; HIGH tidak pernah auto-apply dan butuh konfirmasi (dialog di APK).
- Deteksi perintah uji (pytest/unittest, go test, npm test, make test) + `ExecutionService.submit_command`.
- Menu APK dikelompokkan (Workspace, Development, AI Development, Project Tools, Server, System).
- Dokumen audit: `PROJECT_AUDIT.md`, `SECURITY_REVIEW.md`, `FEATURE_STATUS.md`, `ROADMAP.md`.
### Database
- Skema v3: tabel `agent_tasks`, `agent_events`; kolom `risk`, `risk_reasons`, `task_id` di `ai_proposals`
  (migrasi otomatis, data lama tetap; diuji pada DB v2).

## 1.3.0 — 2026-11-23
### Ditambahkan
- **Language server (LSP)**: clangd 22 (C/C++) dan pyright (Python) di Pi, lewat WebSocket `/ws/lsp`, di dalam
  sandbox bubblewrap (proyek read-only, tanpa jaringan, path asli disamarkan). Editor: autocomplete dari LSP,
  error/peringatan saat mengetik, **Info simbol di kursor**, **Ke definisi** lintas file (membuka file tujuan).
  Sakelar di Pengaturan → Editor. Dipasang otomatis tanpa sudo oleh `install_runtimes.sh`.
- **Build C/C++ multi-file**: CMake (Ninja, compile_commands.json), Makefile (`make run` / executable terbaru),
  dan mode otomatis multi-file dengan deteksi `main()`.
- **AI mengubah file proyek**: proposal dari jawaban AI (file utuh atau SEARCH/REPLACE toleran spasi/indentasi),
  kartu diff Terapkan/Tolak/Batalkan di aplikasi, sakelar terapkan otomatis, tab editor dimuat ulang, proposal basi
  ditolak, editan bisa dibatalkan.
### Diperbaiki
- Pesan error job tampil sebagai `\n` literal di output.

## 1.2.0 — 2026-11-23 (Android)
### Ditambahkan
- **Pilihan tema aplikasi** (Pengaturan → Tampilan): mode Ikuti sistem / Gelap / Terang, 11 warna aksen (Biru, Teal,
  Hijau, Ungu, Nila, Oranye, Merah, Merah muda, Kuning, Abu-abu, **Dinamis** = Material You dari wallpaper, Android 12+),
  dan latar **hitam pekat AMOLED**. Ikon status bar menyesuaikan tema. Disimpan di DataStore.
- **Preset warna editor** di dialog Warna editor: One Dark, Dracula, Monokai, Nord, Solarized Gelap/Terang,
  GitHub Gelap/Terang, Hitam AMOLED, Kertas (sekaligus memilih editor gelap/terang).
- Unit test tema (`ThemeTest`).

## 1.1.1 — 2026-11-23
### Ditambahkan
- `scripts/uninstall.sh`: hapus service systemd (system/user) + cron autostart, hentikan proses tersisa, bersihkan
  `.venv`, log, cache, PID, `__pycache__`. Opsi `--purge` (hapus data setelah backup akhir terverifikasi),
  `--remove-runtimes`, `--remove-repo`, `--dry-run`, `-y`. Penghapusan dibatasi ke folder instalasi.
- `CS_SERVICE_NAME` untuk menjalankan instalasi kedua (mis. uji) berdampingan dengan nama service berbeda.
- `install_runtimes.sh` mencatat runtime yang dipasangnya (`deployment/configuration/.installed_runtimes`).
### Diperbaiki
- Skrip mengenali unit systemd hanya dari namanya: `stop.sh`/`start.sh` dari salinan lain bisa mematikan service
  utama, dan installer salinan bisa menimpa unit-nya. Kini unit dianggap milik instalasi ini hanya bila `ExecStart`
  menunjuk ke folder ini; installer menolak menimpa unit milik folder lain.
- Pembersihan cron hanya menghapus baris milik folder ini (sebelumnya semua baris ber-marker).
- `status.sh` tidak lagi membuat ulang folder `logs/`/`workspace/` dan memberi pesan jelas bila venv tidak ada.
- Versi backend (`/system/health`) masih 1.0.0 padahal rilis 1.1.0 → kini 1.1.1.

## 1.1.0 — 2026-11-20
### Ditambahkan
- **AI Chat & Model AI** (konsep seperti ai_asisten): koneksi **lokal** (llama-server mode router di Pi, Ollama, server
  OpenAI-compatible lain) dan **online** (OpenAI, OpenRouter, Groq, DeepSeek, Anthropic, Google Gemini, custom).
  Alur: pilih Lokal/Online → koneksi → model → **Terapkan**. Model lokal dimuat saat diterapkan, model lama dibongkar,
  dan dibongkar otomatis bila idle (default 15 menit). API key terenkripsi, tidak pernah dikirim ke HP.
- Chat streaming via WebSocket `/ws/ai/chat` (proses berpikir model ditampilkan terpisah), riwayat percakapan per
  pengguna, sertakan file yang terbuka di editor sebagai konteks, blok kode bisa disalin / disisipkan ke editor,
  tombol "Tanya AI tentang error ini" di Build Output.
- Info versi APK di header menu samping (selain di Pengaturan → Pembaruan aplikasi).
### Diperbaiki
- Editor tidak bisa mengetik di sebagian HP: CodeMirror di Android memakai API EditContext yang input keyboard-nya
  tidak sampai ke editor pada sebagian WebView/keyboard → dimatikan (pakai contenteditable). WebView editor/terminal
  kini memakai context Activity + fokus saat disentuh; konten diberi `imePadding` (Android 15 edge-to-edge) agar baris
  yang diketik tidak tertutup keyboard; editor tanpa file terbuka kini read-only dengan petunjuk + tombol **File baru**.


## 1.0.0 — 2026-11-20
### Ditambahkan
- Backend FastAPI modular: auth (scrypt, JWT access/refresh rotasi, pencabutan, rate limit), izin berbasis peran, audit log.
- File & project manager aman (traversal/symlink), tulis atomik, deteksi konflik, riwayat versi & restore, favorit, file terakhir, pencarian.
- Execution manager: antrean, batas job bersamaan, cek RAM, timeout, watchdog RAM, rlimit, batas output, cancel, stdin, streaming WebSocket, riwayat.
- 11 engine: Python, Node.js, PHP, Go, C, C++, Java, C#, SQLite, HTML/CSS (pratinjau), Bash — semuanya lolos uji di Raspberry Pi 5 ARM64.
- Sandbox bubblewrap untuk eksekusi, terminal, dan Git.
- Terminal PTY multi-sesi lewat WebSocket.
- Database manager SQLite, Git manager (token terenkripsi), HTTP client anti-SSRF, system monitor, backup/restore terverifikasi + backup harian otomatis, fondasi AI agent.
- Web editor CodeMirror 6 + terminal xterm.js (bundel offline).
- Aplikasi Android (Compose) lengkap 12 halaman, update otomatis dari GitHub Releases, CI build APK + uji kontrak API.
- Skrip instalasi, systemd (system & user), health check, backup CLI, dokumentasi.

### Diperbaiki selama pengujian
- Terminal: `pty.fork()` di proses multi-thread → `subprocess` + `setsid --ctty`; `remove_reader` sebelum `close(fd)` (fd pidfd dicuri callback terminal sehingga eksekusi berikutnya menggantung).
- Engine memakai path asli executable (symlink di `~/.local/bin` tidak ada di sandbox).
- .NET: lock `~/.dotnet/corefx` writable & W^X dimatikan (SIGXFSZ).
- Pemisahan pernyataan SQL per karakter `;` (bukan per baris).
