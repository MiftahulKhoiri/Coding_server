"""Penyedia model AI: lokal (llama-server mode router, Ollama/llama-server biasa) dan online
(OpenAI-compatible: OpenAI, OpenRouter, Groq, DeepSeek, custom; Anthropic; Google Gemini).

Semua penyedia punya antarmuka sama:
  list_models()            -> [{id, status?, context_length?}]
  stream_chat(messages, …) -> async iterator ("delta"|"reasoning", teks)
  load(model) / unload(model) / model_status(model)  (hanya bermakna untuk llama-server router)
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

import httpx

from backend.core.exceptions import AppError

KINDS = ("llama_router", "openai", "anthropic", "gemini")

# Templat koneksi yang ditawarkan di halaman "Model AI".
PRESETS = [
    {"key": "llama_local", "name": "llama-server lokal (Pi)", "kind": "llama_router", "location": "local",
     "base_url": "http://127.0.0.1:8080", "needs_key": False,
     "note": "llama-server mode router (--models-dir). Model dimuat saat diterapkan & dibongkar saat idle."},
    {"key": "ollama_local", "name": "Ollama lokal", "kind": "openai", "location": "local",
     "base_url": "http://127.0.0.1:11434", "needs_key": False, "note": "Ollama (API kompatibel OpenAI)."},
    {"key": "openai_local", "name": "Server lokal lain (OpenAI-compatible)", "kind": "openai", "location": "local",
     "base_url": "http://192.168.1.10:8080", "needs_key": False, "note": "llama-server/LM Studio/vLLM di PC lain."},
    {"key": "openai", "name": "OpenAI", "kind": "openai", "location": "online", "base_url": "https://api.openai.com",
     "needs_key": True, "note": ""},
    {"key": "openrouter", "name": "OpenRouter", "kind": "openai", "location": "online", "base_url": "https://openrouter.ai/api",
     "needs_key": True, "note": "Banyak model (ada yang gratis)."},
    {"key": "groq", "name": "Groq", "kind": "openai", "location": "online", "base_url": "https://api.groq.com/openai",
     "needs_key": True, "note": ""},
    {"key": "deepseek", "name": "DeepSeek", "kind": "openai", "location": "online", "base_url": "https://api.deepseek.com",
     "needs_key": True, "note": ""},
    {"key": "anthropic", "name": "Anthropic (Claude)", "kind": "anthropic", "location": "online",
     "base_url": "https://api.anthropic.com", "needs_key": True, "note": ""},
    {"key": "gemini", "name": "Google Gemini", "kind": "gemini", "location": "online",
     "base_url": "https://generativelanguage.googleapis.com", "needs_key": True, "note": ""},
    {"key": "custom", "name": "Custom (OpenAI-compatible)", "kind": "openai", "location": "online",
     "base_url": "https://", "needs_key": True, "note": "Isi URL dasar tanpa /v1."},
]


def normalize_base(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    for suffix in ("/v1/chat/completions", "/v1beta", "/v1"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    if not url.startswith(("http://", "https://")):
        raise AppError("URL harus diawali http:// atau https://", code="bad_url")
    return url


def http_client(timeout: float = 30.0) -> httpx.AsyncClient:
    """Dipisah agar bisa diganti transport tiruan saat pengujian."""
    return httpx.AsyncClient(timeout=httpx.Timeout(timeout, read=300.0), trust_env=False)


def _err(resp: httpx.Response, body: str) -> AppError:
    msg = body[:400]
    try:
        j = json.loads(body)
        e = j.get("error", j)
        msg = e.get("message", msg) if isinstance(e, dict) else str(e)
    except Exception:
        pass
    code = "ai_auth" if resp.status_code in (401, 403) else "ai_error"
    return AppError(f"Penyedia AI menjawab {resp.status_code}: {msg}", code=code, status_code=502)


async def _sse_lines(resp: httpx.Response) -> AsyncIterator[str]:
    async for line in resp.aiter_lines():
        line = line.strip()
        if line.startswith("data:"):
            yield line[5:].strip()


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


class Provider:
    def __init__(self, base_url: str, api_key: str = ""):
        self.base = normalize_base(base_url)
        self.key = api_key
        # Statistik panggilan stream_chat terakhir (bila penyedia mengirimnya): prompt_tokens,
        # completion_tokens, gen_tps (token/detik generasi), prompt_tps. Dipakai agent & Uji Model.
        self.last_stats: dict = {}

    supports_load = False

    async def list_models(self) -> list[dict]:
        raise NotImplementedError

    def stream_chat(self, model: str, messages: list[dict], temperature: float | None,
                    max_tokens: int | None) -> AsyncIterator[tuple[str, str]]:
        raise NotImplementedError

    async def load(self, model: str) -> None:
        return None

    async def unload(self, model: str) -> None:
        return None

    async def model_status(self, model: str) -> str | None:
        return "loaded"


class OpenAIProvider(Provider):
    def headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.key:
            h["Authorization"] = f"Bearer {self.key}"
        if "openrouter.ai" in self.base:
            h["X-Title"] = "CODING_SERVER"
        return h

    async def _models_raw(self) -> list[dict]:
        async with http_client(15) as c:
            try:
                r = await c.get(f"{self.base}/v1/models", headers=self.headers())
            except httpx.HTTPError as e:
                raise AppError(f"Tidak bisa menghubungi {self.base}: {e}", code="ai_unreachable", status_code=502)
        if not r.is_success:
            raise _err(r, r.text)
        data = r.json()
        return data.get("data") or data.get("models") or []

    async def list_models(self) -> list[dict]:
        out = []
        for m in await self._models_raw():
            mid = m.get("id") or m.get("name")
            if not mid:
                continue
            st = m.get("status")
            out.append({"id": mid, "status": st.get("value") if isinstance(st, dict) else None,
                        "context_length": m.get("context_length")})
        return sorted(out, key=lambda x: x["id"].lower())

    async def stream_chat(self, model, messages, temperature, max_tokens):
        self.last_stats = {}
        body = {"model": model, "messages": messages, "stream": True}
        if temperature is not None:
            body["temperature"] = temperature
        if max_tokens:
            body["max_tokens"] = max_tokens
        async with http_client() as c:
            try:
                async with c.stream("POST", f"{self.base}/v1/chat/completions", headers=self.headers(), json=body) as r:
                    if not r.is_success:
                        raise _err(r, (await r.aread()).decode(errors="replace"))
                    async for data in _sse_lines(r):
                        if data == "[DONE]":
                            break
                        try:
                            j = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        if j.get("error"):
                            raise AppError(f"Penyedia AI: {j['error']}", code="ai_error", status_code=502)
                        self._collect_stats(j)
                        for ch in j.get("choices") or []:
                            d = ch.get("delta") or {}
                            if d.get("reasoning_content"):
                                yield "reasoning", d["reasoning_content"]
                            elif d.get("reasoning"):
                                yield "reasoning", d["reasoning"]
                            if d.get("content"):
                                yield "delta", d["content"]
            except httpx.HTTPError as e:
                raise AppError(f"Koneksi ke penyedia AI terputus: {e}", code="ai_unreachable", status_code=502)


    def _collect_stats(self, j: dict) -> None:
        t = j.get("timings") if isinstance(j.get("timings"), dict) else {}   # llama-server
        u = j.get("usage") if isinstance(j.get("usage"), dict) else {}       # OpenAI-compatible
        for key, val in (("prompt_tokens", _num(t.get("prompt_n")) or _num(u.get("prompt_tokens"))),
                         ("completion_tokens", _num(t.get("predicted_n")) or _num(u.get("completion_tokens"))),
                         ("gen_tps", _num(t.get("predicted_per_second"))),
                         ("prompt_tps", _num(t.get("prompt_per_second")))):
            if val:
                self.last_stats[key] = val


class LlamaRouterProvider(OpenAIProvider):
    """llama-server mode router: tiap model punya status unloaded/loading/loaded, bisa dimuat/dibongkar."""

    supports_load = True

    async def model_status(self, model: str) -> str | None:
        for m in await self.list_models():
            if m["id"] == model:
                return m["status"] or "loaded"  # server satu-model: tanpa status = selalu siap
        return None

    async def _post(self, path: str, model: str) -> httpx.Response:
        async with http_client(30) as c:
            try:
                return await c.post(f"{self.base}{path}", headers=self.headers(), json={"model": model})
            except httpx.HTTPError as e:
                raise AppError(f"Tidak bisa menghubungi llama-server: {e}", code="ai_unreachable", status_code=502)

    async def load(self, model: str) -> None:
        r = await self._post("/models/load", model)
        if not r.is_success and r.status_code != 400:
            raise _err(r, r.text)

    async def unload(self, model: str, wait: float = 15.0) -> None:
        r = await self._post("/models/unload", model)
        if not r.is_success and r.status_code != 400:  # 400 = memang tidak termuat
            raise _err(r, r.text)
        # Pembongkaran di llama-server bersifat asinkron: tunggu sampai benar-benar lepas dari RAM.
        end = asyncio.get_running_loop().time() + wait
        while asyncio.get_running_loop().time() < end:
            if await self.model_status(model) in ("unloaded", None):
                return
            await asyncio.sleep(0.5)


class AnthropicProvider(Provider):
    def headers(self) -> dict:
        return {"x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"}

    async def list_models(self) -> list[dict]:
        async with http_client(15) as c:
            try:
                r = await c.get(f"{self.base}/v1/models?limit=100", headers=self.headers())
            except httpx.HTTPError as e:
                raise AppError(f"Tidak bisa menghubungi Anthropic: {e}", code="ai_unreachable", status_code=502)
        if not r.is_success:
            raise _err(r, r.text)
        return [{"id": m["id"], "status": None, "context_length": None} for m in r.json().get("data", [])]

    async def stream_chat(self, model, messages, temperature, max_tokens):
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        msgs = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] in ("user", "assistant")]
        body = {"model": model, "messages": msgs, "max_tokens": max_tokens or 4096, "stream": True}
        self.last_stats = {}
        if system:
            body["system"] = system
        if temperature is not None:
            body["temperature"] = temperature
        async with http_client() as c:
            try:
                async with c.stream("POST", f"{self.base}/v1/messages", headers=self.headers(), json=body) as r:
                    if not r.is_success:
                        raise _err(r, (await r.aread()).decode(errors="replace"))
                    async for data in _sse_lines(r):
                        try:
                            j = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        if j.get("type") == "error":
                            raise AppError(f"Anthropic: {j.get('error', {}).get('message')}", code="ai_error", status_code=502)
                        usage = (j.get("message") or {}).get("usage") or j.get("usage") or {}
                        if _num(usage.get("input_tokens")):
                            self.last_stats["prompt_tokens"] = usage["input_tokens"]
                        if _num(usage.get("output_tokens")):
                            self.last_stats["completion_tokens"] = usage["output_tokens"]
                        if j.get("type") == "content_block_delta":
                            d = j.get("delta", {})
                            if d.get("type") == "text_delta":
                                yield "delta", d.get("text", "")
                            elif d.get("type") == "thinking_delta":
                                yield "reasoning", d.get("thinking", "")
            except httpx.HTTPError as e:
                raise AppError(f"Koneksi ke Anthropic terputus: {e}", code="ai_unreachable", status_code=502)


class GeminiProvider(Provider):
    def headers(self) -> dict:
        return {"x-goog-api-key": self.key, "Content-Type": "application/json"}

    async def list_models(self) -> list[dict]:
        async with http_client(15) as c:
            try:
                r = await c.get(f"{self.base}/v1beta/models?pageSize=200", headers=self.headers())
            except httpx.HTTPError as e:
                raise AppError(f"Tidak bisa menghubungi Gemini: {e}", code="ai_unreachable", status_code=502)
        if not r.is_success:
            raise _err(r, r.text)
        out = []
        for m in r.json().get("models", []):
            if "generateContent" in (m.get("supportedGenerationMethods") or []):
                out.append({"id": m["name"].removeprefix("models/"), "status": None,
                            "context_length": m.get("inputTokenLimit")})
        return out

    async def stream_chat(self, model, messages, temperature, max_tokens):
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        contents = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                    for m in messages if m["role"] in ("user", "assistant")]
        body: dict = {"contents": contents, "generationConfig": {}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if temperature is not None:
            body["generationConfig"]["temperature"] = temperature
        if max_tokens:
            body["generationConfig"]["maxOutputTokens"] = max_tokens
        url = f"{self.base}/v1beta/models/{model}:streamGenerateContent?alt=sse"
        self.last_stats = {}
        async with http_client() as c:
            try:
                async with c.stream("POST", url, headers=self.headers(), json=body) as r:
                    if not r.is_success:
                        raise _err(r, (await r.aread()).decode(errors="replace"))
                    async for data in _sse_lines(r):
                        try:
                            j = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        um = j.get("usageMetadata") or {}
                        if _num(um.get("promptTokenCount")):
                            self.last_stats["prompt_tokens"] = um["promptTokenCount"]
                        if _num(um.get("candidatesTokenCount")):
                            self.last_stats["completion_tokens"] = um["candidatesTokenCount"]
                        for cand in j.get("candidates") or []:
                            for part in (cand.get("content") or {}).get("parts") or []:
                                if part.get("text"):
                                    yield ("reasoning" if part.get("thought") else "delta"), part["text"]
            except httpx.HTTPError as e:
                raise AppError(f"Koneksi ke Gemini terputus: {e}", code="ai_unreachable", status_code=502)


def make_provider(kind: str, base_url: str, api_key: str = "") -> Provider:
    cls = {"llama_router": LlamaRouterProvider, "openai": OpenAIProvider, "anthropic": AnthropicProvider,
           "gemini": GeminiProvider}.get(kind)
    if cls is None:
        raise AppError(f"Jenis penyedia tidak dikenal: {kind}", code="bad_kind")
    return cls(base_url, api_key)
