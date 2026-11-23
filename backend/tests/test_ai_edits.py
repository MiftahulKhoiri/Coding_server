"""AI agent: jawaban berisi blok file= -> proposal -> terapkan / batalkan / auto-apply."""
import json
import time

import httpx
import pytest

from backend.services import ai_providers
from backend.services.ai_edits import EditError, apply_replace, looks_truncated, parse_edits

ANSWER = {"text": ""}
LAST = {"body": None}


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/v1/models":
        return httpx.Response(200, json={"data": [{"id": "coder"}]})
    LAST["body"] = json.loads(request.content)
    chunks = [ANSWER["text"][i:i + 40] for i in range(0, len(ANSWER["text"]), 40)]
    body = "".join(f"data: {json.dumps({'choices': [{'delta': {'content': c}}]})}\n\n" for c in chunks) + "data: [DONE]\n\n"
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body.encode())


@pytest.fixture(autouse=True)
def fake(monkeypatch):
    monkeypatch.setattr(ai_providers, "http_client",
                        lambda timeout=30.0: httpx.AsyncClient(transport=httpx.MockTransport(_handler), timeout=timeout))


# ---------------- unit: parser & penerap ----------------
def test_parse_full_replace_and_headings():
    ans = """Perbaikan:
```python file=src/main.py
print("ok")
```
Lalu ubah util:
```edit file=util.py
<<<<<<< SEARCH
def f(x):
    return x+1
=======
def f(x):
    return x + 2
>>>>>>> REPLACE
```
File: lib/a.js
```js
console.log(1)
```
Contoh saja (bukan editan):
```bash
ls -la
```"""
    edits = parse_edits(ans)
    assert [(e.path, e.kind) for e in edits] == [("src/main.py", "full"), ("util.py", "replace"), ("lib/a.js", "full")]
    assert edits[0].content == 'print("ok")\n'
    assert edits[1].blocks[0][1] == "def f(x):\n    return x + 2\n"


def test_apply_replace_tolerant_and_strict():
    src = "def f(x):\n    return x+1   \n\nprint(f(1))\n"
    # spasi akhir baris berbeda tetap cocok
    out = apply_replace(src, [("def f(x):\n    return x+1\n", "def f(x):\n    return x + 2\n")])
    assert out == "def f(x):\n    return x + 2\n\nprint(f(1))\n"
    # indentasi berbeda (model menulis tanpa indent) disesuaikan
    cls = "class A:\n    def g(self):\n        return 1\n"
    out = apply_replace(cls, [("def g(self):\n    return 1\n", "def g(self):\n    return 2\n")])
    assert out == "class A:\n    def g(self):\n        return 2\n"
    with pytest.raises(EditError, match="tidak ditemukan"):
        apply_replace(src, [("tidak ada\n", "x\n")])
    with pytest.raises(EditError, match="lebih dari sekali"):
        apply_replace("a\nb\na\n", [("a\n", "c\n")])
    assert apply_replace("", [("", "baru\n")]) == "baru\n"


def test_truncation_detection():
    assert looks_truncated("def a():\n    pass\n# ... kode lain tetap sama\n")
    assert looks_truncated("x = 1\n...\n")
    assert not looks_truncated("for i in range(3):\n    print(i)\n")


# ---------------- integrasi: chat -> edits ----------------
def _setup_model(client, auth):
    r = client.post("/api/v1/ai/connections", json={"name": "edit", "kind": "openai", "location": "local",
                                                    "base_url": "http://edit.test"}, headers=auth)
    cid = r.json()["id"]
    client.post("/api/v1/ai/apply", json={"connection_id": cid, "model": "coder"}, headers=auth)
    end = time.time() + 10
    while client.get("/api/v1/ai/status", headers=auth).json()["status"] != "ready":
        assert time.time() < end
        time.sleep(0.2)
    return cid


def _chat(client, token, **msg):
    events = []
    with client.websocket_connect(f"/ws/ai/chat?token={token}") as ws:
        ws.send_json({"type": "send", **msg})
        while True:
            ev = ws.receive_json()
            events.append(ev)
            if ev["type"] in ("done", "error"):
                return events


def _read(client, auth, project, path):
    return client.get("/api/v1/files/read", params={"project_id": project, "path": path}, headers=auth)


def test_chat_edits_apply_revert_and_auto(client, auth, token, project):
    cid = _setup_model(client, auth)
    client.put("/api/v1/files/write", json={"project_id": project, "path": "calc.py",
                                            "content": "def add(a, b):\n    return a - b\n\nprint(add(2, 3))\n"}, headers=auth)
    ANSWER["text"] = ("Bug-nya operator salah.\n```edit file=calc.py\n<<<<<<< SEARCH\n    return a - b\n=======\n"
                      "    return a + b\n>>>>>>> REPLACE\n```\nDan tambahkan test:\n```python file=test_calc.py\n"
                      "from calc import add\nassert add(2, 3) == 5\n```\n")
    ev = _chat(client, token, content="perbaiki", project_id=project, editor_name="calc.py",
               editor_text=_read(client, auth, project, "calc.py").json()["content"])
    # protokol edit dikirim ke model + struktur proyek
    system = LAST["body"]["messages"][0]["content"]
    assert "file=" in system and "SEARCH" in system
    assert "calc.py" in LAST["body"]["messages"][-1]["content"]
    edits = next(e for e in ev if e["type"] == "edits")
    assert [e["type"] for e in ev][-2:] == ["edits", "done"]
    items = {i["path"]: i for i in edits["items"]}
    assert items["calc.py"]["status"] == "pending" and items["calc.py"]["additions"] == 1 and items["calc.py"]["deletions"] == 1
    assert "+    return a + b" in items["calc.py"]["diff"]
    assert items["test_calc.py"]["new_file"] and items["test_calc.py"]["status"] == "pending"
    # belum diterapkan
    assert "a - b" in _read(client, auth, project, "calc.py").json()["content"]

    # terapkan, lalu file berubah & tercatat sebagai AI
    pid = items["calc.py"]["id"]
    r = client.post(f"/api/v1/ai/proposals/{pid}/decide", json={"project_id": project, "approve": True}, headers=auth)
    assert r.status_code == 200 and r.json()["proposal"]["status"] == "approved", r.text
    assert "a + b" in _read(client, auth, project, "calc.py").json()["content"]
    hist = client.get("/api/v1/files/history", params={"project_id": project, "path": "calc.py"}, headers=auth).json()
    assert any(h.get("actor_type") == "ai" for h in hist.get("history", hist if isinstance(hist, list) else []))
    # tidak bisa diterapkan dua kali
    assert client.post(f"/api/v1/ai/proposals/{pid}/decide", json={"project_id": project, "approve": True},
                       headers=auth).status_code == 409
    # batalkan -> isi lama kembali
    r = client.post(f"/api/v1/ai/proposals/{pid}/revert", json={"project_id": project}, headers=auth)
    assert r.status_code == 200 and r.json()["status"] == "reverted", r.text
    assert "a - b" in _read(client, auth, project, "calc.py").json()["content"]

    # file baru diterapkan lalu dibatalkan -> file dihapus
    nid = items["test_calc.py"]["id"]
    client.post(f"/api/v1/ai/proposals/{nid}/decide", json={"project_id": project, "approve": True}, headers=auth)
    assert _read(client, auth, project, "test_calc.py").status_code == 200
    client.post(f"/api/v1/ai/proposals/{nid}/revert", json={"project_id": project}, headers=auth)
    assert _read(client, auth, project, "test_calc.py").status_code == 404

    # proposal basi: file diubah setelah usulan dibuat -> 409, isi tidak ditimpa
    ev = _chat(client, token, content="lagi", project_id=project)
    stale = next(e for e in ev if e["type"] == "edits")["items"][0]
    client.put("/api/v1/files/write", json={"project_id": project, "path": "calc.py", "content": "x = 1\n"}, headers=auth)
    r = client.post(f"/api/v1/ai/proposals/{stale['id']}/decide", json={"project_id": project, "approve": True}, headers=auth)
    assert r.status_code == 409 and r.json()["error"]["code"] == "proposal_stale"
    assert _read(client, auth, project, "calc.py").json()["content"] == "x = 1\n"

    # SEARCH tidak cocok -> proposal 'failed' dengan alasan, file tidak disentuh
    ev = _chat(client, token, content="lagi", project_id=project)
    failed = {i["path"]: i for i in next(e for e in ev if e["type"] == "edits")["items"]}["calc.py"]
    assert failed["status"] == "failed" and "tidak ditemukan" in failed["error"]

    # auto_apply: langsung diterapkan
    client.put("/api/v1/files/write", json={"project_id": project, "path": "calc.py",
                                            "content": "def add(a, b):\n    return a - b\n"}, headers=auth)
    ANSWER["text"] = "```edit file=calc.py\n<<<<<<< SEARCH\nreturn a - b\n=======\nreturn a + b\n>>>>>>> REPLACE\n```"
    ev = _chat(client, token, content="perbaiki", project_id=project, auto_apply=True)
    item = next(e for e in ev if e["type"] == "edits")["items"][0]
    assert item["status"] == "approved"
    assert _read(client, auth, project, "calc.py").json()["content"] == "def add(a, b):\n    return a + b\n"
    # daftar proposal per percakapan (untuk memuat ulang riwayat chat)
    conv = next(e for e in ev if e["type"] == "conversation")["id"]
    lst = client.get("/api/v1/ai/proposals", params={"project_id": project, "conversation_id": conv}, headers=auth).json()
    assert [p["id"] for p in lst["proposals"]] == [item["id"]] and "content" not in lst["proposals"][0]

    # tanpa proyek: tidak ada mode edit
    ev = _chat(client, token, content="halo")
    assert not any(e["type"] == "edits" for e in ev)
    assert "SEARCH" not in LAST["body"]["messages"][0]["content"]

    client.post("/api/v1/ai/unload", headers=auth)
    client.delete(f"/api/v1/ai/connections/{cid}", headers=auth)
