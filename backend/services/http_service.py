"""HTTP Client / API tester dengan perlindungan SSRF.

Secara default tujuan ke loopback, link-local (169.254.x, metadata cloud), multicast, dan
alamat reserved DITOLAK. Jaringan privat (192.168.x, 10.x) juga ditolak kecuali
``CS_HTTP_ALLOW_PRIVATE=true``. Redirect diikuti manual dan setiap lompatan diperiksa ulang.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
import time
from urllib.parse import urljoin, urlparse

import httpx

from backend.config import Settings
from backend.core.exceptions import AppError, Forbidden, NotFound
from backend.database.db import Database

METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
MAX_BODY = 2_000_000


def classify(ip: str) -> str:
    a = ipaddress.ip_address(ip)
    if a.is_loopback:
        return "loopback"
    if a.is_link_local:
        return "link_local"
    if a.is_multicast or a.is_reserved or a.is_unspecified:
        return "reserved"
    if a.is_private:
        return "private"
    return "public"


async def check_destination(url: str, allow_private: bool) -> None:
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise AppError("URL harus http:// atau https://", code="bad_url")
    port = u.port or (443 if u.scheme == "https" else 80)
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(u.hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise AppError(f"Host tidak ditemukan: {u.hostname}", code="dns_error")
    for info in infos:
        kind = classify(info[4][0])
        if kind in ("loopback", "link_local", "reserved"):
            raise Forbidden(f"Tujuan {info[4][0]} ({kind}) diblokir untuk mencegah SSRF", code="ssrf_blocked")
        if kind == "private" and not allow_private:
            raise Forbidden(
                f"Tujuan jaringan privat {info[4][0]} diblokir. Aktifkan CS_HTTP_ALLOW_PRIVATE bila diperlukan.",
                code="ssrf_blocked",
            )


class HttpService:
    def __init__(self, settings: Settings, db: Database):
        self.s = settings
        self.db = db

    async def send(self, method: str, url: str, headers: dict | None = None, params: dict | None = None,
                   body: str | None = None, body_type: str = "none", form: dict | None = None,
                   timeout: float | None = None, follow_redirects: bool = True) -> dict:
        method = method.upper()
        if method not in METHODS:
            raise AppError("Method tidak didukung", code="bad_method")
        headers = {str(k): str(v) for k, v in (headers or {}).items()}
        kwargs: dict = {"headers": headers, "params": params or None}
        if body_type == "json":
            try:
                kwargs["json"] = json.loads(body or "null")
            except json.JSONDecodeError as e:
                raise AppError(f"Body JSON tidak valid: {e}", code="bad_json")
        elif body_type == "form":
            kwargs["data"] = form or {}
        elif body_type == "raw" and body is not None:
            kwargs["content"] = body.encode()
        start = time.monotonic()
        redirects = []
        async with httpx.AsyncClient(timeout=timeout or self.s.http_timeout, follow_redirects=False, trust_env=False) as c:
            current = url
            for _ in range(6):
                await check_destination(current, self.s.http_allow_private)
                try:
                    req = c.build_request(method, current, **kwargs)
                    resp = await c.send(req, stream=True)
                except httpx.HTTPError as e:
                    raise AppError(f"Request gagal: {e}", code="http_error")
                try:
                    if follow_redirects and resp.is_redirect and "location" in resp.headers:
                        redirects.append({"status": resp.status_code, "location": resp.headers["location"]})
                        current = urljoin(current, resp.headers["location"])
                        if resp.status_code in (301, 302, 303):
                            method = "GET" if method != "HEAD" else "HEAD"
                            kwargs = {"headers": headers}
                        continue
                    raw = b""
                    truncated = False
                    async for chunk in resp.aiter_bytes():
                        raw += chunk
                        if len(raw) > MAX_BODY:
                            raw = raw[:MAX_BODY]
                            truncated = True
                            break
                finally:
                    await resp.aclose()
                text = raw.decode(resp.encoding or "utf-8", errors="replace")
                return {
                    "status_code": resp.status_code,
                    "reason": resp.reason_phrase,
                    "http_version": resp.http_version,
                    "url": str(resp.url),
                    "headers": dict(resp.headers),
                    "body": text,
                    "size": len(raw),
                    "truncated": truncated,
                    "time_ms": round((time.monotonic() - start) * 1000, 1),
                    "redirects": redirects,
                }
        raise AppError("Terlalu banyak redirect", code="too_many_redirects")

    # ---------- koleksi ----------
    def collections(self, user: dict) -> dict:
        rows = self.db.all("SELECT * FROM http_requests WHERE user_id=? ORDER BY collection, name", (user["id"],))
        out: dict[str, list] = {}
        for r in rows:
            r["headers"] = json.loads(r["headers"])
            r["params"] = json.loads(r["params"])
            out.setdefault(r["collection"], []).append(r)
        return {"collections": [{"name": k, "requests": v} for k, v in out.items()]}

    def save(self, user: dict, data: dict) -> dict:
        cur = self.db.execute(
            "INSERT INTO http_requests(user_id, collection, name, method, url, headers, params, body, body_type, created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (user["id"], data.get("collection") or "default", data["name"], data["method"].upper(), data["url"],
             json.dumps(data.get("headers") or {}), json.dumps(data.get("params") or {}), data.get("body"),
             data.get("body_type") or "none", time.time()),
        )
        row = self.db.one("SELECT * FROM http_requests WHERE id=?", (cur.lastrowid,))
        row["headers"] = json.loads(row["headers"])
        row["params"] = json.loads(row["params"])
        return row

    def delete(self, user: dict, request_id: int) -> None:
        row = self.db.one("SELECT id FROM http_requests WHERE id=? AND user_id=?", (request_id, user["id"]))
        if not row:
            raise NotFound("Request tersimpan tidak ditemukan")
        self.db.execute("DELETE FROM http_requests WHERE id=?", (request_id,))
