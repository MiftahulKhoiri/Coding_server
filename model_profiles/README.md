# Profil Model

Satu file JSON per model AI: pengaturan khusus yang dipakai CODING_SERVER setiap kali model itu dipanggil
(AI Agent, AI Chat, Uji Model). File di folder ini dibuat & di-commit **otomatis oleh server** setelah
kalibrasi (menu **Uji Model → 🎯 Kalibrasi**) atau perubahan manual (menu **Profil Model**).

| Kolom | Arti |
|---|---|
| `model` | Nama model persis seperti di llama-server / penyedia |
| `family` | Keluarga model yang dikenali (qwen3.5, qwen3, gemma-4, llama, …) |
| `source` | `kalibrasi` (hasil uji di Pi), `manual`, `impor` |
| `status` | `ok` atau `perlu_penyesuaian` |
| `kegunaan` / `kegunaan_label` | Untuk apa model ini cocok (perencana, pelaksana coding, peninjau, penjelasan, chat) |
| `catatan` | Ringkasan hasil kalibrasi / catatan bebas |
| `prompt_tambahan` | Aturan tambahan yang ditempel ke system prompt khusus model ini |
| `preset.kualitas` | Dipakai Perencana, Peninjau, AI Chat |
| `preset.cepat` | Dipakai Pelaksana (langkah rutin agent) |
| `kalibrasi` | Bukti: skor & detik per kasus tiap varian, varian terpilih, saran |

Isi preset: `temperature`, `top_p`, `top_k`, `min_p`, `presence_penalty`, `repeat_penalty`,
`thinking` (`true`/`false`/`null` = bawaan model), `max_tokens`.

Model tanpa file di sini memakai profil **bawaan** dari rekomendasi resmi pembuat model.
Untuk memindahkan ke server lain: salin file JSON-nya, atau pakai **Ekspor / Impor** di aplikasi.
