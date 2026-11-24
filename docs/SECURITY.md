# Keamanan

## Yang diterapkan
| Kontrol | Implementasi |
|---|---|
| Password | scrypt (n=2^14, r=8, p=1, salt 16 byte); waktu respons login konstan untuk user tak dikenal |
| Token | JWT HS256, access 12 jam, refresh 30 hari **sekali pakai** (rotasi), logout mencabut `jti`; secret 64 byte acak (0600) |
| Rate limit | login/refresh 10/menit/IP; API 600/menit/token |
| Izin | read, write, delete, execute, build, terminal, admin; peran admin/developer/runner/viewer/ai |
| Isolasi proyek | user hanya mengakses proyek miliknya (admin semua) |
| Path | normalisasi, tolak `..`/absolut/NUL, cek setiap komponen symlink, tolak tulis lewat symlink, hapus symlink tidak mengikuti target, operasi di root proyek ditolak |
| Tulis file | atomik (tmp + fsync + `os.replace`, `O_NOFOLLOW`), deteksi konflik SHA-256, snapshot riwayat |
| Eksekusi | argumen list (tanpa shell), engine dipilih dari ekstensi, timeout/CPU/RAM/file-size/output limit, antrean, pembatalan |
| **Sandbox** | **bubblewrap**: `--unshare-all` (user, pid, ipc, uts, net, cgroup), `--die-with-parent`, `--new-session`, `/usr` `/etc` read-only, `$HOME` & `/tmp` tmpfs, hanya proyek + cache yang writable, `--clearenv`. Diuji: kunci `~/.ssh` tidak terlihat, `/etc/shadow` tak terbaca, jaringan putus, tulis di luar proyek gagal |
| Git | hooks dimatikan (`core.hooksPath=/dev/null`), `protocol.ext` dilarang, hanya URL `https://` tanpa kredensial, validasi ref/remote, dijalankan di sandbox; token disimpan **Fernet** (kunci turunan secret server) dan diberikan via `GIT_ASKPASS` (tidak pernah di argumen/URL/log) |
| HTTP client | hanya http/https; tolak loopback, link-local (169.254.x / metadata cloud), reserved, multicast (termasuk bentuk IPv4-mapped/NAT64/6to4); jaringan privat & CGNAT ditolak kecuali `CS_HTTP_ALLOW_PRIVATE=true`; **IP diperiksa saat koneksi dibuat** (anti DNS rebinding) dan di setiap redirect; body respons ≤ 2 MB |
| Database | mode baca memakai koneksi read-only + authorizer; `ATTACH`/`load_extension` ditolak; operasi destruktif butuh `confirm=true` |
| Audit | login, gagal login, eksekusi, build, hapus, terminal, git, backup, perubahan user → `audit_log` + `logs/audit.log` |
| Log | token/password disensor; access log uvicorn mati (query `?token=`) |
| Service | tidak pernah root (skrip menolak root), systemd `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=full` |
| Android | token di EncryptedSharedPreferences (kunci Android Keystore); APK update diverifikasi SHA-256 & tanda tangan |
| AI | hak AI = irisan hak user ∩ peran `ai` (tanpa terminal/admin/delete); perubahan berupa proposal yang butuh persetujuan, tercatat & bisa di-undo; risiko LOW/MEDIUM/HIGH, HIGH tidak pernah auto-apply & butuh konfirmasi eksplisit |
| Agen AI | tanpa shell; tool berskema & ber-izin; eksekusi lewat sandbox yang sama; perintah uji disusun server; lihat `AI_AGENT.md` |
| Pencarian | pencarian isi tidak pernah membaca lewat symlink |

## Batasan yang perlu diketahui
- HTTP tanpa TLS secara default (jaringan rumah). Untuk akses dari internet: pasang reverse proxy HTTPS (Caddy/nginx) atau VPN (Tailscale/WireGuard); jangan buka port 8800 ke internet.
- Sandbox bwrap bergantung pada user namespace kernel. Bila tidak tersedia, mode `auto`/`bwrap` **menolak** eksekusi, terminal, git, dan LSP (`503 sandbox_unavailable`); menjalankan tanpa isolasi hanya mungkin bila dipilih eksplisit `CS_SANDBOX=none`. Status terlihat di `/system/health` → `sandbox`.
- Terminal sengaja punya jaringan (bisa dimatikan `CS_TERMINAL_NETWORK=false`).
