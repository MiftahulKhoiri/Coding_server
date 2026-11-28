"""Jawaban AI Chat tetap berjalan di server walau aplikasi ditutup; bisa disambung lagi (attach) dan dihentikan."""
import asyncio
import json
import time

import httpx
import pytest

from backend.services import ai_providers

CHUNKS = ["Satu ", "dua ", "tiga ", "empat ", "lima"]
DELAY = {"s": 0.25}


async def handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/v1/models":
        return httpx.Response(200, json={"data": [{"id": "lambat"}]})

    async def body():
        for t in CHUNKS:
            await asyncio.sleep(DELAY["s"])
            yield f"data: {json.dumps({'choices': [{'delta': {'content': t}}]})}\n\n".encode()
        yield b"data: [DONE]\n\n"
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body())


@pytest.fixture()
def slow_model(client, auth, monkeypatch):
    monkeypatch.setattr(ai_providers, "http_client",
                        lambda timeout=30.0: httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=timeout))
    c = client.post("/api/v1/ai/connections", json={"name": "Lambat", "kind": "openai", "location": "online",
                                                    "base_url": "http://slow.test", "api_key": "k"}, headers=auth).json()
    st = client.post("/api/v1/ai/apply", json={"connection_id": c["id"], "model": "lambat", "wait": True}, headers=auth).json()
    assert st["status"] == "ready", st
    yield c
    client.post("/api/v1/ai/unload", headers=auth)
    client.delete(f"/api/v1/ai/connections/{c['id']}", headers=auth)


def conv(client, auth, cid):
    return client.get(f"/api/v1/ai/conversations/{cid}", headers=auth).json()


def wait_idle(client, auth, cid, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        d = conv(client, auth, cid)
        if not d["generating"]:
            return d
        time.sleep(0.2)
    raise AssertionError("jawaban tidak selesai")


def test_answer_continues_after_app_disconnects_and_can_be_reattached(client, auth, token, slow_model):
    with client.websocket_connect(f"/ws/ai/chat?token={token}") as ws:
        ws.send_json({"type": "send", "content": "hitung"})
        cid = ws.receive_json()["id"]            # "conversation"
        assert ws.receive_json()["type"] == "start"
    # aplikasi "ditutup": koneksi putus, server tetap menjawab
    assert conv(client, auth, cid)["generating"] is True
    listed = {c["id"]: c for c in client.get("/api/v1/ai/conversations", headers=auth).json()["conversations"]}
    assert listed[cid]["generating"] is True
    # dibuka lagi: attach menerima ulang semua event dari awal lalu lanjut sampai selesai
    with client.websocket_connect(f"/ws/ai/chat?token={token}") as ws:
        ws.send_json({"type": "attach", "conversation_id": cid})
        events = []
        while True:
            ev = ws.receive_json()
            events.append(ev)
            if ev["type"] in ("done", "error", "stopped"):
                break
    assert events[-1]["type"] == "done", events
    assert "".join(e["text"] for e in events if e["type"] == "delta") == "".join(CHUNKS)
    d = wait_idle(client, auth, cid)
    assert [m["role"] for m in d["messages"]] == ["user", "assistant"]
    assert d["messages"][1]["content"] == "".join(CHUNKS)


def test_answer_saved_even_if_nobody_reattaches(client, auth, token, slow_model):
    with client.websocket_connect(f"/ws/ai/chat?token={token}") as ws:
        ws.send_json({"type": "send", "content": "hitung lagi"})
        cid = ws.receive_json()["id"]
    d = wait_idle(client, auth, cid)
    assert d["messages"][-1]["content"] == "".join(CHUNKS)
    # tidak ada jawaban berjalan -> attach dijawab idle (aplikasi memuat ulang dari database)
    with client.websocket_connect(f"/ws/ai/chat?token={token}") as ws:
        ws.send_json({"type": "attach", "conversation_id": cid})
        # job selesai < 10 menit lalu masih bisa diputar ulang; selain itu "idle"
        first = ws.receive_json()
        assert first["type"] in ("conversation", "idle"), first


def test_busy_and_stop_from_another_connection(client, auth, token, slow_model):
    DELAY["s"] = 0.6
    try:
        with client.websocket_connect(f"/ws/ai/chat?token={token}") as ws:
            ws.send_json({"type": "send", "content": "panjang"})
            cid = ws.receive_json()["id"]
        with client.websocket_connect(f"/ws/ai/chat?token={token}") as ws:
            ws.send_json({"type": "send", "content": "pertanyaan lain"})
            err = ws.receive_json()
            assert err["type"] == "error" and err["code"] == "busy" and err["conversation_id"] == cid, err
            time.sleep(0.9)  # setidaknya satu potongan jawaban sudah diterima
            ws.send_json({"type": "stop", "conversation_id": cid})
        d = wait_idle(client, auth, cid)
        assert d["messages"][-1]["role"] == "assistant" and d["messages"][-1]["content"].endswith("[dihentikan]"), d
    finally:
        DELAY["s"] = 0.25
