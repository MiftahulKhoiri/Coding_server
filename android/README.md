# Coding Server — Android

Klien remote IDE untuk CODING_SERVER. Detail lengkap: [../docs/ANDROID.md](../docs/ANDROID.md).

- **Unduh APK**: GitHub Releases → tag `android-latest` → `CodingServer.apk` (dibuat otomatis oleh CI setiap push ke `main`).
- **Update**: di aplikasi, Pengaturan → Periksa pembaruan.
- **Tanda tangan rilis**: isi secret repo `ANDROID_KEYSTORE_PASSWORD` dengan isi file
  `~/.coding_server_signing/ANDROID_KEYSTORE_PASSWORD` di Raspberry Pi. Sampai secret diisi, CI memakai kunci debug
  (APK tetap jalan; saat beralih ke kunci rilis, hapus aplikasi sekali lalu pasang ulang).
  Cadangan kunci asli: `~/.coding_server_signing/release.jks` — simpan juga di tempat aman lain.
- **Build lokal di Pi**: lihat docs/ANDROID.md bagian "Build lokal".
