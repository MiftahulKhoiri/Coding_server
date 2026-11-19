# Aplikasi Android

Kotlin + Jetpack Compose (Material 3), Retrofit + OkHttp (REST & WebSocket), kotlinx.serialization,
DataStore (konfigurasi), EncryptedSharedPreferences + **Android Keystore** (token, tidak pernah plaintext).
Editor = WebView memuat `assets/web/editor.html` (CodeMirror 6, dibundel dari `web_editor/`, tanpa CDN);
Terminal = WebView `assets/web/terminal.html` (xterm.js). minSdk 26 (Android 8.0), targetSdk 35.

## Halaman
| Halaman | Fungsi (semuanya memanggil backend nyata) |
|---|---|
| Koneksi Server | tambah/ubah/hapus server, tes koneksi (`/system/health`), hubungkan/putuskan, status online/offline |
| Login | `/auth/login`; token disimpan terenkripsi; refresh otomatis (rotasi) saat 401 |
| Dashboard | IP server, CPU/RAM/disk/suhu, jumlah proyek, eksekusi aktif, proyek terbaru (`/monitor/dashboard`, refresh 5 dtk) |
| Proyek | daftar, buat (dengan template bahasa), hapus, clone dari Git |
| Project Explorer | pohon folder (lazy), buka, buat file/folder, ganti nama, salin, pindah, hapus, cari nama/isi, favorit, refresh, jalankan |
| Code Editor | banyak tab, simpan (deteksi konflik SHA-256), simpan sebagai, run, build, undo/redo, cari & ganti, ke baris, simbol, ke definisi, fold, word wrap, font, tema, riwayat versi/restore |
| Terminal | banyak sesi PTY, xterm.js, tombol ESC/TAB/Ctrl-C/D/Z/L/panah, tutup sesi |
| Build Output | status, fase build/run, stdout/stderr real-time berwarna, stdin, Stop, exit code, durasi, lokasi artefak, error compiler yang bisa diklik (lompat ke baris + diagnostics di editor), riwayat eksekusi, pratinjau HTML |
| Database | DB pengguna / DB di proyek, buat DB, skema, query mode baca/tulis, tabel hasil, konfirmasi operasi destruktif |
| Git | init, status, commit, pull, push, diff, branch, checkout, remote, token Git (disimpan terenkripsi di server), log |
| HTTP Client | method, URL, header, query, body (json/form/raw), status/waktu/header/body (JSON dirapikan), koleksi tersimpan |
| Server Monitor | CPU per core, RAM, disk, suhu, uptime, jaringan, job, status & versi compiler, proses teratas (admin) |
| Pengaturan | akun & logout, preferensi editor, **periksa & pasang pembaruan APK**, status AI, backup (admin) |

Bila server tidak bisa dihubungi, aplikasi tetap berjalan dan menampilkan banner **OFFLINE** (health dicek
tiap 5–15 detik) — tidak ada data palsu.

## Build & rilis otomatis
Workflow `.github/workflows/android.yml` pada setiap push ke `main` yang mengubah `android/**` atau `web_editor/**`:
1. build aset editor (`npm ci && npm run build`),
2. menjalankan backend asli lalu `testDebugUnitTest` (unit test + **uji kontrak API** ke backend),
3. `assembleRelease` (R8/minify), 4. menerbitkan **CodingServer.apk** ke GitHub Release `android-latest`
   dengan judul `Coding Server Android (build #N)`; N = `versionCode`.

Aplikasi membaca rilis itu (Pengaturan → Periksa pembaruan), mengunduh, memverifikasi ukuran & SHA-256,
lalu memasang lewat `PackageInstaller` (Android meminta konfirmasi).

## Penandatanganan APK
- Kunci rilis: `android/signing/release.jks.enc` (AES-256, PBKDF2 600k). Password-nya **tidak** ada di repo;
  salinannya disimpan di Raspberry Pi: `~/.coding_server_signing/ANDROID_KEYSTORE_PASSWORD` (0600).
- Isi secret repo **`ANDROID_KEYSTORE_PASSWORD`** (GitHub → Settings → Secrets and variables → Actions) dengan isi file itu.
- Sebelum secret diisi, CI tetap membuat APK tetapi ditandatangani **kunci debug** (ada peringatan di catatan rilis).
  Setelah secret diisi, tanda tangan berubah → **hapus aplikasi sekali** lalu pasang APK baru; setelah itu update otomatis lancar.

## Build lokal di Raspberry Pi (ARM64)
```bash
cd android
echo "sdk.dir=$HOME/android-sdk" > local.properties
./gradlew -Pcodingserver.localArm64 -Pcodingserver.allowDebugSigning \
  -Pandroid.aapt2FromMavenOverride=$HOME/android-sdk/aapt2-arm64/aapt2 testDebugUnitTest assembleDebug
# uji kontrak ke server lokal:
CS_SERVER_URL=http://127.0.0.1:8800 CS_ADMIN_PASSWORD=... ./gradlew ... testDebugUnitTest
```
`localArm64` memakai compileSdk 34 karena aapt2 ARM64 belum membaca android.jar API 35; APK resmi tetap dari CI (API 35).
