"""Peran model agent (perencana/pelaksana/peninjau), eskalasi, dan Uji Model."""
import json
import time

import httpx
import pytest

from backend.services import ai_providers
from backend.services.model_bench import CASES, J

# Antrean balasan per nama model; SEEN mencatat (model, pesan) setiap panggilan chat.
REPLIES: dict[str, list[str]] = {}
SEEN: list[tuple[str, list[dict]]] = []
DEFAULT = '```json\n{"tool": "finish", "args": {"summary": "skrip habis"}}\n```'


async def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/v1/models":
        return httpx.Response(200, json={"data": [{"id": m} for m in ("kecil", "besar", "pintar", "bodoh")]})
    body = json.loads(request.content)
    SEEN.append((body["model"], body["messages"]))
    q = REPLIES.get(body["model"]) or []
    text = q.pop(0) if q else DEFAULT
    chunks = [{"choices": [{"delta": {"content": text}}]},
              {"choices": [], "timings": {"predicted_n": 40, "predicted_per_second": 8.5, "prompt_n": 900}}]
    sse = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse.encode())


@pytest.fixture(autouse=True)
def fake(monkeypatch):
    monkeypatch.setattr(ai_providers, "http_client",
                        lambda timeout=30.0: httpx.AsyncClient(transport=httpx.MockTransport(_handler), timeout=timeout))
    REPLIES.clear()
    SEEN.clear()


@pytest.fixture()
def conn(client, auth):
    r = client.post("/api/v1/ai/connections", json={"name": "multi", "kind": "openai", "location": "local",
                                                    "base_url": "http://multi.test"}, headers=auth)
    cid = r.json()["id"]
    client.post("/api/v1/ai/apply", json={"connection_id": cid, "model": "kecil"}, headers=auth)
    end = time.time() + 10
    while client.get("/api/v1/ai/status", headers=auth).json()["status"] != "ready":
        assert time.time() < end
        time.sleep(0.1)
    yield cid
    client.put("/api/v1/ai/agent-models", json={"planner": None, "executor": None, "reviewer": None, "online": None,
                                                "allow_online": False}, headers=auth)
    client.post("/api/v1/ai/unload", headers=auth)
    client.delete(f"/api/v1/ai/connections/{cid}", headers=auth)


def roles(client, auth, **kw):
    r = client.put("/api/v1/ai/agent-models", json=kw, headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def run_task(client, auth, project, desc="tugas"):
    r = client.post("/api/v1/agent/tasks", json={"project_id": project, "description": desc, "auto_apply": True},
                    headers=auth)
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    end = time.time() + 60
    while time.time() < end:
        t = client.get(f"/api/v1/agent/tasks/{tid}", headers=auth).json()
        if t["status"] in ("COMPLETED", "FAILED", "WAITING_APPROVAL"):
            ev = client.get(f"/api/v1/agent/tasks/{tid}/events", headers=auth).json()["events"]
            return t, ev
        time.sleep(0.1)
    raise AssertionError("task tidak selesai")


PLAN = J("update_plan", steps=[{"id": "1", "description": "kerjakan", "status": "in_progress"}])


def test_agent_models_api(client, auth, conn):
    out = roles(client, auth, planner={"connection_id": conn, "model": "besar"}, max_loaded_models=3)
    assert out["planner"]["model"] == "besar" and out["planner"]["connection_name"] == "multi"
    assert out["executor"] is None and out["default"]["model"] == "kecil" and out["max_loaded_models"] == 3
    assert out["allow_online"] is False
    assert client.put("/api/v1/ai/agent-models", json={"planner": {"connection_id": "tidak-ada", "model": "x"}},
                      headers=auth).status_code == 404
    out = roles(client, auth, planner=None)
    assert out["planner"] is None


def test_planner_then_executor(client, auth, conn, project):
    roles(client, auth, planner={"connection_id": conn, "model": "besar"}, executor={"connection_id": conn, "model": "kecil"})
    REPLIES["besar"] = [J("list_dir"), PLAN]
    REPLIES["kecil"] = [J("finish", summary="beres")]
    t, ev = run_task(client, auth, project)
    assert t["status"] == "COMPLETED", t
    assert [m for m, _ in SEEN] == ["besar", "besar", "kecil"]
    thinking = [e["data"] for e in ev if e["kind"] == "thinking"]
    assert [d["role"] for d in thinking] == ["planner", "planner", "executor"]
    thought = [e["data"] for e in ev if e["kind"] == "thought"]
    assert thought[0]["model"] == "besar" and thought[0]["tps"] == 8.5 and thought[0]["tokens"] == 40


def test_escalation_on_bad_format(client, auth, conn, project):
    roles(client, auth, planner={"connection_id": conn, "model": "besar"}, executor={"connection_id": conn, "model": "kecil"})
    REPLIES["besar"] = [PLAN, J("finish", summary="diambil alih perencana")]
    REPLIES["kecil"] = ["maaf saya bingung", "tetap bingung"]
    t, ev = run_task(client, auth, project)
    assert t["status"] == "COMPLETED", t
    assert [m for m, _ in SEEN] == ["besar", "kecil", "kecil", "besar"]
    esc = [e["data"] for e in ev if e["kind"] == "escalation"]
    assert esc and esc[0]["to_role"] == "planner" and esc[0]["from_model"] == "kecil"


def test_online_escalation_only_when_allowed(client, auth, conn, project):
    # Pelaksana = Perencana (sama), online diatur tapi TIDAK diizinkan -> gagal tanpa memanggil model online.
    roles(client, auth, executor={"connection_id": conn, "model": "kecil"}, online={"connection_id": conn, "model": "pintar"},
          allow_online=False)
    REPLIES["kecil"] = [PLAN, "x", "y", "z"]
    t, _ = run_task(client, auth, project)
    assert t["status"] == "FAILED" and "pintar" not in [m for m, _ in SEEN]
    SEEN.clear()
    roles(client, auth, allow_online=True)
    REPLIES["kecil"] = [PLAN, "x", "y"]
    REPLIES["pintar"] = [J("finish", summary="diselesaikan model online")]
    t, ev = run_task(client, auth, project)
    assert t["status"] == "COMPLETED", t
    assert [m for m, _ in SEEN][-1] == "pintar"
    assert any(e["kind"] == "escalation" and e["data"]["to_role"] == "online" for e in ev)


def test_reviewer_checks_before_finish(client, auth, conn, project):
    roles(client, auth, executor={"connection_id": conn, "model": "kecil"}, reviewer={"connection_id": conn, "model": "besar"})
    REPLIES["kecil"] = [PLAN, J("finish", summary="kayaknya beres"), J("finish", summary="beres setelah dicek")]
    REPLIES["besar"] = [J("list_dir"), J("finish", summary="sudah ditinjau")]
    t, ev = run_task(client, auth, project)
    assert t["status"] == "COMPLETED", t
    # kecil: plan, finish(ditahan) -> besar meninjau: list_dir (belum setuju) -> kecil: finish(ditahan lagi)
    # -> besar: finish (disetujui). Batas peninjauan 2.
    assert [m for m, _ in SEEN] == ["kecil", "kecil", "besar", "kecil", "besar"]
    assert any("[peninjau]" in m["content"] for m in SEEN[2][1])
    reviews = [e["data"] for e in ev if e["kind"] == "review"]
    assert [r["approved"] for r in reviews] == [False, True]
    assert t["report"]["ai_generated"]["summary"] == "sudah ditinjau"


GOOD = {
    "langkah_pertama": J("read_file", path="calc.py"),
    "rencana": J("update_plan", steps=[{"id": "1", "description": "perbaiki add"}, {"id": "2", "description": "uji"}]),
    "perbaiki_bug": J("edit_file", path="calc.py", search="def add(a, b):\n    return a - b",
                      replace="def add(a, b):\n    return a + b"),
    "tulis_fungsi": J("write_file", path="teks_util.py") + "\n```python\nimport re\n\n\ndef is_palindrome(s):\n"
                    "    t = re.sub(r'[^0-9a-z]', '', s.lower())\n    return t == t[::-1]\n\n\n"
                    "def word_count(s):\n    return len(s.split())\n```",
    "perbaiki_error": J("edit_file", path="stats.py") + "\n```\n<<<<<<< SEARCH\n    return sum(xs) / len(xs)\n=======\n"
                      "    return sum(xs) / len(xs) if xs else 0.0\n>>>>>>> REPLACE\n```",
    "jujur": J("read_file", path="calc.py"),
}


def wait_bench(client, auth, rid):
    end = time.time() + 60
    while time.time() < end:
        r = client.get(f"/api/v1/ai/bench/{rid}", headers=auth).json()
        if r["status"] not in ("PENDING", "RUNNING"):
            return r
        time.sleep(0.1)
    raise AssertionError("uji model tidak selesai")


def test_model_bench(client, auth, conn):
    REPLIES["pintar"] = [GOOD[c.id] for c in CASES]
    # jawaban "nakal" untuk kasus kode: edit menyasar 'return a - b' (muncul 2x) & mengaku selesai saat tes gagal
    REPLIES["bodoh"] = ["halo!", J("read_file", path="calc.py"),
                        J("edit_file", path="calc.py", search="    return a - b", replace="    return a + b"),
                        "tidak tahu", "tidak tahu", J("finish", summary="semua beres")]
    r = client.post("/api/v1/ai/bench", json={"targets": [{"connection_id": conn, "model": "pintar"},
                                                         {"connection_id": conn, "model": "bodoh"}]}, headers=auth)
    assert r.status_code == 201, r.text
    ids = [x["id"] for x in r.json()["runs"]]
    good, bad = wait_bench(client, auth, ids[0]), wait_bench(client, auth, ids[1])
    assert good["status"] == "COMPLETED", good
    notes = {x["id"]: x["note"] for x in good["results"]}
    assert good["summary"]["score"] == 100.0, notes
    assert good["summary"]["format_ok"] == len(CASES) and good["summary"]["avg_tps"] == 8.5
    res = {x["id"]: x for x in bad["results"]}
    assert bad["summary"]["score"] < 40
    assert not res["langkah_pertama"]["format_ok"]
    assert res["perbaiki_bug"]["score"] < 1 and "lebih dari sekali" in res["perbaiki_bug"]["note"]
    assert res["jujur"]["score"] == 0.0
    data = client.get("/api/v1/ai/bench", headers=auth).json()
    assert data["leaderboard"][0]["model"] == "pintar" and len(data["cases"]) == len(CASES)
    assert data["recommendation"]["planner"]["model"] == "pintar"
    for rid in ids:
        assert client.delete(f"/api/v1/ai/bench/{rid}", headers=auth).status_code == 200


# ---------------- pemuat model llama-server (mode router) ----------------
ROUTER: dict[str, str] = {}   # model -> unloaded|loading|loaded
ROUTER_LOG: list[str] = []


async def _router(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/v1/models":
        return httpx.Response(200, json={"data": [{"id": m, "status": {"value": st}} for m, st in ROUTER.items()]})
    if path in ("/models/load", "/models/unload"):
        m = json.loads(request.content)["model"]
        ROUTER[m] = "loaded" if path.endswith("load") and "unload" not in path else "unloaded"
        ROUTER_LOG.append(f"{path.rsplit('/', 1)[1]}:{m}")
        return httpx.Response(200, json={"success": True})
    return await _handler(request)


def test_router_acquire_respects_memory_limit(client, auth, monkeypatch):
    import asyncio

    monkeypatch.setattr(ai_providers, "http_client",
                        lambda timeout=30.0: httpx.AsyncClient(transport=httpx.MockTransport(_router), timeout=timeout))
    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)
    ROUTER.clear(); ROUTER.update({"a": "unloaded", "b": "unloaded", "c": "unloaded"}); ROUTER_LOG.clear()
    cid = client.post("/api/v1/ai/connections", json={"name": "router", "kind": "llama_router", "location": "local",
                                                      "base_url": "http://router.test"}, headers=auth).json()["id"]
    try:
        roles(client, auth, max_loaded_models=2)
        ai = client.app.state.services.ai

        def acq(m):
            return client.portal.call(ai.acquire, cid, m) if hasattr(client, "portal") else asyncio.run(ai.acquire(cid, m))

        acq("a"); acq("b")
        assert ROUTER["a"] == ROUTER["b"] == "loaded" and ROUTER_LOG == ["load:a", "load:b"]
        acq("c")  # batas 2 -> model paling lama tidak dipakai (a) dibongkar dulu
        assert ROUTER_LOG[-2:] == ["unload:a", "load:c"] and ROUTER["b"] == "loaded"
        acq("b")  # sudah termuat: tidak memuat ulang
        assert ROUTER_LOG[-1] == "load:c"
    finally:
        ai._agent_loaded.clear()
        roles(client, auth, max_loaded_models=2)
        client.delete(f"/api/v1/ai/connections/{cid}", headers=auth)


_real_sleep = __import__("asyncio").sleep


async def _fast_sleep(delay, *a, **kw):
    return await _real_sleep(0)
