"""Profil model: pengaturan khusus per model (sampling, mode berpikir, max token, prompt tambahan, kegunaan).

* Satu file JSON per model di ``model_profiles/`` (ikut repo) -> bisa dipakai ulang / dipindah ke server lain.
* Profil awal ("bawaan") diambil dari rekomendasi resmi pembuat model berdasarkan nama file model.
* Uji Model mode "kalibrasi" mencoba 3 varian pengaturan, lalu memilih preset:
    - "kualitas": skor tertinggi  -> dipakai Perencana, Peninjau, AI Chat
    - "cepat":    varian tercepat yang skornya paling banyak 5 poin di bawah terbaik -> dipakai Pelaksana
  Hasil yang bagus disimpan otomatis; yang belum bagus menjadi draf "perlu penyesuaian" + saran.
* Setiap kali profil disimpan, file di-commit & di-push ke GitHub (bila server berada di repo git) agar
  tidak hilang. Status sinkron disimpan di DB (bukan di file, supaya file tetap bersih setelah commit).
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path

from backend.config import Settings
from backend.core.exceptions import AppError, NotFound
from backend.core.logging import get_logger
from backend.database.db import Database

log = get_logger("profiles")

PURPOSES = {
    "perencana": "Perencana (memahami tugas & menyusun rencana)",
    "pelaksana_coding": "Pelaksana coding (edit file, build, test)",
    "peninjau": "Peninjau hasil kerja agent",
    "spesialis_coding": "Spesialis coding (tugas kode sulit)",
    "penjelasan_coding": "Penjelasan kode / tanya-jawab teknis",
    "chat_umum": "Chat umum",
}
PRESET_KEYS = ("temperature", "top_p", "top_k", "min_p", "presence_penalty", "repeat_penalty", "thinking", "max_tokens")
GOOD_SCORE = 60          # skor minimal agar hasil kalibrasi disimpan otomatis
FAST_TOLERANCE = 5       # preset "cepat" boleh sampai 5 poin di bawah skor terbaik


def _p(temperature, top_p, top_k=None, min_p=None, presence=None, repeat=None, thinking=None, max_tokens=2048) -> dict:
    return {"temperature": temperature, "top_p": top_p, "top_k": top_k, "min_p": min_p, "presence_penalty": presence,
            "repeat_penalty": repeat, "thinking": thinking, "max_tokens": max_tokens}


# Rekomendasi resmi per keluarga model. thinking_supported: True/False/None (tidak diketahui).
# "resmi" = mode berpikir (bila didukung), "tanpa_berpikir" = mode instruksi biasa.
FAMILIES: list[dict] = [
    {"family": "qwen3.5", "match": r"qwen3[._]?[56]", "thinking": True,
     "resmi": _p(0.6, 0.95, 20, 0.0, 0.0, thinking=True, max_tokens=4096),          # thinking, coding presisi
     "tanpa_berpikir": _p(0.7, 0.8, 20, 0.0, 1.5, thinking=False, max_tokens=2048),
     "sumber": "Qwen3.5 model card / Unsloth: thinking-coding 0.6/0.95/20, non-thinking 0.7/0.8/20 presence 1.5"},
    {"family": "qwen3", "match": r"qwen3", "thinking": True,  # qwen3.5/3.6 sudah tertangkap di atas
     "resmi": _p(0.6, 0.95, 20, 0.0, thinking=True, max_tokens=4096),
     "tanpa_berpikir": _p(0.7, 0.8, 20, 0.0, thinking=False, max_tokens=2048),
     "sumber": "Qwen3 model card: thinking 0.6/0.95/20, non-thinking 0.7/0.8/20"},
    {"family": "qwen2.5-coder", "match": r"qwen2[._]?5", "thinking": False,
     "resmi": _p(0.7, 0.8, 20, repeat=1.05, max_tokens=2048),
     "sumber": "Qwen2.5(-Coder) generation_config: 0.7/0.8/20, repetition 1.05"},
    {"family": "gemma-4", "match": r"gemma[-_ ]?4", "thinking": True,
     "resmi": _p(1.0, 0.95, 64, thinking=True, max_tokens=4096),
     "tanpa_berpikir": _p(1.0, 0.95, 64, thinking=False, max_tokens=2048),
     "sumber": "Google: Gemma 4 memakai 1.0/0.95/64 untuk semua kegunaan"},
    {"family": "gemma", "match": r"gemma", "thinking": False,
     "resmi": _p(1.0, 0.95, 64, max_tokens=2048), "sumber": "Google: Gemma 1.0/0.95/64"},
    {"family": "llama", "match": r"llama", "thinking": False,
     "resmi": _p(0.6, 0.9, max_tokens=2048), "sumber": "Meta Llama generation_config: 0.6/0.9"},
    {"family": "deepseek-r1", "match": r"deepseek[-_ ]?r1|r1[-_]distill", "thinking": True,
     "resmi": _p(0.6, 0.95, thinking=True, max_tokens=4096),
     "tanpa_berpikir": _p(0.6, 0.95, thinking=False, max_tokens=2048), "sumber": "DeepSeek-R1: 0.6/0.95"},
    {"family": "umum", "match": r".", "thinking": None,
     "resmi": _p(0.7, 0.95, max_tokens=2048), "sumber": "Bawaan umum (keluarga model tidak dikenali)"},
]


def family_of(model: str) -> dict:
    name = model.lower()
    return next(f for f in FAMILIES if re.search(f["match"], name))


def safe_name(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model).strip("._")[:150] or "model"


def clean_preset(p: dict) -> dict:
    out = {}
    for k in PRESET_KEYS:
        v = p.get(k)
        if k == "thinking":
            out[k] = None if v is None else bool(v)
        elif k == "max_tokens":
            out[k] = max(64, min(int(v or 2048), 32768))
        elif v is None or v == "":
            out[k] = None
        else:
            out[k] = round(float(v), 3)
            if k == "top_k":
                out[k] = int(out[k])
    return out


def describe(p: dict) -> str:
    bits = [f"temp {p.get('temperature')}"]
    if p.get("top_p") is not None:
        bits.append(f"top_p {p['top_p']}")
    if p.get("top_k") is not None:
        bits.append(f"top_k {p['top_k']}")
    if p.get("thinking") is not None:
        bits.append("berpikir ON" if p["thinking"] else "berpikir OFF")
    bits.append(f"max {p.get('max_tokens')} token")
    return ", ".join(bits)


class ModelProfiles:
    def __init__(self, settings: Settings, db: Database):
        self.s = settings
        self.db = db
        self.dir: Path = settings.model_profiles_dir
        self._git_lock = asyncio.Lock()

    # ---------- bawaan & varian ----------
    def default(self, model: str) -> dict:
        f = family_of(model)
        resmi = dict(f["resmi"])
        cepat = dict(f.get("tanpa_berpikir") or f["resmi"])
        return {
            "model": model, "family": f["family"], "thinking_supported": f["thinking"],
            "source": "bawaan", "status": "ok", "active": True,
            "kegunaan": ["chat_umum"], "catatan": f"Profil bawaan dari rekomendasi resmi ({f['sumber']}). "
                                                  "Jalankan Kalibrasi di Uji Model untuk menyesuaikan dengan Pi ini.",
            "prompt_tambahan": "",
            "preset": {"kualitas": clean_preset(resmi), "cepat": clean_preset(cepat)},
            "kalibrasi": None, "updated_at": None,
        }

    def variants(self, model: str) -> list[dict]:
        """3 varian kalibrasi. Model berpikir: resmi+berpikir / resmi tanpa berpikir / suhu rendah tanpa berpikir.
        Model tanpa mode berpikir: resmi / seimbang (0.5) / suhu rendah (0.2)."""
        f = family_of(model)
        resmi = clean_preset(f["resmi"])
        if f["thinking"] is False:
            mid = dict(resmi, temperature=0.5)
            low = dict(resmi, temperature=0.2)
            return [
                {"key": "A", "label": "Resmi", "params": resmi},
                {"key": "B", "label": "Seimbang (suhu 0,5)", "params": clean_preset(mid)},
                {"key": "C", "label": "Suhu rendah (0,2)", "params": clean_preset(low)},
            ]
        think = dict(resmi, thinking=True, max_tokens=max(resmi["max_tokens"], 4096))
        nothink = clean_preset(dict(f.get("tanpa_berpikir") or resmi, thinking=False))
        low = dict(nothink, temperature=0.2)
        return [
            {"key": "A", "label": "Resmi + berpikir", "params": clean_preset(think)},
            {"key": "B", "label": "Resmi tanpa berpikir", "params": nothink},
            {"key": "C", "label": "Suhu rendah tanpa berpikir", "params": clean_preset(low)},
        ]

    # ---------- penyimpanan ----------
    def path(self, model: str) -> Path:
        return self.dir / f"{safe_name(model)}.json"

    def stored(self, model: str) -> dict | None:
        p = self.path(model)
        if not p.is_file():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            log.warning("Profil %s rusak: %s", p.name, e)
            return None
        return self._normalize(data, model)

    def _normalize(self, data: dict, model: str) -> dict:
        base = self.default(model)
        base.update({k: v for k, v in data.items() if k in base})
        presets = data.get("preset") or {}
        base["preset"] = {k: clean_preset({**self.default(model)["preset"][k], **(presets.get(k) or {})})
                          for k in ("kualitas", "cepat")}
        base["kegunaan"] = [k for k in (data.get("kegunaan") or []) if k in PURPOSES] or ["chat_umum"]
        base["model"] = model
        return base

    def get(self, model: str) -> dict:
        prof = self.stored(model) or self.default(model)
        prof["sync"] = self.sync_status(model)
        prof["file"] = self.path(model).name
        return prof

    def list(self, models: list[str]) -> list[dict]:
        names = set(models)
        if self.dir.is_dir():
            for p in self.dir.glob("*.json"):
                try:
                    names.add(json.loads(p.read_text(encoding="utf-8")).get("model") or p.stem)
                except (OSError, json.JSONDecodeError):
                    continue
        return sorted((self.get(m) for m in names), key=lambda x: (x["source"] == "bawaan", x["model"].lower()))

    def save(self, profile: dict, source: str, sync: bool = True) -> dict:
        model = profile["model"]
        prof = self._normalize(profile, model)
        prof["source"] = source
        prof["updated_at"] = time.time()
        self.dir.mkdir(parents=True, exist_ok=True)
        data = {k: prof[k] for k in ("model", "family", "thinking_supported", "source", "status", "active",
                                     "kegunaan", "catatan", "prompt_tambahan", "preset", "kalibrasi", "updated_at")}
        data["kegunaan_label"] = [PURPOSES[k] for k in prof["kegunaan"]]
        tmp = self.path(model).with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path(model))
        log.info("Profil %s disimpan (%s)", model, source)
        if sync:
            self.schedule_sync(model, f"profil model {model}: {source}")
        return self.get(model)

    def update(self, model: str, patch: dict) -> dict:
        """Ubahan manual dari aplikasi (sumber jadi "manual")."""
        prof = self.stored(model) or self.default(model)
        for k in ("active", "catatan", "prompt_tambahan"):
            if patch.get(k) is not None:
                prof[k] = patch[k]
        if patch.get("kegunaan") is not None:
            prof["kegunaan"] = [k for k in patch["kegunaan"] if k in PURPOSES]
        for pk in ("kualitas", "cepat"):
            if patch.get(pk):
                prof["preset"][pk] = clean_preset(patch[pk])
        prof["status"] = "ok"
        return self.save(prof, "manual")

    def import_profile(self, data: dict) -> dict:
        model = str(data.get("model") or "").strip()
        if not model:
            raise AppError("File profil tidak berisi nama model", code="bad_profile")
        return self.save(self._normalize(data, model), "impor")

    def delete(self, model: str) -> dict:
        p = self.path(model)
        if p.is_file():
            p.unlink()
            self.schedule_sync(model, f"profil model {model}: dikembalikan ke bawaan", removed=True)
        return self.get(model)

    # ---------- dipakai saat memanggil model ----------
    def request_options(self, conn_row: dict, model: str, preset: str) -> dict | None:
        """Opsi permintaan dari profil; None = profil dimatikan (pakai pengaturan lama)."""
        prof = self.stored(model) or self.default(model)
        if not prof.get("active", True):
            return None
        p = prof["preset"].get(preset) or prof["preset"]["kualitas"]
        return self.options_from(conn_row, p, prof.get("thinking_supported"), prof.get("prompt_tambahan") or "")

    @staticmethod
    def options_from(conn_row: dict, p: dict, thinking_supported, prompt_extra: str = "") -> dict:
        extra: dict = {}
        local = conn_row.get("location") == "local" or conn_row.get("kind") == "llama_router"
        if p.get("top_p") is not None:
            extra["top_p"] = p["top_p"]
        if conn_row.get("kind") in ("anthropic", "gemini") and p.get("top_k") is not None:
            extra["top_k"] = p["top_k"]
        if local:  # parameter khusus llama-server/Ollama; API online bisa menolak parameter yang tidak dikenal
            for k in ("top_k", "min_p", "presence_penalty"):
                if p.get(k) is not None:
                    extra[k] = p[k]
            if p.get("repeat_penalty") is not None:
                extra["repeat_penalty"] = p["repeat_penalty"]
            if p.get("thinking") is not None and thinking_supported is not False:
                extra["chat_template_kwargs"] = {"enable_thinking": bool(p["thinking"])}
        return {"temperature": p.get("temperature"), "max_tokens": p.get("max_tokens") or 2048, "extra": extra,
                "prompt_extra": prompt_extra.strip(), "thinking": p.get("thinking")}

    @staticmethod
    def with_prompt_extra(messages: list[dict], prompt_extra: str) -> list[dict]:
        if not prompt_extra or not messages or messages[0].get("role") != "system":
            return messages
        first = dict(messages[0], content=messages[0]["content"] + "\n\nAturan khusus model ini:\n" + prompt_extra)
        return [first, *messages[1:]]

    # ---------- keputusan kalibrasi ----------
    def decide(self, model: str, variants: list[dict], run_id: str) -> dict:
        """Pilih preset kualitas & cepat dari hasil varian; tentukan simpan otomatis atau perlu penyesuaian."""
        done = [v for v in variants if v.get("summary")]
        if not done:
            return {"saved": False, "status": "perlu_penyesuaian", "saran": ["Tidak ada varian yang selesai diuji."]}
        def ok_format(v):
            s = v["summary"]
            return s["format_ok"] == s["total"]
        candidates = [v for v in done if ok_format(v)] or done
        best = max(candidates, key=lambda v: (v["summary"]["score"], -v["summary"]["avg_seconds"]))
        best_score = best["summary"]["score"]
        fast_pool = [v for v in candidates if v["summary"]["score"] >= best_score - FAST_TOLERANCE]
        fast = min(fast_pool, key=lambda v: (v["summary"]["avg_seconds"], -v["summary"]["score"]))

        saran: list[str] = []
        if best_score < GOOD_SCORE:
            saran.append(f"Skor terbaik {best_score} masih di bawah {GOOD_SCORE}: model ini belum cocok untuk agent "
                         "coding. Pakai untuk chat/penjelasan, atau coba prompt tambahan lalu kalibrasi ulang.")
        if not any(ok_format(v) for v in done):
            saran.append("Semua varian pernah salah format JSON tool. Coba isi 'prompt tambahan', mis. "
                         "\"Balas hanya satu blok ```json dan tulis isi file di blok kode terpisah.\"")
        for v in done:
            if v["summary"].get("empty_answers"):
                saran.append(f"Varian {v['key']} ({v['label']}): {v['summary']['empty_answers']} jawaban kosong karena "
                             "token habis untuk berpikir — naikkan max_tokens untuk mode berpikir.")
        if fast["summary"]["avg_seconds"] > 300:
            saran.append(f"Rata-rata {int(fast['summary']['avg_seconds'])} dtk/kasus: terlalu lambat untuk Pelaksana di Pi.")

        good = best_score >= GOOD_SCORE and ok_format(best)
        kegunaan = ["chat_umum"]
        if best_score >= 60:
            kegunaan.append("penjelasan_coding")
        if best_score >= 80:
            kegunaan += ["perencana", "peninjau", "spesialis_coding"]
        if fast["summary"]["score"] >= 60 and fast["summary"]["avg_seconds"] <= 300:
            kegunaan.append("pelaksana_coding")
        tanggal = time.strftime("%d %b %Y", time.localtime())
        prev = self.stored(model)
        prof = prev or self.default(model)
        prof.update({
            "status": "ok" if good else "perlu_penyesuaian",
            "kegunaan": list(dict.fromkeys(kegunaan)),
            "catatan": (f"Kalibrasi {tanggal}: kualitas = varian {best['key']} ({best['label']}, skor {best_score}, "
                        f"{int(best['summary']['avg_seconds'])} dtk/kasus); cepat = varian {fast['key']} ({fast['label']}, "
                        f"skor {fast['summary']['score']}, {int(fast['summary']['avg_seconds'])} dtk/kasus)."),
            "preset": {"kualitas": best["params"], "cepat": fast["params"]},
            "kalibrasi": {
                "tanggal": time.time(), "run_id": run_id, "pilihan": {"kualitas": best["key"], "cepat": fast["key"]},
                "varian": [{"key": v["key"], "label": v["label"], "params": v["params"],
                            **{k: v["summary"].get(k) for k in ("score", "avg_seconds", "format_ok", "total", "passed",
                                                                 "avg_tps", "thinking_tokens")}} for v in done],
                "saran": saran,
            },
        })
        result = {"saved": False, "status": prof["status"], "saran": saran, "draft": prof,
                  "pilihan": {"kualitas": best["key"], "cepat": fast["key"]}}
        if good:
            self.save(prof, "kalibrasi")
            result["saved"] = True
        return result

    # ---------- sinkron GitHub ----------
    def _meta_key(self, model: str) -> str:
        return f"profile_sync:{safe_name(model)}"

    def sync_status(self, model: str) -> dict | None:
        row = self.db.one("SELECT value FROM meta WHERE key=?", (self._meta_key(model),))
        return json.loads(row["value"]) if row else None

    def _set_sync(self, model: str, status: str, message: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)", (self._meta_key(model), json.dumps(
            {"status": status, "message": message[:300], "at": time.time()})))

    def schedule_sync(self, model: str, message: str, removed: bool = False) -> None:
        if not self.s.model_profiles_git:
            self._set_sync(model, "tidak_aktif", "Sinkron GitHub dimatikan (CS_MODEL_PROFILES_GIT=0)")
            return
        try:
            asyncio.get_running_loop().create_task(self.sync(model, message, removed))
        except RuntimeError:  # tidak ada event loop (mis. skrip): lewati
            self._set_sync(model, "tertunda", "Belum disinkronkan")

    async def _git(self, *args: str, timeout: int = 60) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_exec(
            "git", *args, cwd=str(self.s.base_dir), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(Path.home()), "GIT_TERMINAL_PROMPT": "0"})
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return 124, "timeout"
        return proc.returncode, out.decode(errors="replace").strip()

    async def sync(self, model: str, message: str = "", removed: bool = False) -> dict | None:
        """Commit file profil (hanya file itu) lalu push ke GitHub. Tidak pernah menarik (pull) kode lain."""
        if not (self.s.base_dir / ".git").exists():
            self._set_sync(model, "tidak_aktif", "Folder server bukan repo git")
            return self.sync_status(model)
        rel = str(self.path(model).relative_to(self.s.base_dir)) if self.path(model).is_relative_to(self.s.base_dir) \
            else None
        if rel is None:
            self._set_sync(model, "tidak_aktif", "Folder profil di luar repo")
            return self.sync_status(model)
        async with self._git_lock:
            if removed:
                await self._git("rm", "-q", "--cached", "--ignore-unmatch", "--", rel)
            else:
                code, out = await self._git("add", "--", rel)
                if code:
                    self._set_sync(model, "gagal", f"git add: {out}")
                    return self.sync_status(model)
            code, out = await self._git("commit", "-q", "-m", f"chore(model-profiles): {message or model}", "--", rel)
            if code and "nothing" not in out and "no changes" not in out:
                self._set_sync(model, "gagal", f"git commit: {out}")
                return self.sync_status(model)
            code, out = await self._git("push", "-q", "origin", "HEAD", timeout=120)
            if code:
                self._set_sync(model, "gagal", "Tersimpan di server, belum ter-push ke GitHub: " + out)
                log.warning("Push profil %s gagal: %s", model, out)
            else:
                self._set_sync(model, "ok", "Tersimpan di server & GitHub")
        return self.sync_status(model)
