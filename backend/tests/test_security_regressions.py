"""Regresi untuk temuan audit keamanan (lihat docs/SECURITY_REVIEW.md)."""
import os
import tempfile
from pathlib import Path

import pytest

from backend.services.http_service import classify


def _root(client, project):
    return client.app.state.services.projects.project_dir(project)


def test_content_search_does_not_follow_symlink_outside_project(client, auth, project):
    secret_dir = Path(tempfile.mkdtemp(prefix="cs_secret_"))
    (secret_dir / "id_rsa.py").write_text("PRIVATE-KEY-MARKER-XYZ\n")
    root = _root(client, project)
    os.symlink(secret_dir / "id_rsa.py", root / "leak.py")
    os.symlink(secret_dir, root / "leakdir")
    r = client.get("/api/v1/files/search", params={"project_id": project, "q": "PRIVATE-KEY-MARKER", "content": True},
                   headers=auth)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.parametrize("ip,kind", [
    ("127.0.0.1", "loopback"),
    ("::ffff:127.0.0.1", "loopback"),      # IPv4-mapped IPv6
    ("::ffff:169.254.169.254", "link_local"),
    ("::ffff:10.0.0.5", "private"),
    ("100.64.1.1", "private"),             # CGNAT / shared address space
    ("64:ff9b::7f00:1", "loopback"),       # NAT64 ke 127.0.0.1
    ("0.0.0.0", "reserved"),
    ("8.8.8.8", "public"),
])
def test_ssrf_classify(ip, kind):
    assert classify(ip) == kind


def test_http_client_blocks_dns_rebinding(client, auth, monkeypatch):
    """Resolusi pertama (saat validasi) = IP publik, resolusi berikutnya (saat konek) = 127.0.0.1."""
    import asyncio
    import socket

    real = asyncio.base_events.BaseEventLoop.getaddrinfo
    calls = {"n": 0}

    async def fake(self, host, port, *a, **kw):
        if host == "rebind.example":
            calls["n"] += 1
            ip = "93.184.216.34" if calls["n"] == 1 else "127.0.0.1"
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]
        return await real(self, host, port, *a, **kw)

    monkeypatch.setattr(asyncio.base_events.BaseEventLoop, "getaddrinfo", fake)
    r = client.post("/api/v1/http/request", json={"method": "GET", "url": "http://rebind.example:8800/"}, headers=auth)
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "ssrf_blocked"
    assert calls["n"] >= 2  # pemeriksaan benar-benar dilakukan saat koneksi dibuat
