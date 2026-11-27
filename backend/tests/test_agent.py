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
CTX_FAIL = {"n": 0}  # jumlah permintaan berikutnya yang ditolak "konteks terlampaui" (seperti llama-server)


async def _handler(request: httpx.Request) -> httpx.Response:
    import asyncio

    await asyncio.sleep(DELAY["s"])
    if request.url.path == "/v1/models":
        return httpx.Response(200, json={"data": [{"id": "coder"}]})
    if CTX_FAIL["n"] > 0:
        CTX_FAIL["n"] -= 1
        SEEN.append({"rejected": True, **json.loads(request.content)})
        return httpx.Response(400, json={"error": {"code": 400, "type": "exceed_context_size_error", "message":
                              "request (8226 tokens) exceeds the available context size (8192 tokens), try increasing it"}})
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
    CTX_FAIL["n"] = 0
    AgentService._ctx_tokens.clear()


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


def test_extract_call_recovers_python_style_content():
    """Balasan asli Qwen3.5-4B dari log task gagal: isi app.py ditulis di args.content dengan gaya Python
    (''' dan reason="..."). Dulu isi file dibuang diam-diam → model mengulang 9x sampai langkah habis."""
    import ast
    from pathlib import Path

    raw = (Path(__file__).parent / "data" / "agent_broken_write_file.txt").read_text()
    obj, _ = extract_call(raw)
    content = obj["args"]["content"]
    assert obj["tool"] == "write_file" and obj["args"]["path"] == "app.py"
    assert content.startswith("from flask import Flask") and content.endswith("app.run(debug=True)\n")
    assert "render_template_string('''" in content  # ''' milik kode Python tetap utuh
    ast.parse(content)
    assert obj["args"]["reason"].startswith("Membuat backend Flask")


def test_compact_respects_budget_and_keeps_latest():
    big_code = "x = 1\n" * 2000
    msgs = [{"role": "system", "content": "S" * 3000}, {"role": "user", "content": "TUGAS"}]
    for i in range(8):
        msgs.append({"role": "assistant", "content": f"langkah {i} " + big_code})
        msgs.append({"role": "user", "content": f"[hasil tool read_file]\n{i} " + big_code})
    out = AgentService._compact(msgs, budget=12_000)
    assert sum(len(m["content"]) for m in out) <= 12_000
    assert out[0] == msgs[0] and out[1] == msgs[1]          # system prompt & tugas utuh
    assert out[-1]["content"].startswith("[hasil tool read_file]\n7")  # langkah terbaru tetap ada


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


def test_agent_full_approval_mode_applies_high_risk(client, auth, project, model):
    """Mode izin 'penuh' + task tanpa auto_apply eksplisit: editan risiko TINGGI langsung diterapkan,
    task tidak berhenti di WAITING_APPROVAL."""
    assert client.put("/api/v1/ai/agent-models", json={"approval_mode": "penuh"}, headers=auth).status_code == 200
    try:
        SCRIPT.extend([
            J("write_file", path="deploy.sh", content="echo hai\n"),   # HIGH
            J("finish", summary="ok"),
        ])
        r = client.post("/api/v1/agent/tasks", json={"project_id": project, "description": "buat skrip"}, headers=auth)
        assert r.status_code == 201, r.text
        assert r.json()["auto_apply"] is True  # bawaan mengikuti mode izin
        t = wait_status(client, auth, r.json()["id"], {"COMPLETED", "FAILED", "WAITING_APPROVAL"})
        assert t["status"] == "COMPLETED", t
        root = client.app.state.services.projects.project_dir(project)
        assert (root / "deploy.sh").read_text() == "echo hai\n"
        assert t["report"]["verified"]["files_pending"] == []
    finally:
        client.put("/api/v1/ai/agent-models", json={"approval_mode": "manual"}, headers=auth)


def test_agent_manual_mode_default_waits(client, auth, project, model):
    r = client.post("/api/v1/agent/tasks", json={"project_id": project, "description": "x"}, headers=auth)
    assert r.status_code == 201 and r.json()["auto_apply"] is False
    wait_status(client, auth, r.json()["id"], {"COMPLETED", "FAILED"})


def test_agent_live_progress_visible_while_model_works(client, auth, project, model):
    """Selama model bekerja, GET task menyertakan 'live' (tahap, peran, model); hilang setelah selesai."""
    DELAY["s"] = 1.0
    SCRIPT.extend([J("finish", summary="ok")])
    tid = client.post("/api/v1/agent/tasks", json={"project_id": project, "description": "x"}, headers=auth).json()["id"]
    live = None
    end = time.time() + 10
    while time.time() < end and live is None:
        live = client.get(f"/api/v1/agent/tasks/{tid}", headers=auth).json().get("live")
        time.sleep(0.1)
    assert live and live["model"] == "coder" and live["role"] in ("planner", "executor")
    assert live["phase"] in ("loading", "prompt", "writing") and live["elapsed"] >= 0
    t = wait_status(client, auth, tid, {"COMPLETED", "FAILED"})
    assert t["status"] == "COMPLETED" and t["live"] is None


def test_agent_recovers_from_context_overflow(client, auth, project, model):
    """llama-server menolak (konteks 8192 terlampaui) → riwayat dipangkas & dicoba ulang, task tidak FAILED."""
    SCRIPT.extend([J("list_dir"), J("finish", summary="ok setelah dipangkas")])
    CTX_FAIL["n"] = 1
    tid = client.post("/api/v1/agent/tasks", json={"project_id": project, "description": "cek konteks"},
                      headers=auth).json()["id"]
    t = wait_status(client, auth, tid, {"COMPLETED", "FAILED"})
    assert t["status"] == "COMPLETED", t
    ev = client.get(f"/api/v1/agent/tasks/{tid}/events", headers=auth).json()["events"]
    trims = [e["data"] for e in ev if e["kind"] == "context_trim"]
    assert trims and trims[0]["n_ctx"] == 8192
    assert SEEN[0].get("rejected") and not SEEN[1].get("rejected")


def test_agent_warns_on_repeated_identical_error(client, auth, project, model):
    """Model mengulang panggilan yang sama-sama salah: hasil tool ke-2 memberi PERINGATAN."""
    SCRIPT.extend([J("update_plan"), J("update_plan"),
                   J("update_plan", steps=[{"id": "1", "description": "x", "status": "done"}]), J("finish", summary="ok")])
    tid = client.post("/api/v1/agent/tasks", json={"project_id": project, "description": "rencana"},
                      headers=auth).json()["id"]
    t = wait_status(client, auth, tid, {"COMPLETED", "FAILED"})
    assert t["status"] == "COMPLETED", t
    obs = [e["data"] for e in client.get(f"/api/v1/agent/tasks/{tid}/events", headers=auth).json()["events"]
           if e["kind"] == "observation"]
    assert not obs[0]["ok"] and "PERINGATAN" not in obs[0]["text"]
    assert not obs[1]["ok"] and "PERINGATAN" in obs[1]["text"]
    assert obs[2]["ok"]


def test_write_file_continuation_rejects_tool_call_as_content(client, auth, project, model):
    """Bila model menjawab permintaan isi dengan tool call lagi, JSON itu TIDAK dijadikan isi file."""
    SCRIPT.extend([J("write_file", path="b.css"), J("write_file", path="b.css"),
                   J("write_file", path="b.css") + "\n```css\nbody { margin: 0; }\n```", J("finish", summary="ok")])
    tid = client.post("/api/v1/agent/tasks", json={"project_id": project, "description": "css", "auto_apply": True},
                      headers=auth).json()["id"]
    t = wait_status(client, auth, tid, {"COMPLETED", "FAILED"})
    assert t["status"] == "COMPLETED", t
    root = client.app.state.services.projects.project_dir(project)
    assert (root / "b.css").read_text() == "body { margin: 0; }\n"
    obs = [e["data"] for e in client.get(f"/api/v1/agent/tasks/{tid}/events", headers=auth).json()["events"]
           if e["kind"] == "observation"]
    assert not obs[0]["ok"] and "Contoh persis" in obs[0]["text"]


def test_write_file_without_content_is_requested_without_using_a_step(client, auth, project, model):
    """Model mengirim JSON write_file tanpa isi → server langsung meminta isinya (tidak menghabiskan langkah)."""
    SCRIPT.extend([J("write_file", path="halo.py"), "```python\nprint('halo')\n```",
                   J("update_plan", steps=[{"id": "1", "description": "tulis halo", "status": "done"}]),
                   J("finish", summary="ok")])
    tid = client.post("/api/v1/agent/tasks", json={"project_id": project, "description": "halo", "auto_apply": True},
                      headers=auth).json()["id"]
    t = wait_status(client, auth, tid, {"COMPLETED", "FAILED"})
    assert t["status"] == "COMPLETED", t
    root = client.app.state.services.projects.project_dir(project)
    assert (root / "halo.py").read_text() == "print('halo')\n"
    ev = client.get(f"/api/v1/agent/tasks/{tid}/events", headers=auth).json()["events"]
    assert any(e["kind"] == "continuation" and e["data"]["ok"] for e in ev)
    assert not any(e["kind"] == "observation" and not e["data"]["ok"] for e in ev)
    # 4 balasan model, tetapi hanya write_file & finish yang dihitung (lanjutan isi & update_plan gratis)
    assert t["steps_used"] == 2, t["steps_used"]


def test_default_max_steps_from_settings(client, auth, project, model):
    """'Batas langkah per task' di Model AI → AI Agent menjadi bawaan task baru (dibatasi CS_AGENT_MAX_STEPS)."""
    url = "/api/v1/ai/agent-models"
    try:
        r = client.put(url, json={"max_steps": 45}, headers=auth)
        assert r.status_code == 200, r.text
        assert r.json()["max_steps"] == 45 and r.json()["max_steps_limit"] >= 45
        assert client.put(url, json={"max_steps": 9999}, headers=auth).status_code == 422
        assert client.put(url, json={"max_steps": 500}, headers=auth).json()["max_steps"] == \
            client.app.state.services.settings.agent_max_steps
        client.put(url, json={"max_steps": 45}, headers=auth)
        SCRIPT.extend([J("finish", summary="ok")])
        t = client.post("/api/v1/agent/tasks", json={"project_id": project, "description": "x"}, headers=auth).json()
        assert t["max_steps"] == 45
        wait_status(client, auth, t["id"], {"COMPLETED", "FAILED"})
        SCRIPT.extend([J("finish", summary="ok")])
        t2 = client.post("/api/v1/agent/tasks", json={"project_id": project, "description": "y", "max_steps": 12},
                         headers=auth).json()
        assert t2["max_steps"] == 12  # nilai eksplisit di permintaan tetap dihormati
        wait_status(client, auth, t2["id"], {"COMPLETED", "FAILED"})
    finally:
        client.put(url, json={"max_steps": 30}, headers=auth)
