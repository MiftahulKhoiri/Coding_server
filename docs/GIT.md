# Git Manager

Endpoint `/api/v1/git/*`: `status, init, add, commit, log, branches, branch, checkout, diff, remote, pull, push, clone, credentials`.

- Semua perintah dijalankan sebagai **daftar argumen** dengan validasi: nama branch/ref (regex, tidak boleh diawali `-`,
  tanpa `..`), nama remote, URL hanya `https://` tanpa user/password di dalam URL.
- Konfigurasi aman paksa: `core.hooksPath=/dev/null`, `core.fsmonitor=false`, `protocol.ext.allow=never`,
  `credential.helper=` (kosong), `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_TERMINAL_PROMPT=0`.
- Dijalankan di sandbox bwrap (jaringan hanya untuk pull/push/clone).
- Identitas commit = username CODING_SERVER (`<user>@coding-server.local`).
- **Token**: `POST /git/credentials {host:"github.com", username, token}` → dienkripsi (Fernet, kunci turunan secret server)
  di tabel `git_credentials`. Saat push/pull, token diberikan lewat `GIT_ASKPASS` (`backend/core/git_askpass.sh`) dari
  environment — tidak pernah muncul di argumen, URL, output, maupun log (stderr juga disensor).
- Pull memakai `--ff-only` (tidak membuat merge diam-diam). Clone `--depth 50` menjadi proyek baru.

Contoh alur di APK: Git → git init → Commit semua → Set remote `https://github.com/user/repo.git` → Token Git → Push.
