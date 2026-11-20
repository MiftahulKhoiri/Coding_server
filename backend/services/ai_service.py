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


class AIService:
    def __init__(self, settings: Settings, db: Database, files: FileService):
        self.s = settings
        self.db = db
        self.files = files
        self.secrets = SecretStore(settings.secret_key)
        self._lock = asyncio.Lock()
        self.state: dict = {"status": "idle", "connection_id": None, "model": None, "message": "",
                            "loaded_by_us": False, "last_activity": 0.0, "target": None}
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
                if ours and old_model and (old_cid, old_model) != (cid, model):
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
                self.state.update(status="ready", connection_id=cid, model=model, message="", target=None,
                                  loaded_by_us=loaded_by_us, last_activity=time.time())
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
                        and time.time() - st["last_activity"] > minutes * 60):
                    log.info("Model %s idle %d menit, dibongkar otomatis", st["model"], minutes)
                    await self.unload()
                    self.state["message"] = f"Dibongkar otomatis setelah idle {minutes} menit"
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

    def build_messages(self, conv_id: int | None, content: str, context: str) -> list[dict]:
        conf = self.settings()
        msgs: list[dict] = []
        if conf.get("system_prompt"):
            msgs.append({"role": "system", "content": conf["system_prompt"]})
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
                          editor_name: str | None = None) -> AsyncIterator[dict]:
        """Hasil: {type: conversation|start|reasoning|delta|done|error}. Pesan & jawaban disimpan."""
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
        context = self._context_block(project_dir, files, editor_text, editor_name)
        messages = self.build_messages(conv_id, content, context)
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
    def propose(self, user: dict, project_id: str, path: str, action: str, content: str | None, reason: str) -> dict:
        perms = intersect_for_ai(user["perms"])
        if action not in ("write", "delete"):
            raise AppError("Aksi harus write/delete", code="bad_action")
        if action == "write" and "write" not in perms:
            raise Forbidden("AI tidak punya hak tulis")
        path = FileService.normalize(path)
        cur = self.db.execute(
            "INSERT INTO ai_proposals(project_id, user_id, path, action, content, reason, status, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (project_id, user["id"], path, action, content, reason, "pending", time.time()),
        )
        return self.db.one("SELECT * FROM ai_proposals WHERE id=?", (cur.lastrowid,))

    def proposals(self, project_id: str, status: str | None = None) -> list[dict]:
        if status:
            return self.db.all("SELECT * FROM ai_proposals WHERE project_id=? AND status=? ORDER BY id DESC", (project_id, status))
        return self.db.all("SELECT * FROM ai_proposals WHERE project_id=? ORDER BY id DESC LIMIT 200", (project_id,))

    def decide(self, user: dict, project_id: str, project_dir: Path, proposal_id: int, approve: bool) -> dict:
        row = self.db.one("SELECT * FROM ai_proposals WHERE id=? AND project_id=?", (proposal_id, project_id))
        if not row:
            raise NotFound("Proposal tidak ditemukan")
        if row["status"] != "pending":
            raise Conflict("Proposal sudah diputuskan")
        result = None
        if approve:
            if row["action"] == "write":
                if "write" not in user["perms"]:
                    raise Forbidden("Tidak punya hak tulis")
                result = self.files.write(project_id, project_dir, row["path"], row["content"] or "", actor=user,
                                          actor_type="ai", note=f"proposal AI #{proposal_id}: {row['reason'][:100]}")
            else:
                if "delete" not in user["perms"]:
                    raise Forbidden("Tidak punya hak hapus")
                self.files.delete(project_id, project_dir, row["path"], actor=user, actor_type="ai")
        self.db.execute("UPDATE ai_proposals SET status=?, decided_at=? WHERE id=?",
                        ("approved" if approve else "rejected", time.time(), proposal_id))
        return {"id": proposal_id, "status": "approved" if approve else "rejected", "result": result}
