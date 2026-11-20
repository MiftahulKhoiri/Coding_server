"""Uji fitur AI dengan penyedia tiruan (llama-server router, OpenAI, Anthropic, Gemini)."""
import json
import time

import httpx
import pytest

from backend.services import ai_providers

STATE = {"models": {"Qwen3_1.7B": "unloaded", "Coder-7B": "unloaded"}, "calls": [], "last_body": None}


def sse(events):
    return "".join(f"data: {e if isinstance(e, str) else json.dumps(e)}\n\n" for e in events).encode()


def handler(request: httpx.Request) -> httpx.Response:
    path, host = request.url.path, request.url.host
    STATE["calls"].append((request.method, host, path))
    body = json.loads(request.content) if request.content else {}
    if host == "router.test":
        if path == "/v1/models":
            for k, v in STATE["models"].items():  # loading -> loaded pada polling berikut
                if v == "loading":
                    STATE["models"][k] = "loaded"
            return httpx.Response(200, json={"data": [{"id": k, "status": {"value": v}, "context_length": 8192}
                                                      for k, v in STATE["models"].items()]})
        if path == "/models/load":
            STATE["models"][body["model"]] = "loading"
            return httpx.Response(200, json={"success": True})
        if path == "/models/unload":
            if STATE["models"].get(body["model"]) != "loaded":
                return httpx.Response(400, json={"error": {"message": "not loaded"}})
            STATE["models"][body["model"]] = "unloaded"
            return httpx.Response(200, json={"success": True})
        if path == "/v1/chat/completions":
            STATE["last_body"] = body
            if STATE["models"].get(body["model"]) != "loaded":
                return httpx.Response(400, json={"error": {"message": "model not loaded"}})
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse([
                {"choices": [{"delta": {"reasoning_content": "hmm "}}]},
                {"choices": [{"delta": {"content": "Halo"}}]},
                {"choices": [{"delta": {"content": " dari model lokal"}}]},
                "[DONE]"]))
    if host == "api.openai.test":
        if request.headers.get("authorization") != "Bearer sk-benar":
            return httpx.Response(401, json={"error": {"message": "Incorrect API key"}})
        if path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "gpt-x"}, {"id": "gpt-y"}]})
        if path == "/v1/chat/completions":
            return httpx.Response(200, content=sse([{"choices": [{"delta": {"content": "online!"}}]}, "[DONE]"]))
    if host == "api.anthropic.test":
        assert request.headers["x-api-key"] == "ak"
        if path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "claude-x"}]})
        assert body["system"].startswith("Kamu")
        return httpx.Response(200, content=sse([{"type": "message_start"},
                                                {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hai "}},
                                                {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Claude"}},
                                                {"type": "message_stop"}]))
    if host == "gemini.test":
        if path == "/v1beta/models":
            return httpx.Response(200, json={"models": [{"name": "models/gemini-x", "supportedGenerationMethods": ["generateContent"]},
                                                        {"name": "models/embed", "supportedGenerationMethods": ["embedContent"]}]})
        assert body["contents"][-1]["role"] == "user"
        return httpx.Response(200, content=sse([{"candidates": [{"content": {"parts": [{"text": "Gem", "thought": True}]}}]},
                                                {"candidates": [{"content": {"parts": [{"text": "ini"}]}}]}]))
    return httpx.Response(404, json={"error": "tidak dikenal"})


@pytest.fixture(autouse=True)
def fake_providers(monkeypatch):
    monkeypatch.setattr(ai_providers, "http_client",
                        lambda timeout=30.0: httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=timeout))
    yield


def wait_status(client, auth, want, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        st = client.get("/api/v1/ai/status", headers=auth).json()
        if st["status"] == want:
            return st
        time.sleep(0.3)
    raise AssertionError(f"status bukan {want}: {st}")


def add_conn(client, auth, **kw):
    r = client.post("/api/v1/ai/connections", json=kw, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()


def test_presets_and_default_connection(client, auth):
    assert any(p["kind"] == "anthropic" for p in client.get("/api/v1/ai/presets", headers=auth).json()["presets"])
    conns = client.get("/api/v1/ai/connections", headers=auth).json()["connections"]
    assert any(c["kind"] == "llama_router" and c["location"] == "local" for c in conns)


def test_local_router_load_chat_switch_unload(client, auth, token):
    c = add_conn(client, auth, name="router", kind="llama_router", location="local", base_url="http://router.test:8080/v1")
    assert c["base_url"] == "http://router.test:8080"  # /v1 dibuang
    models = client.get(f"/api/v1/ai/connections/{c['id']}/models", headers=auth).json()["models"]
    assert {m["id"] for m in models} == {"Qwen3_1.7B", "Coder-7B"} and models[0]["status"] == "unloaded"

    r = client.post("/api/v1/ai/apply", json={"connection_id": c["id"], "model": "Qwen3_1.7B"}, headers=auth)
    assert r.status_code == 200
    st = wait_status(client, auth, "ready")
    assert st["model"] == "Qwen3_1.7B" and st["loaded_by_us"] and STATE["models"]["Qwen3_1.7B"] == "loaded"

    # chat streaming via WebSocket + riwayat tersimpan
    events = []
    with client.websocket_connect(f"/ws/ai/chat?token={token}") as ws:
        ws.send_json({"type": "send", "content": "Apa kabar?", "editor_text": "print(1)", "editor_name": "main.py"})
        while True:
            ev = ws.receive_json()
            events.append(ev)
            if ev["type"] in ("done", "error"):
                break
    types = [e["type"] for e in events]
    assert types[0] == "conversation" and "reasoning" in types and types[-1] == "done", events
    text = "".join(e["text"] for e in events if e["type"] == "delta")
    assert text == "Halo dari model lokal"
    sent = STATE["last_body"]["messages"]
    assert sent[0]["role"] == "system" and "print(1)" in sent[-1]["content"]
    conv_id = events[0]["id"]
    conv = client.get(f"/api/v1/ai/conversations/{conv_id}", headers=auth).json()
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    assert conv["messages"][1]["reasoning"] == "hmm "

    # pesan kedua di percakapan sama membawa riwayat
    with client.websocket_connect(f"/ws/ai/chat?token={token}") as ws:
        ws.send_json({"type": "send", "conversation_id": conv_id, "content": "Lanjut"})
        while ws.receive_json()["type"] != "done":
            pass
    assert [m["role"] for m in STATE["last_body"]["messages"]] == ["system", "user", "assistant", "user"]

    # ganti model: model lama yang kita muat dibongkar
    client.post("/api/v1/ai/apply", json={"connection_id": c["id"], "model": "Coder-7B"}, headers=auth)
    wait_status(client, auth, "ready")
    assert STATE["models"] == {"Qwen3_1.7B": "unloaded", "Coder-7B": "loaded"}

    st = client.post("/api/v1/ai/unload", headers=auth).json()
    assert st["status"] == "idle" and STATE["models"]["Coder-7B"] == "unloaded"
    with client.websocket_connect(f"/ws/ai/chat?token={token}") as ws:
        ws.send_json({"type": "send", "content": "halo"})
        assert ws.receive_json()["code"] == "ai_not_configured"

    assert client.delete(f"/api/v1/ai/conversations/{conv_id}", headers=auth).status_code == 200
    assert client.delete(f"/api/v1/ai/connections/{c['id']}", headers=auth).status_code == 200


def test_online_openai_key_is_secret_and_validated(client, auth):
    c = add_conn(client, auth, name="OpenAI uji", kind="openai", location="online", base_url="http://api.openai.test",
                 api_key="sk-salah")
    assert c["has_key"] and "sk-salah" not in json.dumps(client.get("/api/v1/ai/connections", headers=auth).json())
    r = client.get(f"/api/v1/ai/connections/{c['id']}/models", headers=auth)
    assert r.status_code == 502 and r.json()["error"]["code"] == "ai_auth"
    client.put(f"/api/v1/ai/connections/{c['id']}", json={"name": "OpenAI uji", "kind": "openai", "location": "online",
                                                         "base_url": "http://api.openai.test", "api_key": "sk-benar"},
               headers=auth)
    ids = [m["id"] for m in client.get(f"/api/v1/ai/connections/{c['id']}/models", headers=auth).json()["models"]]
    assert ids == ["gpt-x", "gpt-y"]
    st = client.post("/api/v1/ai/apply", json={"connection_id": c["id"], "model": "gpt-y", "wait": True}, headers=auth).json()
    assert st["status"] == "ready" and not st["loaded_by_us"]
    r = client.post("/api/v1/ai/chat", json={"messages": [{"role": "user", "content": "hai"}]}, headers=auth).json()
    assert r["content"] == "online!"
    st = client.post("/api/v1/ai/apply", json={"connection_id": c["id"], "model": "tidak-ada", "wait": True}, headers=auth).json()
    assert st["status"] == "error" and "tidak tersedia" in st["message"]
    client.post("/api/v1/ai/unload", headers=auth)


def test_anthropic_and_gemini(client, auth):
    a = add_conn(client, auth, name="Claude", kind="anthropic", location="online", base_url="http://api.anthropic.test",
                 api_key="ak")
    assert client.get(f"/api/v1/ai/connections/{a['id']}/models", headers=auth).json()["models"][0]["id"] == "claude-x"
    client.post("/api/v1/ai/apply", json={"connection_id": a["id"], "model": "claude-x", "wait": True}, headers=auth)
    r = client.post("/api/v1/ai/chat", json={"messages": [{"role": "user", "content": "hai"}]}, headers=auth).json()
    assert r["content"] == "Hai Claude"
    g = add_conn(client, auth, name="Gemini", kind="gemini", location="online", base_url="http://gemini.test", api_key="gk")
    assert [m["id"] for m in client.get(f"/api/v1/ai/connections/{g['id']}/models", headers=auth).json()["models"]] == ["gemini-x"]
    client.post("/api/v1/ai/apply", json={"connection_id": g["id"], "model": "gemini-x", "wait": True}, headers=auth)
    r = client.post("/api/v1/ai/chat", json={"messages": [{"role": "user", "content": "hai"}]}, headers=auth).json()
    assert r["content"] == "ini" and r["reasoning"] == "Gem"
    client.post("/api/v1/ai/unload", headers=auth)


def test_settings_and_permissions(client, auth):
    st = client.put("/api/v1/ai/settings", json={"system_prompt": "Kamu asisten uji.", "temperature": 0.2,
                                                 "idle_unload_minutes": 5}, headers=auth).json()
    assert st["settings"]["temperature"] == 0.2 and st["settings"]["idle_unload_minutes"] == 5
    client.post("/api/v1/auth/users", json={"username": "dev_ai", "password": "dev-ai-pass1", "role": "developer"}, headers=auth)
    tok = client.post("/api/v1/auth/login", json={"username": "dev_ai", "password": "dev-ai-pass1"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.post("/api/v1/ai/connections", json={"kind": "openai", "location": "local", "base_url": "http://x.test"},
                       headers=h).status_code == 403
    assert client.post("/api/v1/ai/unload", headers=h).status_code == 403
    assert client.get("/api/v1/ai/status", headers=h).status_code == 200
    assert client.get("/api/v1/ai/conversations", headers=h).json()["conversations"] == []
