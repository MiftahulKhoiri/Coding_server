"""Pengaturan ukuran konteks model llama-server (file preset router + reload tanpa restart)."""
import json

import httpx
import pytest

from backend.core.exceptions import AppError
from backend.services import ai_providers, llama_context
from backend.services.llama_context import check_ctx, read_presets, write_presets

CALLS: list[str] = []
STATE = {"ctx": 8192}


async def _router(request: httpx.Request) -> httpx.Response:
    CALLS.append(str(request.url))
    if request.url.path == "/models":
        if request.url.params.get("reload"):
            STATE["ctx"] = 16384  # router membaca ulang preset
        args = ["llama-server", "--alias", "coder", "--ctx-size", str(STATE["ctx"]), "--model", "/m/coder.gguf"]
        return httpx.Response(200, json={"data": [
            {"id": "coder", "status": {"value": "loaded", "args": args}},
            {"id": "kecil", "status": {"value": "unloaded", "args": ["llama-server", "--ctx-size", "8192"]}}]})
    return httpx.Response(404)


@pytest.fixture()
def router(client, auth, tmp_path, monkeypatch):
    monkeypatch.setattr(ai_providers, "http_client",
                        lambda timeout=30.0: httpx.AsyncClient(transport=httpx.MockTransport(_router), timeout=timeout))
    monkeypatch.setattr(llama_context, "http_client",
                        lambda timeout=30.0: httpx.AsyncClient(transport=httpx.MockTransport(_router), timeout=timeout))
    svc = client.app.state.services
    old = svc.settings.llama_presets_file
    svc.settings.llama_presets_file = tmp_path / "presets.ini"
    CALLS.clear()
    STATE["ctx"] = 8192
    r = client.post("/api/v1/ai/connections", json={"name": "router", "kind": "llama_router", "location": "local",
                                                    "base_url": "http://router.test:59999"}, headers=auth)
    cid = r.json()["id"]
    yield cid
    client.delete(f"/api/v1/ai/connections/{cid}", headers=auth)
    svc.settings.llama_presets_file = old


def test_presets_roundtrip(tmp_path):
    p = tmp_path / "x.ini"
    assert read_presets(p) == {"default": None, "models": {}}
    write_presets(p, 16384, {"Qwen2.5-Coder-7B-Instruct-Q4_K_M": 12288})
    text = p.read_text()
    assert "[*]\nc = 16384" in text and "[Qwen2.5-Coder-7B-Instruct-Q4_K_M]\nc = 12288" in text
    assert read_presets(p) == {"default": 16384, "models": {"Qwen2.5-Coder-7B-Instruct-Q4_K_M": 12288}}
    with pytest.raises(AppError):
        write_presets(p, None, {"a]b": 4096})


@pytest.mark.parametrize("v", [1024, 200000, 8193])
def test_ctx_validation(v):
    with pytest.raises(AppError):
        check_ctx(v)


def test_context_status_and_save_reloads_router(client, auth, router):
    st = client.get(f"/api/v1/ai/context?connection_id={router}", headers=auth).json()
    assert {m["id"]: m["ctx"] for m in st["models"]} == {"coder": 8192, "kecil": 8192}
    assert st["default_ctx"] is None and not st["ready"] and st["problems"]  # router lokal tidak ditemukan
    assert "--models-preset" in st["fix_command"]
    r = client.put("/api/v1/ai/context", json={"connection_id": router, "default_ctx": 16384,
                                               "models": {"kecil": 4096}}, headers=auth)
    assert r.status_code == 200, r.text
    st = r.json()
    assert any("reload=1" in u for u in CALLS)
    m = {x["id"]: x for x in st["models"]}
    assert m["coder"]["ctx"] == 16384 and m["coder"]["configured"] == 16384 and m["coder"]["override"] is None
    assert m["kecil"]["configured"] == 4096 and m["kecil"]["override"] == 4096
    # null = kembali ikut bawaan
    st = client.put("/api/v1/ai/context", json={"connection_id": router, "models": {"kecil": None}},
                    headers=auth).json()
    assert {x["id"]: x["configured"] for x in st["models"]}["kecil"] == 16384
    assert client.app.state.services.llama_ctx.ctx_for("coder") == 16384
    assert client.put("/api/v1/ai/context", json={"connection_id": router, "default_ctx": 1000},
                      headers=auth).status_code == 422


def test_context_requires_router_and_admin(client, auth):
    r = client.post("/api/v1/ai/connections", json={"name": "online", "kind": "openai", "location": "online",
                                                    "base_url": "https://api.example.com"}, headers=auth)
    cid = r.json()["id"]
    try:
        r = client.get(f"/api/v1/ai/context?connection_id={cid}", headers=auth)
        assert r.status_code == 400 and r.json()["error"]["code"] == "not_router"
    finally:
        client.delete(f"/api/v1/ai/connections/{cid}", headers=auth)


def test_fix_command_edits_service(tmp_path):
    """Perintah perbaikan menghapus -c dan menambah --models-preset (diuji pada salinan file service)."""
    import subprocess

    unit = tmp_path / "llama-server.service"
    unit.write_text("[Service]\nExecStart=/home/pi5/llama.cpp/build/bin/llama-server --models-dir /home/pi5/models "
                    "--no-models-autoload --jinja --host 0.0.0.0 --port 8080 -c 8192\nRestart=on-failure\n")
    svc = llama_context.LlamaContextService.__new__(llama_context.LlamaContextService)
    svc.s = type("S", (), {"llama_presets_file": tmp_path / "p.ini"})()
    cmd = svc.fix_command(None).split(" && ")[0].replace("sudo ", "").replace(
        "/etc/systemd/system/llama-server.service", str(unit))
    for _ in range(2):  # idempoten
        subprocess.run(cmd, shell=True, check=True)
    line = [x for x in unit.read_text().splitlines() if x.startswith("ExecStart=")][0]
    assert " -c 8192" not in line and line.count("--models-preset") == 1
    assert f"llama-server --models-preset {tmp_path / 'p.ini'} --models-dir" in line and line.endswith("--port 8080")
