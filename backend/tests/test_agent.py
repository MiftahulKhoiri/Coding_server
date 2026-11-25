"""AI Coding Agent: task persisten, tool + izin, persetujuan, uji, laporan, pembatalan, pemulihan."""
import json
import time

import httpx
import pytest

from backend.services import ai_providers
from backend.services.agent_service import AgentService, extract_call
from backend.services.agent_tools import TOOLS, ToolError

SCRIPT: list[str] = []
SEEN: list[dict] = []
DELAY = {"s": 0.0}


async def _handler(request: httpx.Request) -> httpx.Response:
    import asyncio

    await asyncio.sleep(DELAY["s"])
    if request.url.path == "/v1/models":
        return httpx.Response(200, json={"data": [{"id": "coder"}]})
    SEEN.append(json.loads(request.content))
    text = SCRIPT.pop(0) if SCRIPT else '```json\n{"tool": "finish", "args": {"summary": "skrip habis"}}\n```'
    body = f"data: {json.dumps({'choices': [{'delta': {'content': text}}]})}\n\ndata: [DONE]\n\n"
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body.encode())


@pytest.fixture(autouse=True)
def fake(monkeypatch):
    monkeypatch.setattr(ai_providers, "http_client",
                        lambda timeout=30.0: httpx.AsyncClient(transport=httpx.MockTransport(_handler), timeout=timeout))
    SCRIPT.clear()
    SEEN.clear()
    DELAY["s"] = 0.0


@pytest.fixture()
def model(client, auth):
    r = client.post("/api/v1/ai/connections", json={"name": "agent", "kind": "openai", "location": "local",
                                                    "base_url": "http://agent.test"}, headers=auth)
    cid = r.json()["id"]
    client.post("/api/v1/ai/apply", json={"connection_id": cid, "model": "coder"}, headers=auth)
    end = time.time() + 10
    while client.get("/api/v1/ai/status", headers=auth).json()["status"] != "ready":
        assert time.time() < end
        time.sleep(0.1)
    yield cid
    client.post("/api/v1/ai/unload", headers=auth)
    client.delete(f"/api/v1/ai/connections/{cid}", headers=auth)


def J(tool, **args):
    return "```json\n" + json.dumps({"thought": f"pakai {tool}", "tool": tool, "args": args}) + "\n```"


def wait_status(client, auth, tid, statuses, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        t = client.get(f"/api/v1/agent/tasks/{tid}", headers=auth).json()
        if t["status"] in statuses:
            return t
        time.sleep(0.1)
    raise AssertionError(f"status {t['status']} bukan {statuses}")


# ---------------- unit ----------------
def test_extract_call_variants():
    obj, code = extract_call('Oke.\n```json\n{"tool": "write_file", "args": {"path": "a.py"}}\n```\n```python\nprint(1)\n```')
    assert obj["tool"] == "write_file" and code == "print(1)\n"
    obj, code = extract_call('saya pikir {"thought": "x", "tool": "list_dir", "args": {}} begitu')
    assert obj["tool"] == "list_dir" and code is None
    with pytest.raises(ValueError):
        extract_call("tidak ada json di sini")


def test_tool_validation():
    t = TOOLS["read_file"]
    assert t.validate({"path": "a.py", "start_line": "5"}) == {"path": "a.py", "start_line": 5}
    with pytest.raises(ToolError):
        t.validate({})
    with pytest.raises(ToolError):
        t.validate({"path": "a", "hack": 1})
    with pytest.raises(ToolError):
        t.validate({"path": 3})


def test_tools_permissions_listed(client, auth):
    tools = {t["name"]: t for t in client.get("/api/v1/agent/tools", headers=auth).json()["tools"]}
    assert tools["read_file"]["allowed"] and tools["write_file"]["allowed"]
    assert not tools["delete_file"]["allowed"]  # peran 'ai' tidak punya hak hapus


# ---------------- integrasi ----------------
def test_agent_full_flow_with_approval_and_tests(client, auth, project, model):
    w = lambda p, c: client.put("/api/v1/files/write", json={"project_id": project, "path": p, "content": c}, headers=auth)
    w("calc.py", "def add(a, b):\n    return a - b\n")
    w("test_calc.py", "import unittest\nfrom calc import add\n\n\nclass T(unittest.TestCase):\n"
                      "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n")
    SCRIPT.extend([
        J("project_info"),
        J("update_plan", steps=[{"id": "1", "description": "perbaiki add", "files": ["calc.py"], "status": "in_progress",
                                 "verification": "run_tests"}]),
        J("read_file", path="calc.py"),
        J("edit_file", path="calc.py", reason="operator salah")
        + "\n```\n<<<<<<< SEARCH\n    return a - b\n=======\n    return a + b\n>>>>>>> REPLACE\n```",
        J("run_tests", id="unittest"),
        J("update_plan", steps=[{"id": "1", "description": "perbaiki add", "status": "done"}]),
        J("finish", summary="add diperbaiki", limitations="-"),
    ])
    r = client.post("/api/v1/agent/tasks", json={"project_id": project, "description": "Perbaiki fungsi add"},
                    headers=auth)
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    t = wait_status(client, auth, tid, {"WAITING_APPROVAL", "FAILED"})
    assert t["status"] == "WAITING_APPROVAL", t
    assert t["pending_proposals"] == 1 and t["plan"][0]["description"] == "perbaiki add"
    # file belum berubah sebelum disetujui
    assert "a - b" in client.get("/api/v1/files/read", params={"project_id": project, "path": "calc.py"},
                                 headers=auth).json()["content"]
    # tool dan rencana terlihat di log; konteks model berisi isi file nyata
    kinds = [e["kind"] for e in client.get(f"/api/v1/agent/tasks/{tid}/events", headers=auth).json()["events"]]
    assert "plan" in kinds and "tool_call" in kinds and "approval" in kinds
    assert any("return a - b" in m["content"] for m in SEEN[-1]["messages"])
    # resume ditolak selama masih ada proposal pending
    assert client.post(f"/api/v1/agent/tasks/{tid}/resume", headers=auth).status_code == 409

    props = client.get(f"/api/v1/agent/tasks/{tid}/proposals", headers=auth).json()["proposals"]
    assert props[0]["task_id"] == tid and props[0]["risk"] == "MEDIUM"
    r = client.post(f"/api/v1/ai/proposals/{props[0]['id']}/decide", json={"project_id": project, "approve": True},
                    headers=auth)
    assert r.status_code == 200, r.text
    # setelah disetujui task lanjut otomatis: tes dijalankan nyata lalu finish
    t = wait_status(client, auth, tid, {"COMPLETED", "FAILED"}, timeout=120)
    assert t["status"] == "COMPLETED", t
    rep = t["report"]
    assert rep["verified"]["files_changed"] == ["calc.py"]
    assert rep["verified"]["tests_passed"] == 1 and rep["verified"]["tests_failed"] == 0
    assert rep["ai_generated"]["summary"] == "add diperbaiki"
    assert t["progress"] == 1.0
    obs = [e for e in client.get(f"/api/v1/agent/tasks/{tid}/events", headers=auth).json()["events"]
           if e["kind"] == "observation" and e["data"]["tool"] == "run_tests"]
    assert "COMPLETED, exit code: 0" in obs[-1]["data"]["text"]
    assert any(x["id"] == tid for x in client.get("/api/v1/agent/tasks", params={"project_id": project},
                                                  headers=auth).json()["tasks"])
    assert client.delete(f"/api/v1/agent/tasks/{tid}", headers=auth).status_code == 200


def test_agent_auto_apply_and_tool_errors(client, auth, project, model):
    SCRIPT.extend([
        J("read_file", path="tidak_ada.py"),            # error dikembalikan ke model, task tetap jalan
        J("delete_file", path="main.py"),               # tidak diizinkan untuk agen
        J("write_file", path="notes.md") + "\n```markdown\n# Catatan\n```",
        J("write_file", path="deploy.sh", content="echo hai\n"),   # HIGH: tidak diterapkan otomatis
        J("finish", summary="ok"),
    ])
    tid = client.post("/api/v1/agent/tasks", json={"project_id": project, "description": "tulis catatan",
                                                   "auto_apply": True}, headers=auth).json()["id"]
    t = wait_status(client, auth, tid, {"COMPLETED", "FAILED"})
    assert t["status"] == "COMPLETED", t
    root = client.app.state.services.projects.project_dir(project)
    assert (root / "notes.md").read_text() == "# Catatan\n"
    assert not (root / "deploy.sh").exists() and (root / "main.py").exists()
    obs = [e["data"] for e in client.get(f"/api/v1/agent/tasks/{tid}/events", headers=auth).json()["events"]
           if e["kind"] == "observation"]
    assert not obs[0]["ok"] and "tidak ditemukan" in obs[0]["text"]
    assert not obs[1]["ok"] and "izin 'delete'" in obs[1]["text"]
    assert obs[2]["ok"] and "DITERAPKAN" in obs[2]["text"]
    assert "MENUNGGU" in obs[3]["text"]
    assert t["report"]["verified"]["files_pending"] == ["deploy.sh"]


def test_agent_bad_format_fails_and_cancel(client, auth, project, model):
    SCRIPT.extend(["bukan json", "masih bukan", "tetap bukan"])
    tid = client.post("/api/v1/agent/tasks", json={"project_id": project, "description": "x"}, headers=auth).json()["id"]
    t = wait_status(client, auth, tid, {"FAILED", "COMPLETED"})
    assert t["status"] == "FAILED" and "format" in t["error"]
    # retry dari checkpoint
    SCRIPT.extend([J("finish", summary="pulih")])
    r = client.post(f"/api/v1/agent/tasks/{tid}/resume", headers=auth)
    assert r.status_code == 200
    assert wait_status(client, auth, tid, {"COMPLETED", "FAILED"})["status"] == "COMPLETED"

    # batalkan task yang sedang berjalan (model lambat)
    DELAY["s"] = 0.3
    SCRIPT.extend([J("list_dir")] * 50)
    tid2 = client.post("/api/v1/agent/tasks", json={"project_id": project, "description": "lama",
                                                    "max_steps": 50}, headers=auth).json()["id"]
    r = client.post(f"/api/v1/agent/tasks/{tid2}/cancel", headers=auth)
    assert r.status_code == 200 and r.json()["status"] == "CANCELLED", r.json()["error"]
    assert r.json()["steps_used"] < 50
    SCRIPT.clear()


def test_agent_permissions_and_restart_recovery(client, auth, project):
    svc = client.app.state.services
    # pengguna viewer tidak boleh membuat task (izin execute) dan agen tak punya hak tulis untuknya
    from backend.core.exceptions import Forbidden

    viewer = {"id": 999, "username": "lihat", "perms": {"read"}}
    with pytest.raises(Forbidden):
        svc.agent.create({**viewer, "perms": set()}, project, "x")
    assert not [t for t in svc.agent.tools_for(viewer) if t["allowed"] and t["permission"] != "read"]
    # task yang 'berjalan' saat server mati -> PAUSED setelah restart, bukan hilang
    now = time.time()
    svc.db.execute("INSERT INTO agent_tasks(id, user_id, project_id, title, description, status, stage, created_at, "
                   "updated_at) VALUES('zombie', 1, ?, 't', 'd', 'EXECUTING', 'EXECUTING', ?, ?)", (project, now, now))
    fresh = AgentService(svc.settings, svc.db, lambda: svc)
    # sekadar membuat service (mis. mengimpor aplikasi dari skrip) tidak boleh menjeda task yang berjalan
    assert svc.db.one("SELECT status FROM agent_tasks WHERE id='zombie'")["status"] == "EXECUTING"
    fresh.recover()  # dipanggil lifespan saat server benar-benar mulai
    row = svc.db.one("SELECT status, current_op FROM agent_tasks WHERE id='zombie'")
    assert row["status"] == "PAUSED" and "checkpoint" in row["current_op"]
    svc.db.execute("DELETE FROM agent_tasks WHERE id='zombie'")
