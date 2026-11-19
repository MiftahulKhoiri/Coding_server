"""Fondasi integrasi AI Coding Agent.

* Provider dapat diganti (interface AIProvider). Bawaan: OpenAI-compatible
  (llama-server/llama.cpp lokal, Ollama, atau API eksternal). Model TIDAK dipasang otomatis.
* Hak AI = irisan hak pengguna dan peran 'ai' (tidak pernah melebihi pengguna).
* Perubahan kode oleh AI dibuat sebagai *proposal*; diterapkan hanya setelah disetujui,
  dicatat di riwayat file (actor_type='ai') sehingga bisa diperiksa & dibatalkan.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from pathlib import Path

import httpx

from backend.config import Settings
from backend.core.exceptions import AppError, Conflict, Forbidden, NotFound
from backend.core.permissions import intersect_for_ai
from backend.database.db import Database
from backend.services.file_service import FileService


class AIProvider(ABC):
    name = "base"

    @abstractmethod
    async def chat(self, messages: list[dict], **opts) -> dict: ...

    @abstractmethod
    async def status(self) -> dict: ...


class OpenAICompatibleProvider(AIProvider):
    name = "openai-compatible"

    def __init__(self, base_url: str, model: str, api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    async def status(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=5, trust_env=False) as c:
                r = await c.get(f"{self.base_url}/v1/models", headers=self._headers())
            models = [m.get("id") for m in r.json().get("data", [])] if r.is_success else []
            return {"reachable": r.is_success, "models": models}
        except Exception as e:
            return {"reachable": False, "error": str(e)}

    async def chat(self, messages: list[dict], **opts) -> dict:
        payload = {"model": self.model or "default", "messages": messages, "stream": False}
        for k in ("temperature", "max_tokens"):
            if opts.get(k) is not None:
                payload[k] = opts[k]
        try:
            async with httpx.AsyncClient(timeout=300, trust_env=False) as c:
                r = await c.post(f"{self.base_url}/v1/chat/completions", json=payload, headers=self._headers())
        except httpx.HTTPError as e:
            raise AppError(f"Provider AI tidak bisa dihubungi: {e}", code="ai_unreachable", status_code=502)
        if not r.is_success:
            raise AppError(f"Provider AI menjawab {r.status_code}: {r.text[:300]}", code="ai_error", status_code=502)
        data = r.json()
        msg = data.get("choices", [{}])[0].get("message", {})
        return {"content": msg.get("content", ""), "model": data.get("model"), "usage": data.get("usage")}


class AIService:
    def __init__(self, settings: Settings, db: Database, files: FileService):
        self.s = settings
        self.db = db
        self.files = files

    def provider(self) -> AIProvider | None:
        if not self.s.ai_base_url:
            return None
        return OpenAICompatibleProvider(self.s.ai_base_url, self.s.ai_model, self.s.ai_api_key)

    async def status(self, user: dict) -> dict:
        p = self.provider()
        return {
            "configured": p is not None,
            "provider": p.name if p else None,
            "base_url": self.s.ai_base_url or None,
            "model": self.s.ai_model or None,
            "ai_permissions": sorted(intersect_for_ai(user["perms"])),
            **(await p.status() if p else {}),
        }

    async def chat(self, user: dict, messages: list[dict], project_dir: Path | None = None, files: list[str] | None = None,
                   **opts) -> dict:
        p = self.provider()
        if not p:
            raise AppError("AI provider belum dikonfigurasi (CS_AI_BASE_URL)", code="ai_not_configured", status_code=503)
        if "read" not in intersect_for_ai(user["perms"]):
            raise Forbidden("AI tidak punya hak baca")
        context = []
        if project_dir is not None and files:
            for rel in files[:10]:
                f = self.files.read(project_dir, rel)
                if not f.get("binary"):
                    context.append(f"### File: {rel}\n```\n{f['content'][:20000]}\n```")
        msgs = list(messages)
        if context:
            msgs.insert(0, {"role": "system", "content": "Konteks file proyek:\n\n" + "\n\n".join(context)})
        return await p.chat(msgs, **opts)

    # ---------- proposal perubahan ----------
    def propose(self, user: dict, project_id: str, path: str, action: str, content: str | None, reason: str) -> dict:
        perms = intersect_for_ai(user["perms"])
        need = "write" if action == "write" else "delete"
        if action not in ("write", "delete"):
            raise AppError("Aksi harus write/delete", code="bad_action")
        if action == "write" and "write" not in perms:
            raise Forbidden("AI tidak punya hak tulis")
        _ = need
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
            # Persetujuan dilakukan pengguna; hak dicek terhadap pengguna yang menyetujui.
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
