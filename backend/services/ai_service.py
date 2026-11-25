"""AI: chatbot dengan model lokal atau online + fondasi AI Coding Agent.

Konsep (seperti ai_asisten):
* Koneksi (penyedia) dikelola admin: lokal (llama-server mode router di Pi, Ollama, server lain)
  atau online (OpenAI, OpenRouter, Groq, DeepSeek, Anthropic, Gemini, custom). API key disimpan
  terenkripsi dan tidak pernah dikirim balik ke klien.
* Di halaman "Model AI": pilih Lokal/Online -> koneksi -> model -> Terapkan. Model llama-server
  baru DIMUAT saat diterapkan, model lama yang kita muat DIBONGKAR, dan model dibongkar otomatis
  bila idle (CS_AI_IDLE_UNLOAD_MINUTES / pengaturan).
* Chat streaming lewat WebSocket, riwayat percakapan tersimpan per pengguna.
* Hak AI = irisan hak pengguna dan peran 'ai'. Perubahan file oleh AI berupa proposal yang harus
  disetujui, dicatat di riwayat file (actor_type='ai') sehingga bisa diperiksa & dibatalkan.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import time
from pathlib import Path
from typing import AsyncIterator

from backend.config import Settings
from backend.core.exceptions import AppError, Conflict, Forbidden, NotFound
from backend.core.logging import get_logger
from backend.core.permissions import intersect_for_ai
from backend.database.db import Database
from backend.services.ai_edits import EDIT_PROTOCOL, Edit, EditError, apply_replace, looks_truncated, parse_edits, unified_diff
from backend.services.ai_risk import HIGH, classify_change
from backend.services.ai_providers import PRESETS, Provider, make_provider, normalize_base
from backend.services.file_service import FileService
from backend.services.secret_store import SecretStore

log = get_logger("ai")

DEFAULT_SETTINGS = {
    "system_prompt": "Kamu adalah asisten pemrograman di CODING_SERVER (Raspberry Pi 5). Jawab dalam bahasa "
                     "pengguna, ringkas dan tepat. Tulis kode dalam blok ``` dengan nama bahasa.",
    "temperature": 0.7,
    "max_tokens": 2048,
    "idle_unload_minutes": 15,
    "history_messages": 20,
}
MAX_CONTEXT_CHARS = 60_000

# Peran model untuk AI Coding Agent. None = pakai model aktif (menu Model AI) seperti sebelumnya.
AGENT_ROLES = ("planner", "executor", "reviewer", "online")
DEFAULT_AGENT_MODELS = {
    "planner": None,        # memahami tugas, memeriksa proyek, menyusun rencana; target eskalasi pertama
    "executor": None,       # langkah rutin: baca/edit file, jalankan build/test
    "reviewer": None,       # meninjau hasil sebelum task dinyatakan selesai (opsional)
    "online": None,         # model online untuk eskalasi terakhir (hanya bila allow_online)
    "allow_online": False,  # 100% lokal secara default
    "escalate_after_failures": 2,  # verifikasi gagal berturut-turut sebelum eskalasi
    "max_loaded_models": 2,        # model lokal yang boleh termuat bersamaan (RAM Pi)
}


class AIService:
    def __init__(self, settings: Settings, db: Database, files: FileService):
        self.s = settings
        self.db = db
        self.files = files
        self.secrets = SecretStore(settings.secret_key)
        self._lock = asyncio.Lock()
        self.state: dict = {"status": "idle", "connection_id": None, "model": None, "message": "",
                            "loaded_by_us": False, "last_activity": 0.0, "target": None}
        # Model llama-server yang dimuat untuk agent / Uji Model (selain model chat aktif): (cid, model) -> terakhir dipakai
        self._agent_loaded: dict[tuple[str, str], float] = {}
        # Model yang sedang dipakai agent / Uji Model (penghitung): tidak boleh dibongkar sampai dilepas.
        self._in_use: dict[tuple[str, str], int] = {}
        self._bootstrap()

    # ---------- pengaturan & koneksi ----------
    def _bootstrap(self) -> None:
        if self.db.one("SELECT 1 AS x FROM ai_connections LIMIT 1"):
            return
        now = time.time()
        self.db.execute("INSERT INTO ai_connections(id, name, kind, location, base_url, api_key, created_at) "
                        "VALUES(?,?,?,?,?,?,?)", ("llama-lokal", "llama-server lokal (Pi)", "llama_router", "local",
                                                  "http://127.0.0.1:8080", "", now))
        if self.s.ai_base_url:  # konfigurasi lama via env
            self.db.execute("INSERT INTO ai_connections(id, name, kind, location, base_url, api_key, created_at) "
                            "VALUES(?,?,?,?,?,?,?)", ("env", "Dari konfigurasi server", "openai", "local",
                                                      normalize_base(self.s.ai_base_url),
                                                      self.secrets.encrypt(self.s.ai_api_key) if self.s.ai_api_key else "",
                                                      now))
            self.save_settings({"connection_id": "env", "model": self.s.ai_model or None})

    def settings(self) -> dict:
        row = self.db.one("SELECT value FROM meta WHERE key='ai_settings'")
        data = dict(DEFAULT_SETTINGS)
        data.update({"connection_id": None, "model": None})
        if row:
            try:
                data.update(json.loads(row["value"]))
            except json.JSONDecodeError:
                pass
        return data

    def save_settings(self, patch: dict) -> dict:
        data = self.settings()
        data.update({k: v for k, v in patch.items() if v is not None or k in ("connection_id", "model")})
        self.db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('ai_settings', ?)", (json.dumps(data),))
        return data

    @staticmethod
    def _public_conn(row: dict) -> dict:
        return {"id": row["id"], "name": row["name"], "kind": row["kind"], "location": row["location"],
                "base_url": row["base_url"], "has_key": bool(row["api_key"]), "created_at": row["created_at"]}

    def presets(self) -> list[dict]:
        return PRESETS

    def connections(self) -> list[dict]:
        return [self._public_conn(r) for r in self.db.all("SELECT * FROM ai_connections ORDER BY location, name")]

    def _conn_row(self, cid: str) -> dict:
        row = self.db.one("SELECT * FROM ai_connections WHERE id=?", (cid,))
        if not row:
            raise NotFound("Koneksi AI tidak ditemukan")
        return row

    def save_connection(self, data: dict, cid: str | None = None) -> dict:
        if data.get("kind") not in ("llama_router", "openai", "anthropic", "gemini"):
            raise AppError("Jenis koneksi tidak valid", code="bad_kind")
        if data.get("location") not in ("local", "online"):
            raise AppError("Lokasi harus local/online", code="bad_location")
        base = normalize_base(data.get("base_url", ""))
        name = (data.get("name") or "").strip() or base
        if cid:
            row = self._conn_row(cid)
            key = row["api_key"]
            if data.get("api_key") is not None:  # "" = hapus kunci, None = biarkan
                key = self.secrets.encrypt(data["api_key"]) if data["api_key"] else ""
            self.db.execute("UPDATE ai_connections SET name=?, kind=?, location=?, base_url=?, api_key=? WHERE id=?",
                            (name, data["kind"], data["location"], base, key, cid))
        else:
            cid = "c" + secrets.token_hex(4)
            key = self.secrets.encrypt(data["api_key"]) if data.get("api_key") else ""
            self.db.execute("INSERT INTO ai_connections(id, name, kind, location, base_url, api_key, created_at) "
                            "VALUES(?,?,?,?,?,?,?)", (cid, name, data["kind"], data["location"], base, key, time.time()))
        return self._public_conn(self._conn_row(cid))

    def delete_connection(self, cid: str) -> None:
        self._conn_row(cid)
        if self.state["connection_id"] == cid and self.state["status"] in ("loading", "ready"):
            raise Conflict("Koneksi sedang dipakai. Bongkar model dulu.")
        self.db.execute("DELETE FROM ai_connections WHERE id=?", (cid,))
        if self.settings().get("connection_id") == cid:
            self.save_settings({"connection_id": None, "model": None})

    def provider(self, cid: str) -> tuple[dict, Provider]:
        row = self._conn_row(cid)
        key = self.secrets.decrypt(row["api_key"]) if row["api_key"] else ""
        return row, make_provider(row["kind"], row["base_url"], key or "")

    async def list_models(self, cid: str) -> list[dict]:
        _, p = self.provider(cid)
        return await p.list_models()

    # ---------- peran model agent ----------
    def _target_ok(self, t) -> bool:
        return (isinstance(t, dict) and bool(t.get("connection_id")) and bool(t.get("model"))
                and self.db.one("SELECT 1 AS x FROM ai_connections WHERE id=?", (t["connection_id"],)) is not None)

    def agent_models(self) -> dict:
        conf = self.settings().get("agent_models") or {}
        out = dict(DEFAULT_AGENT_MODELS)
        out.update({k: v for k, v in conf.items() if k in DEFAULT_AGENT_MODELS})
        for r in AGENT_ROLES:  # koneksi yang sudah dihapus = peran kosong
            if out.get(r) is not None and not self._target_ok(out[r]):
                out[r] = None
        return out

    def public_agent_models(self) -> dict:
        conf = self.agent_models()
        out = {k: conf[k] for k in DEFAULT_AGENT_MODELS if k not in AGENT_ROLES}
        for r in AGENT_ROLES:
            t = conf.get(r)
            if t:
                row = self._conn_row(t["connection_id"])
                out[r] = {"connection_id": t["connection_id"], "model": t["model"],
                          "connection_name": row["name"], "location": row["location"]}
            else:
                out[r] = None
        d = self.default_target()
        out["default"] = {"connection_id": d[0], "model": d[1]} if d else None
        return out

    def save_agent_models(self, patch: dict) -> dict:
        cur = self.agent_models()
        for k, v in patch.items():
            if k in AGENT_ROLES:
                if not v:
                    cur[k] = None
                else:
                    self._conn_row(v["connection_id"])
                    if not str(v.get("model") or "").strip():
                        raise AppError("Model wajib dipilih", code="no_model")
                    cur[k] = {"connection_id": v["connection_id"], "model": str(v["model"]).strip()}
            elif k == "allow_online" and v is not None:
                cur[k] = bool(v)
            elif k == "escalate_after_failures" and v is not None:
                cur[k] = max(1, min(int(v), 10))
            elif k == "max_loaded_models" and v is not None:
                cur[k] = max(1, min(int(v), 4))
        self.save_settings({"agent_models": cur})
        return self.public_agent_models()

    def role_target(self, role: str) -> tuple[str, str] | None:
        t = self.agent_models().get(role)
        return (t["connection_id"], t["model"]) if t else None

    def default_target(self) -> tuple[str, str] | None:
        """Model aktif (atau yang terakhir dipilih di menu Model AI walau sedang dibongkar)."""
        st = self.state
        if st["status"] == "ready" and st["model"] and st["connection_id"]:
            return st["connection_id"], st["model"]
        conf = self.settings()
        if conf.get("connection_id") and conf.get("model"):
            try:
                self._conn_row(conf["connection_id"])
                return conf["connection_id"], conf["model"]
            except NotFound:
                return None
        return None

    def connection_info(self, cid: str) -> dict:
        return self._public_conn(self._conn_row(cid))

    async def _unload_key(self, key: tuple[str, str]) -> None:
        try:
            _, p = self.provider(key[0])
            await p.unload(key[1])
            log.info("Model %s dibongkar (memberi RAM ke model lain)", key[1])
        except Exception as e:
            log.warning("Gagal membongkar %s: %s", key[1], e)
        self._agent_loaded.pop(key, None)

    async def _make_room(self, key: tuple[str, str]) -> None:
        """Bongkar model lokal yang paling lama tidak dipakai bila batas max_loaded_models tercapai."""
        limit = int(self.agent_models().get("max_loaded_models") or 2)
        st = self.state
        active = (st["connection_id"], st["model"]) if st["status"] == "ready" and st["loaded_by_us"] else None
        ours = [k for k in self._agent_loaded if k != key and k != active and not self.in_use(k)]
        count = len(ours) + (1 if active and active != key else 0)
        for k in sorted(ours, key=lambda k: self._agent_loaded[k]):
            if count < limit:
                return
            await self._unload_key(k)
            count -= 1
        if count >= limit and active and active != key and not self.in_use(active):
            await self._unload_key(active)
            st.update(status="idle", model=None, loaded_by_us=False, target=None,
                      message="Dibongkar sementara untuk memberi RAM ke agent (muat otomatis saat dipakai lagi)")

    def hold(self, cid: str, model: str) -> None:
        self._in_use[(cid, model)] = self._in_use.get((cid, model), 0) + 1

    def release(self, cid: str, model: str) -> None:
        n = self._in_use.get((cid, model), 0) - 1
        if n > 0:
            self._in_use[(cid, model)] = n
        else:
            self._in_use.pop((cid, model), None)

    def in_use(self, key: tuple[str, str] | None) -> bool:
        return bool(key and self._in_use.get(key))

    def touch(self, cid: str, model: str) -> None:
        now = time.time()
        if (cid, model) in self._agent_loaded:
            self._agent_loaded[(cid, model)] = now
        if (self.state["connection_id"], self.state["model"]) == (cid, model):
            self.state["last_activity"] = now

    async def acquire(self, cid: str, model: str, on_status=None) -> tuple[dict, Provider]:
        """Pastikan model siap dipakai agent/Uji Model (memuat di llama-server router bila perlu).

        Berbeda dengan apply(): pilihan model chat di menu Model AI tidak diubah."""
        row, prov = self.provider(cid)
        key = (cid, model)
        if not prov.supports_load:
            self.touch(cid, model)
            return row, prov
        async with self._lock:
            st = await prov.model_status(model)
            if st is None:
                raise AppError(f"Model {model} tidak ada di {row['name']}", code="no_model", status_code=502)
            if st != "loaded":
                await self._make_room(key)
                if on_status:
                    on_status(f"Memuat model {model} …")
                if st != "loading":
                    log.info("Memuat model %s untuk agent", model)
                    await prov.load(model)
                start = time.time()
                while True:
                    await asyncio.sleep(2)
                    st = await prov.model_status(model)
                    if st == "loaded":
                        break
                    if st == "failed":
                        raise AppError(f"llama-server gagal memuat {model} (RAM kurang / berkas rusak?)",
                                       code="load_failed", status_code=502)
                    if time.time() - start > 300:
                        raise AppError(f"Model {model} belum siap setelah 5 menit", code="load_timeout", status_code=502)
                    if on_status:
                        on_status(f"Memuat model {model} … {int(time.time() - start)} dtk")
                conf = self.settings()
                if (conf.get("connection_id"), conf.get("model")) == key and self.state["status"] != "loading":
                    # model chat pilihan pengguna: tandai siap lagi
                    self.state.update(status="ready", connection_id=cid, model=model, loaded_by_us=True,
                                      message="", target=None, last_activity=time.time())
                else:
                    self._agent_loaded[key] = time.time()
        self.touch(cid, model)
        return row, prov

    # ---------- status, terapkan, bongkar ----------
    async def status(self, user: dict) -> dict:
        st = dict(self.state)
        conf = self.settings()
        conn = None
        if st["connection_id"]:
            try:
                conn = self._public_conn(self._conn_row(st["connection_id"]))
            except NotFound:
                pass
        return {
            **st,
            "configured": st["status"] == "ready",
            "connection": conn,
            "settings": {k: conf.get(k) for k in DEFAULT_SETTINGS},
            "selected": {"connection_id": conf.get("connection_id"), "model": conf.get("model")},
            "ai_permissions": sorted(intersect_for_ai(user["perms"])),
            # kompatibel dengan klien lama
            "provider": conn["kind"] if conn else None, "base_url": conn["base_url"] if conn else None,
            "reachable": st["status"] == "ready",
        }

    async def apply(self, cid: str, model: str, wait: bool = False) -> dict:
        """Terapkan model: simpan pilihan, bongkar model lama milik kita, muat model baru (router)."""
        row, prov = self.provider(cid)
        if not model:
            raise AppError("Pilih model dulu", code="no_model")
        if self.state["status"] == "loading":
            raise Conflict("Masih memuat model lain, tunggu sebentar", code="busy")
        self.save_settings({"connection_id": cid, "model": model})
        self.state.update(status="loading", target=model, message=f"Menyiapkan {model} …")
        task = asyncio.create_task(self._apply(row, prov, cid, model))
        if wait:
            await task
        return dict(self.state)

    async def _apply(self, row: dict, prov: Provider, cid: str, model: str) -> None:
        async with self._lock:
            old_cid, old_model, ours = self.state["connection_id"], self.state["model"], self.state["loaded_by_us"]
            loaded_by_us = False
            try:
                if ours and old_model and (old_cid, old_model) != (cid, model) and self.in_use((old_cid, old_model)):
                    # masih dipakai agent / Uji Model: jangan dibongkar sekarang; dibersihkan nanti (idle/LRU)
                    self._agent_loaded[(old_cid, old_model)] = time.time()
                elif ours and old_model and (old_cid, old_model) != (cid, model):
                    try:
                        _, old_prov = self.provider(old_cid)
                        log.info("Membongkar model sebelumnya: %s", old_model)
                        await old_prov.unload(old_model)
                    except Exception as e:  # koneksi lama mungkin sudah dihapus
                        log.warning("Gagal membongkar %s: %s", old_model, e)
                if prov.supports_load:
                    st = await prov.model_status(model)
                    if st is None:
                        raise AppError(f"Model {model} tidak ada di {row['name']}", code="no_model")
                    if st != "loaded":
                        await self._make_room((cid, model))
                        if st != "loading":
                            log.info("Memuat model %s di %s", model, row["base_url"])
                            await prov.load(model)
                        loaded_by_us = True
                        start = time.time()
                        while True:
                            await asyncio.sleep(2)
                            st = await prov.model_status(model)
                            self.state["message"] = f"Memuat {model} … {int(time.time() - start)} dtk"
                            if st == "loaded":
                                break
                            if st == "failed":
                                raise AppError("llama-server gagal memuat model (RAM kurang / berkas rusak?)",
                                               code="load_failed")
                            if time.time() - start > 300:
                                raise AppError("Model belum siap setelah 5 menit", code="load_timeout")
                    elif old_model == model and old_cid == cid and ours:
                        loaded_by_us = True
                else:
                    models = [m["id"] for m in await prov.list_models()]
                    if models and model not in models:
                        raise AppError(f"Model {model} tidak tersedia di {row['name']}", code="no_model")
                # Model yang tadinya dimuat agent kini jadi model chat aktif (tetap "milik kita").
                was_agent = self._agent_loaded.pop((cid, model), None) is not None
                self.state.update(status="ready", connection_id=cid, model=model, message="", target=None,
                                  loaded_by_us=loaded_by_us or was_agent, last_activity=time.time())
                log.info("Model AI siap: %s (%s)", model, row["name"])
            except Exception as e:
                msg = e.message if isinstance(e, AppError) else str(e)
                log.error("Gagal menerapkan model %s: %s", model, msg)
                if loaded_by_us:
                    try:
                        await prov.unload(model)
                    except Exception:
                        pass
                self.state.update(status="error", connection_id=cid, model=None, message=msg, target=None,
                                  loaded_by_us=False)

    async def unload(self) -> dict:
        async with self._lock:
            cid, model, ours = self.state["connection_id"], self.state["model"], self.state["loaded_by_us"]
            if model and self.in_use((cid, model)):
                raise Conflict(f"Model {model} sedang dipakai AI Agent / Uji Model. Tunggu sampai selesai atau "
                               "batalkan dulu, baru bongkar.", code="model_in_use")
            if model and ours:
                try:
                    _, prov = self.provider(cid)
                    await prov.unload(model)
                    log.info("Model %s dibongkar", model)
                except Exception as e:
                    log.warning("Gagal membongkar %s: %s", model, e)
            self.state.update(status="idle", model=None, loaded_by_us=False, message="Model dibongkar", target=None)
        return dict(self.state)

    async def idle_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            try:
                minutes = int(self.settings().get("idle_unload_minutes") or 0)
                st = self.state
                if (minutes > 0 and st["status"] == "ready" and st["loaded_by_us"]
                        and not self.in_use((st["connection_id"], st["model"]))
                        and time.time() - st["last_activity"] > minutes * 60):
                    log.info("Model %s idle %d menit, dibongkar otomatis", st["model"], minutes)
                    await self.unload()
                    self.state["message"] = f"Dibongkar otomatis setelah idle {minutes} menit"
                if minutes > 0:
                    for key, used in list(self._agent_loaded.items()):
                        if time.time() - used > minutes * 60 and not self.in_use(key):
                            async with self._lock:
                                if key in self._agent_loaded and time.time() - self._agent_loaded[key] > minutes * 60:
                                    await self._unload_key(key)
            except Exception as e:
                log.warning("idle_loop: %s", e)

    async def restore_on_start(self) -> None:
        """Saat server mulai: model online/lokal-tanpa-router langsung siap; router hanya bila sudah termuat."""
        conf = self.settings()
        cid, model = conf.get("connection_id"), conf.get("model")
        if not cid or not model:
            return
        try:
            row, prov = self.provider(cid)
            if prov.supports_load:
                if await prov.model_status(model) == "loaded":
                    self.state.update(status="ready", connection_id=cid, model=model, loaded_by_us=False,
                                      last_activity=time.time(), message="")
            else:
                self.state.update(status="ready", connection_id=cid, model=model, loaded_by_us=False,
                                  last_activity=time.time(), message="")
        except Exception as e:
            log.info("Model AI belum dipulihkan: %s", e)

    # ---------- percakapan ----------
    def conversations(self, user: dict) -> list[dict]:
        return self.db.all("SELECT c.*, (SELECT COUNT(*) FROM ai_messages m WHERE m.conversation_id=c.id) AS messages "
                           "FROM ai_conversations c WHERE user_id=? ORDER BY updated_at DESC LIMIT 200", (user["id"],))

    def conversation(self, user: dict, conv_id: int) -> dict:
        c = self.db.one("SELECT * FROM ai_conversations WHERE id=? AND user_id=?", (conv_id, user["id"]))
        if not c:
            raise NotFound("Percakapan tidak ditemukan")
        c["messages"] = self.db.all("SELECT id, role, content, reasoning, model, created_at FROM ai_messages "
                                    "WHERE conversation_id=? ORDER BY id", (conv_id,))
        return c

    def create_conversation(self, user: dict, title: str = "Percakapan baru") -> dict:
        now = time.time()
        cur = self.db.execute("INSERT INTO ai_conversations(user_id, title, created_at, updated_at) VALUES(?,?,?,?)",
                              (user["id"], title[:120], now, now))
        return self.conversation(user, cur.lastrowid)

    def rename_conversation(self, user: dict, conv_id: int, title: str) -> dict:
        self.conversation(user, conv_id)
        self.db.execute("UPDATE ai_conversations SET title=? WHERE id=?", (title.strip()[:120] or "Percakapan", conv_id))
        return self.conversation(user, conv_id)

    def delete_conversation(self, user: dict, conv_id: int) -> None:
        self.conversation(user, conv_id)
        with self.db.tx() as c:
            c.execute("DELETE FROM ai_messages WHERE conversation_id=?", (conv_id,))
            c.execute("DELETE FROM ai_conversations WHERE id=?", (conv_id,))

    def _add_message(self, conv_id: int, role: str, content: str, reasoning: str = "", model: str = "") -> int:
        cur = self.db.execute("INSERT INTO ai_messages(conversation_id, role, content, reasoning, model, created_at) "
                              "VALUES(?,?,?,?,?,?)", (conv_id, role, content, reasoning, model, time.time()))
        self.db.execute("UPDATE ai_conversations SET updated_at=? WHERE id=?", (time.time(), conv_id))
        return cur.lastrowid

    # ---------- chat ----------
    def _ready_provider(self) -> tuple[dict, Provider, str]:
        st = self.state
        if st["status"] == "loading":
            raise AppError(f"Model masih dimuat: {st['message']}", code="ai_loading", status_code=503)
        if st["status"] != "ready" or not st["model"]:
            raise AppError("Belum ada model AI yang diterapkan. Buka menu Model AI, pilih model, lalu Terapkan.",
                           code="ai_not_configured", status_code=503)
        row, prov = self.provider(st["connection_id"])
        return row, prov, st["model"]

    def _context_block(self, project_dir: Path | None, files: list[str] | None, editor_text: str | None,
                       editor_name: str | None) -> str:
        parts = []
        if project_dir is not None:
            listing = self._project_listing(project_dir)
            if listing:
                parts.append("### Struktur proyek (path relatif)\n" + listing)
        if project_dir is not None and files:
            for rel in files[:10]:
                try:
                    f = self.files.read(project_dir, rel)
                except AppError:
                    continue
                if not f.get("binary"):
                    parts.append(f"### File: {f['path']}\n```{f.get('language', '')}\n{f['content'][:20000]}\n```")
        if editor_text:
            parts.append(f"### File di editor: {editor_name or 'tanpa nama'}\n```\n{editor_text[:30000]}\n```")
        return "\n\n".join(parts)

    def _project_listing(self, root: Path, limit: int = 300) -> str:
        skip = {".git", "node_modules", "__pycache__", ".venv", "venv", "build", "dist", ".gradle", "target", "bin", "obj"}
        out: list[str] = []
        for p in sorted(root.rglob("*")):
            rel = p.relative_to(root)
            if any(part in skip or part.startswith(".cs_") for part in rel.parts) or p.is_dir() or p.is_symlink():
                continue
            out.append(str(rel))
            if len(out) >= limit:
                out.append("…")
                break
        return "\n".join(out)

    def build_messages(self, conv_id: int | None, content: str, context: str, edit_mode: bool = False) -> list[dict]:
        conf = self.settings()
        msgs: list[dict] = []
        system = conf.get("system_prompt") or ""
        if edit_mode:
            system = (system + "\n\n" + EDIT_PROTOCOL).strip()
        if system:
            msgs.append({"role": "system", "content": system})
        history: list[dict] = []
        if conv_id:
            n = int(conf.get("history_messages") or 20)
            rows = self.db.all("SELECT role, content FROM ai_messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?",
                               (conv_id, n))
            history = [{"role": r["role"], "content": r["content"]} for r in reversed(rows) if r["role"] in ("user", "assistant")]
        user_msg = content if not context else f"{context}\n\n---\n\n{content}"
        total = sum(len(m["content"]) for m in history) + len(user_msg)
        while history and total > MAX_CONTEXT_CHARS:  # buang pesan terlama bila konteks terlalu panjang
            total -= len(history.pop(0)["content"])
        return msgs + history + [{"role": "user", "content": user_msg}]

    async def chat_stream(self, user: dict, conv_id: int | None, content: str, *, project_dir: Path | None = None,
                          files: list[str] | None = None, editor_text: str | None = None,
                          editor_name: str | None = None, project_id: str | None = None,
                          auto_apply: bool = False) -> AsyncIterator[dict]:
        """Hasil: {type: conversation|start|reasoning|delta|edits|done|error}. Pesan & jawaban disimpan.

        Bila ada proyek dan AI punya hak tulis, jawaban yang berisi blok file= diubah menjadi proposal
        (event 'edits'); dengan auto_apply proposal langsung diterapkan (tetap tercatat & bisa dibatalkan)."""
        if "read" not in intersect_for_ai(user["perms"]):
            raise Forbidden("AI tidak punya hak baca untuk pengguna ini")
        content = (content or "").strip()
        if not content:
            raise AppError("Pesan kosong", code="empty_message")
        row, prov, model = self._ready_provider()
        if conv_id:
            self.conversation(user, conv_id)
        else:
            conv_id = self.create_conversation(user, content.splitlines()[0][:60])["id"]
            yield {"type": "conversation", "id": conv_id}
        edit_mode = project_dir is not None and project_id is not None and "write" in intersect_for_ai(user["perms"])
        context = self._context_block(project_dir, files, editor_text, editor_name)
        messages = self.build_messages(conv_id, content, context, edit_mode=edit_mode)
        self._add_message(conv_id, "user", content)
        self.db.execute("UPDATE ai_conversations SET connection_id=?, model=? WHERE id=?", (row["id"], model, conv_id))
        conf = self.settings()
        yield {"type": "start", "model": model, "connection": row["name"], "conversation_id": conv_id}
        answer, reasoning = [], []
        started = time.time()
        self.state["last_activity"] = time.time()
        try:
            async for kind, text in prov.stream_chat(model, messages, conf.get("temperature"), conf.get("max_tokens")):
                (answer if kind == "delta" else reasoning).append(text)
                self.state["last_activity"] = time.time()
                yield {"type": kind, "text": text}
        except asyncio.CancelledError:
            if answer:
                self._add_message(conv_id, "assistant", "".join(answer) + "\n\n[dihentikan]", "".join(reasoning), model)
            raise
        except AppError as e:
            yield {"type": "error", "code": e.code, "message": e.message}
            return
        text = "".join(answer)
        if not text and reasoning:
            text = "(Model hanya mengirim proses berpikir tanpa jawaban akhir — coba naikkan max_tokens.)"
        mid = self._add_message(conv_id, "assistant", text, "".join(reasoning), model)
        self.state["last_activity"] = time.time()
        if edit_mode:
            items = self.proposals_from_answer(user, project_id, project_dir, text, conv_id, mid, auto_apply=auto_apply)
            if items:
                yield {"type": "edits", "message_id": mid, "items": items}
        yield {"type": "done", "message_id": mid, "conversation_id": conv_id, "model": model,
               "seconds": round(time.time() - started, 2)}

    async def chat(self, user: dict, messages: list[dict], project_dir: Path | None = None, files: list[str] | None = None,
                   **opts) -> dict:
        """Chat non-streaming (tanpa riwayat) untuk klien sederhana/otomasi."""
        row, prov, model = self._ready_provider()
        if "read" not in intersect_for_ai(user["perms"]):
            raise Forbidden("AI tidak punya hak baca")
        context = self._context_block(project_dir, files, None, None)
        msgs = list(messages)
        conf = self.settings()
        if conf.get("system_prompt"):
            msgs.insert(0, {"role": "system", "content": conf["system_prompt"]})
        if context:
            msgs.insert(1 if conf.get("system_prompt") else 0, {"role": "system", "content": "Konteks file proyek:\n\n" + context})
        out, reasoning = [], []
        async for kind, text in prov.stream_chat(model, msgs, opts.get("temperature", conf.get("temperature")),
                                                 opts.get("max_tokens") or conf.get("max_tokens")):
            (out if kind == "delta" else reasoning).append(text)
        self.state["last_activity"] = time.time()
        return {"content": "".join(out), "reasoning": "".join(reasoning), "model": model}

    # ---------- proposal perubahan (agent) ----------
    @staticmethod
    def public_proposal(row: dict) -> dict:
        """Tanpa isi file penuh (bisa besar); klien cukup melihat diff."""
        return {k: row.get(k) for k in ("id", "project_id", "path", "action", "reason", "status", "created_at",
                                        "decided_at", "conversation_id", "message_id", "diff", "additions",
                                        "deletions", "error", "risk", "task_id")} | {
            "new_file": not row.get("existed", 1),
            "risk_reasons": [r for r in (row.get("risk_reasons") or "").split("; ") if r]}

    def _insert_proposal(self, **f) -> dict:
        f.setdefault("created_at", time.time())
        cols = ", ".join(f)
        cur = self.db.execute(f"INSERT INTO ai_proposals({cols}) VALUES({', '.join('?' * len(f))})", tuple(f.values()))
        return self.db.one("SELECT * FROM ai_proposals WHERE id=?", (cur.lastrowid,))

    def _current(self, root: Path, path: str) -> tuple[bool, str, str | None]:
        """(ada?, isi, sha256) file saat ini."""
        p = self.files.resolve(root, path, allow_root=False)
        if not p.exists():
            return False, "", None
        f = self.files.read(root, path)
        if f.get("binary"):
            raise AppError("File biner tidak bisa diubah AI", code="binary_file")
        return True, f["content"], f["sha256"]

    def propose_edit(self, user: dict, project_id: str, root: Path, edit: Edit, conv_id: int | None = None,
                     message_id: int | None = None, reason: str = "", task_id: str | None = None) -> dict:
        """Hitung isi baru dari editan AI -> proposal 'pending' (atau 'failed' + alasan bila tak bisa diterapkan)."""
        base = {"project_id": project_id, "user_id": user["id"], "action": "write", "reason": reason[:500],
                "conversation_id": conv_id, "message_id": message_id, "task_id": task_id}
        try:
            path = FileService.normalize(edit.path)
            existed, old, sha = self._current(root, path)
            if edit.kind == "replace":
                if not existed and any(s.strip() for s, _ in edit.blocks):
                    raise EditError("File belum ada, padahal blok SEARCH merujuk isi lama")
                new = apply_replace(old, edit.blocks)
            else:
                new = edit.content
                if existed and looks_truncated(new) and len(new) < len(old) * 0.8:
                    raise EditError("Isi file dari AI tampak disingkat (\"... kode lain tetap sama\"). "
                                    "Minta AI menulis isi lengkap atau memakai blok SEARCH/REPLACE.")
            if existed and new == old:
                raise EditError("Tidak ada perubahan terhadap isi file saat ini")
            diff, adds, dels = unified_diff(path, old, new)
            risk, why = classify_change(path, "write", old if existed else None, new)
            return self._insert_proposal(**base, path=path, content=new, status="pending", base_sha256=sha,
                                         old_content=old if existed else None, existed=1 if existed else 0,
                                         diff=diff, additions=adds, deletions=dels, risk=risk,
                                         risk_reasons="; ".join(why))
        except (EditError, AppError) as e:
            msg = e.message if isinstance(e, AppError) else str(e)
            return self._insert_proposal(**base, path=edit.path[:500], content=None, status="failed", error=msg)

    def proposals_from_answer(self, user: dict, project_id: str, root: Path, answer: str, conv_id: int | None,
                              message_id: int | None, auto_apply: bool = False) -> list[dict]:
        edits = parse_edits(answer)
        # gabungkan beberapa editan ke file yang sama menjadi satu proposal (berurutan)
        merged: dict[str, Edit] = {}
        for e in edits:
            prev = merged.get(e.path)
            if prev is None:
                merged[e.path] = e
            elif e.kind == "full":
                merged[e.path] = e
            elif prev.kind == "replace":
                prev.blocks.extend(e.blocks)
            else:  # full lalu replace: terapkan replace ke isi full
                try:
                    prev.content = apply_replace(prev.content, e.blocks)
                except EditError:
                    pass
        items = []
        for e in merged.values():
            row = self.propose_edit(user, project_id, root, e, conv_id, message_id, reason="dari jawaban AI")
            if auto_apply and row["status"] == "pending" and row.get("risk") == HIGH:
                # Risiko tinggi tidak pernah diterapkan otomatis; tetap menunggu persetujuan eksplisit.
                pass
            elif auto_apply and row["status"] == "pending":
                try:
                    self.decide(user, project_id, root, row["id"], True)
                except AppError as err:
                    self.db.execute("UPDATE ai_proposals SET status='failed', error=? WHERE id=?", (err.message, row["id"]))
                row = self.db.one("SELECT * FROM ai_proposals WHERE id=?", (row["id"],))
            items.append(self.public_proposal(row))
        if items:
            self.db.audit("ai_edits", user=user, target=project_id,
                          detail={"message_id": message_id, "files": [i["path"] for i in items],
                                  "status": [i["status"] for i in items]})
        return items

    def propose(self, user: dict, project_id: str, path: str, action: str, content: str | None, reason: str,
                root: Path | None = None, task_id: str | None = None) -> dict:
        perms = intersect_for_ai(user["perms"])
        if action not in ("write", "delete"):
            raise AppError("Aksi harus write/delete", code="bad_action")
        if action == "write" and "write" not in perms:
            raise Forbidden("AI tidak punya hak tulis")
        if action == "delete" and "delete" not in perms:
            raise Forbidden("AI tidak punya hak hapus")
        path = FileService.normalize(path)
        if action == "write" and root is not None:
            row = self.propose_edit(user, project_id, root, Edit(path, "full", content=content or ""), reason=reason,
                                    task_id=task_id)
            if row["status"] == "failed":
                raise AppError(row["error"], code="bad_edit")
            return row
        existed, old, sha = self._current(root, path) if root is not None else (True, None, None)
        risk, why = classify_change(path, action, old, content)
        return self._insert_proposal(project_id=project_id, user_id=user["id"], path=path, action=action,
                                     content=content, reason=reason, status="pending", base_sha256=sha,
                                     old_content=old, existed=1 if existed else 0, risk=risk,
                                     risk_reasons="; ".join(why), task_id=task_id)

    def proposals(self, project_id: str, status: str | None = None, conversation_id: int | None = None,
                  task_id: str | None = None) -> list[dict]:
        sql, args = "SELECT * FROM ai_proposals WHERE project_id=?", [project_id]
        if task_id:
            sql += " AND task_id=?"; args.append(task_id)
        if status:
            sql += " AND status=?"; args.append(status)
        if conversation_id is not None:
            sql += " AND conversation_id=?"; args.append(conversation_id)
        return [self.public_proposal(r) for r in self.db.all(sql + " ORDER BY id DESC LIMIT 200", tuple(args))]

    def _proposal(self, project_id: str, proposal_id: int) -> dict:
        row = self.db.one("SELECT * FROM ai_proposals WHERE id=? AND project_id=?", (proposal_id, project_id))
        if not row:
            raise NotFound("Proposal tidak ditemukan")
        return row

    def decide(self, user: dict, project_id: str, project_dir: Path, proposal_id: int, approve: bool,
               confirm_high_risk: bool = False) -> dict:
        row = self._proposal(project_id, proposal_id)
        if row["status"] != "pending":
            raise Conflict(f"Proposal sudah {row['status']}")
        if approve and row.get("risk") == HIGH and not confirm_high_risk:
            raise Conflict("Perubahan berisiko TINGGI (" + (row.get("risk_reasons") or "-") + "). "
                           "Periksa diff lalu setujui dengan confirm_high_risk=true.",
                           code="high_risk_confirmation_required")
        result = None
        if approve:
            note = f"AI #{proposal_id}: {(row['reason'] or '')[:100]}"
            if row["action"] == "write":
                if "write" not in user["perms"]:
                    raise Forbidden("Tidak punya hak tulis")
                existed = bool(row.get("existed", 1))
                try:
                    result = self.files.write(project_id, project_dir, row["path"], row["content"] or "", actor=user,
                                              actor_type="ai", note=note, expected_sha256=row.get("base_sha256"),
                                              create_only=not existed)
                except Conflict as e:
                    raise Conflict("File sudah berubah sejak AI membuat usulan ini. Minta AI mengulang dengan isi terbaru.",
                                   code="proposal_stale") from e
                self.db.execute("UPDATE ai_proposals SET new_sha256=? WHERE id=?", (result["sha256"], proposal_id))
            else:
                if "delete" not in user["perms"]:
                    raise Forbidden("Tidak punya hak hapus")
                self.files.delete(project_id, project_dir, row["path"], actor=user, actor_type="ai")
        status = "approved" if approve else "rejected"
        self.db.execute("UPDATE ai_proposals SET status=?, decided_at=? WHERE id=?", (status, time.time(), proposal_id))
        return {"id": proposal_id, "status": status, "result": result,
                "proposal": self.public_proposal(self._proposal(project_id, proposal_id))}

    def revert(self, user: dict, project_id: str, project_dir: Path, proposal_id: int) -> dict:
        """Batalkan editan AI yang sudah diterapkan: kembalikan isi lama (atau hapus file baru)."""
        row = self._proposal(project_id, proposal_id)
        if row["status"] != "approved" or row["action"] != "write":
            raise Conflict("Hanya editan AI yang sudah diterapkan yang bisa dibatalkan")
        if "write" not in user["perms"]:
            raise Forbidden("Tidak punya hak tulis")
        p = self.files.resolve(project_dir, row["path"], allow_root=False)
        current = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
        if row.get("new_sha256") and current != row["new_sha256"]:
            raise Conflict("File sudah diubah lagi setelah editan AI; pulihkan lewat Riwayat file.", code="revert_conflict")
        result = None
        if row.get("existed", 1):
            result = self.files.write(project_id, project_dir, row["path"], row.get("old_content") or "", actor=user,
                                      actor_type="user", note=f"batalkan AI #{proposal_id}")
        elif p.is_file():
            if "delete" not in user["perms"]:
                raise Forbidden("Tidak punya hak hapus")
            self.files.delete(project_id, project_dir, row["path"], actor=user, actor_type="user")
        self.db.execute("UPDATE ai_proposals SET status='reverted', decided_at=? WHERE id=?", (time.time(), proposal_id))
        return {"id": proposal_id, "status": "reverted", "result": result,
                "proposal": self.public_proposal(self._proposal(project_id, proposal_id))}
