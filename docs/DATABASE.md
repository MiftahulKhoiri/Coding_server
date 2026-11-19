# Database Manager (SQLite)

Dua jenis lokasi:
- **DB saya** — `workspace/database/<user_id>/<nama>.db` (tanpa `project_id`).
- **DB di proyek** — file `.db/.sqlite/.sqlite3` di folder proyek (dengan `project_id`, path relatif).

| Fitur | Endpoint |
|---|---|
| Daftar / buat database | `GET /database/list`, `POST /database/create` |
| Eksekusi SQL (beberapa pernyataan) | `POST /database/query {database, project_id?, sql, mode: read|write, confirm}` |
| Skema (tabel, view, index, trigger, kolom, jumlah baris) | `GET /database/schema` |
| Select/insert/update/delete/create/drop table | lewat `/database/query` |
| Export CSV / Import CSV | `GET /database/export?table=`, `POST /database/import` |
| Backup (dengan `integrity_check`) | `POST /database/backup` → `backups/databases/` |

Pemisahan baca/tulis: mode `read` membuka koneksi `mode=ro` + authorizer yang menolak operasi tulis;
mode `write` berjalan dalam transaksi. DROP/DELETE/ALTER/DETACH tanpa `confirm=true` di-*rollback* dan
dijawab 409 `confirmation_required` (APK menampilkan dialog konfirmasi). `ATTACH`, `load_extension`,
`readfile/writefile` selalu ditolak. Hasil query dibatasi 1000 baris per pernyataan.

File `.sql` juga bisa dijalankan sebagai program (engine `sql`), hasil dicetak sebagai tabel teks.
