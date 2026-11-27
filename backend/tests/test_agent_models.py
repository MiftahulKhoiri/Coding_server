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
BODIES: list[dict] = []
DEFAULT = '```json\n{"tool": "finish", "args": {"summary": "skrip habis"}}\n```'


async def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/v1/models":
        return httpx.Response(200, json={"data": [{"id": m} for m in ("kecil", "besar", "pintar", "bodoh",
                                                                       "Qwen3.5-uji", "Llama-uji")]})
    body = json.loads(request.content)
    SEEN.append((body["model"], body["messages"]))
    BODIES.append(body)
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
    BODIES.clear()


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
        time.sleep(0.25)
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
        time.sleep(0.25)
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
    texts = [e["text"] for e in good["log"]]
    assert any("Kasus 1/6" in t for t in texts) and any("sandbox" in t for t in texts)
    assert any(t.startswith("🏁 Selesai: skor 100") for t in texts) and good["live"] is None
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


def test_unload_refused_while_model_in_use(client, auth, conn):
    ai = client.app.state.services.ai
    ai.hold(conn, "kecil")  # mis. Uji Model / agent sedang memakai model chat aktif
    try:
        r = client.post("/api/v1/ai/unload", headers=auth)
        assert r.status_code == 409 and r.json()["error"]["code"] == "model_in_use", r.text
    finally:
        ai.release(conn, "kecil")
    assert client.post("/api/v1/ai/unload", headers=auth).status_code == 200



# ---------------- profil model & kalibrasi ----------------
def test_profile_defaults_and_options(client):
    from backend.services.model_profiles import family_of

    prof = client.app.state.services.ai.profiles
    q = prof.default("Qwen3.5-9B-Q4_K_M")
    assert q["family"] == "qwen3.5" and q["thinking_supported"] is True
    assert q["preset"]["kualitas"]["thinking"] is True and q["preset"]["kualitas"]["temperature"] == 0.6
    assert q["preset"]["cepat"]["thinking"] is False and q["preset"]["cepat"]["top_p"] == 0.8
    assert family_of("Qwen3_1.7B.Q4_K_M")["family"] == "qwen3"
    assert family_of("Qwen2.5-Coder-7B-Instruct-Q4_K_M")["family"] == "qwen2.5-coder"
    assert family_of("gemma-4-E4B-it-Q4_K_M")["family"] == "gemma-4"
    llama = prof.variants("Llama-3.2-3B-Instruct-Q4_K_M")
    assert [v["params"]["thinking"] for v in llama] == [None, None, None] and len(llama) == 3
    qv = prof.variants("Qwen3.5-9B-Q4_K_M")
    assert [v["params"]["thinking"] for v in qv] == [True, False, False] and qv[2]["params"]["temperature"] == 0.2
    local = prof.options_from({"location": "local", "kind": "llama_router"}, q["preset"]["kualitas"], True)
    assert local["extra"]["chat_template_kwargs"] == {"enable_thinking": True} and local["extra"]["top_k"] == 20
    online = prof.options_from({"location": "online", "kind": "openai"}, q["preset"]["kualitas"], True)
    assert online["extra"] == {"top_p": 0.95}  # API online tidak dikirimi parameter khusus llama-server


def test_calibration_saves_good_profile(client, auth, conn):
    import pathlib

    REPLIES["Qwen3.5-uji"] = [GOOD[c.id] for c in CASES] * 3
    r = client.post("/api/v1/ai/bench", json={"targets": [{"connection_id": conn, "model": "Qwen3.5-uji"}],
                                             "mode": "kalibrasi"}, headers=auth)
    assert r.status_code == 201, r.text
    run = wait_bench(client, auth, r.json()["runs"][0]["id"])
    assert run["status"] == "COMPLETED" and run["mode"] == "kalibrasi", run
    assert len(run["variants"]) == 3 and run["done_cases"] == run["total_cases"] == 3 * len(CASES)
    assert run["profile_decision"]["saved"] is True and run["profile_decision"]["status"] == "ok"
    # varian A mengirim berpikir ON, varian B/C OFF (kontrol thinking per permintaan llama-server)
    kw = [b.get("chat_template_kwargs") for b in BODIES]
    assert kw[0] == {"enable_thinking": True} and kw[-1] == {"enable_thinking": False}
    assert BODIES[-1]["temperature"] == 0.2
    p = client.get("/api/v1/ai/profiles/item", params={"model": "Qwen3.5-uji"}, headers=auth).json()
    assert p["source"] == "kalibrasi" and "perencana" in p["kegunaan"] and "pelaksana_coding" in p["kegunaan"]
    assert p["kalibrasi"]["pilihan"]["kualitas"] in "ABC" and len(p["kalibrasi"]["varian"]) == 3
    assert p["sync"]["status"] == "tidak_aktif"  # tes: sinkron GitHub dimatikan
    f = pathlib.Path(client.app.state.services.settings.model_profiles_dir) / p["file"]
    data = json.loads(f.read_text())
    assert data["model"] == "Qwen3.5-uji" and data["kegunaan_label"]
    listed = client.get("/api/v1/ai/profiles", headers=auth).json()
    assert any(x["model"] == "Qwen3.5-uji" and x["source"] == "kalibrasi" for x in listed["profiles"])
    assert {x["key"] for x in listed["purposes"]} >= {"perencana", "pelaksana_coding", "penjelasan_coding"}
    client.delete("/api/v1/ai/profiles/item", params={"model": "Qwen3.5-uji"}, headers=auth)
    client.delete(f"/api/v1/ai/bench/{run['id']}", headers=auth)


def test_calibration_bad_result_needs_tuning(client, auth, conn):
    REPLIES["Llama-uji"] = ["tidak tahu"] * 18
    r = client.post("/api/v1/ai/bench", json={"targets": [{"connection_id": conn, "model": "Llama-uji"}],
                                             "mode": "kalibrasi"}, headers=auth)
    run = wait_bench(client, auth, r.json()["runs"][0]["id"])
    d = run["profile_decision"]
    assert d["saved"] is False and d["status"] == "perlu_penyesuaian" and d["saran"], d
    assert client.get("/api/v1/ai/profiles/item", params={"model": "Llama-uji"}, headers=auth).json()["source"] == "bawaan"
    # pengguna tetap boleh menyimpan draf
    saved = client.post(f"/api/v1/ai/bench/{run['id']}/save-profile", headers=auth).json()
    assert saved["source"] == "kalibrasi" and saved["status"] == "perlu_penyesuaian"
    client.delete("/api/v1/ai/profiles/item", params={"model": "Llama-uji"}, headers=auth)
    client.delete(f"/api/v1/ai/bench/{run['id']}", headers=auth)


def test_profile_manual_edit_import_and_agent_use(client, auth, conn, project):
    body = {"kegunaan": ["pelaksana_coding", "bukan-kegunaan"], "catatan": "cepat untuk edit kecil",
            "prompt_tambahan": "Selalu sertakan nama fungsi di SEARCH.",
            "cepat": {"temperature": 0.33, "top_p": 0.7, "max_tokens": 1024},
            "kualitas": {"temperature": 0.44, "top_p": 0.9, "max_tokens": 3000}}
    p = client.put("/api/v1/ai/profiles/item", params={"model": "kecil"}, json=body, headers=auth).json()
    assert p["source"] == "manual" and p["kegunaan"] == ["pelaksana_coding"]
    # agent: Perencana (preset kualitas) lalu Pelaksana (preset cepat) + prompt tambahan di system prompt
    roles(client, auth, planner={"connection_id": conn, "model": "kecil"}, executor={"connection_id": conn, "model": "kecil"})
    REPLIES["kecil"] = [PLAN, J("finish", summary="beres")]
    t, ev = run_task(client, auth, project)
    assert t["status"] == "COMPLETED", t
    assert [b["temperature"] for b in BODIES] == [0.44, 0.33] and BODIES[1]["max_tokens"] == 1024
    assert "Selalu sertakan nama fungsi" in BODIES[0]["messages"][0]["content"]
    thought = [e["data"] for e in ev if e["kind"] == "thought"]
    assert [d["profile"] for d in thought] == ["kualitas", "cepat"]
    # profil nonaktif -> perilaku lama
    client.put("/api/v1/ai/profiles/item", params={"model": "kecil"}, json={"active": False}, headers=auth)
    BODIES.clear()
    REPLIES["kecil"] = [PLAN, J("finish", summary="beres")]
    run_task(client, auth, project)
    assert BODIES[0]["temperature"] <= 0.4 and "top_p" not in BODIES[0]
    # ekspor -> reset -> impor
    exported = client.get("/api/v1/ai/profiles/item", params={"model": "kecil"}, headers=auth).json()
    assert client.delete("/api/v1/ai/profiles/item", params={"model": "kecil"}, headers=auth).json()["source"] == "bawaan"
    imp = client.post("/api/v1/ai/profiles/import", json={"profile": exported}, headers=auth).json()
    assert imp["source"] == "impor" and imp["preset"]["cepat"]["temperature"] == 0.33
    client.delete("/api/v1/ai/profiles/item", params={"model": "kecil"}, headers=auth)


def test_profile_git_sync_commits_only_profile_file(client, tmp_path):
    """Sinkron: commit HANYA file profil lalu push; file lain yang sedang diubah tidak ikut ter-commit."""
    import subprocess
    import types

    from backend.services.model_profiles import ModelProfiles

    def git(*a, cwd):
        return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout

    remote, repo = tmp_path / "remote.git", tmp_path / "repo"
    git("init", "-q", "--bare", "-b", "main", str(remote), cwd=tmp_path)
    git("clone", "-q", str(remote), str(repo), cwd=tmp_path)
    git("config", "user.email", "t@t", cwd=repo); git("config", "user.name", "t", cwd=repo)
    (repo / "kode.py").write_text("a = 1\n"); git("add", ".", cwd=repo); git("commit", "-qm", "awal", cwd=repo)
    git("push", "-q", "origin", "HEAD:main", cwd=repo)
    (repo / "kode.py").write_text("a = 2  # perubahan lain yang belum di-commit\n")
    settings = types.SimpleNamespace(base_dir=repo, model_profiles_dir=repo / "model_profiles", model_profiles_git=True)
    prof = ModelProfiles(settings, client.app.state.services.db)

    async def go():
        p = prof.default("Qwen3.5-9B-Q4_K_M")
        prof.save(p, "manual", sync=False)
        return await prof.sync("Qwen3.5-9B-Q4_K_M", "uji sinkron")

    st = client.portal.call(go)  # jalankan di event loop server tes (bukan asyncio.run di thread utama)
    assert st["status"] == "ok", st
    files = git("show", "--name-only", "--format=%s", "main", cwd=remote)
    assert "chore(model-profiles): uji sinkron" in files and "model_profiles/Qwen3.5-9B-Q4_K_M.json" in files
    assert "kode.py" not in files  # perubahan lain tidak ikut
    assert "a = 2" in (repo / "kode.py").read_text()  # dan tetap ada di working tree


async def _router_only(request: httpx.Request) -> httpx.Response:
    if request.url.host != "router.test" and request.url.path == "/v1/models":
        return httpx.Response(200, json={"data": []})  # koneksi lokal lain (bawaan) tidak memuat apa pun
    return await _router(request)


def test_unload_all_skips_models_in_use(client, auth, monkeypatch):
    import asyncio

    monkeypatch.setattr(ai_providers, "http_client",
                        lambda timeout=30.0: httpx.AsyncClient(transport=httpx.MockTransport(_router_only), timeout=timeout))
    monkeypatch.setattr(asyncio, "sleep", _fast_sleep)
    ROUTER.clear(); ROUTER.update({"a": "loaded", "b": "loaded", "c": "unloaded"}); ROUTER_LOG.clear()
    cid = client.post("/api/v1/ai/connections", json={"name": "router", "kind": "llama_router", "location": "local",
                                                      "base_url": "http://router.test"}, headers=auth).json()["id"]
    ai = client.app.state.services.ai
    ai.hold(cid, "b")  # mis. sedang dipakai task agent
    try:
        r = client.post("/api/v1/ai/unload-all", headers=auth)
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["unloaded"] == ["a"] and out["skipped"] == ["b"] and out["errors"] == []
        assert ROUTER == {"a": "unloaded", "b": "loaded", "c": "unloaded"}
    finally:
        ai.release(cid, "b")
        ai._agent_loaded.clear()
        client.delete(f"/api/v1/ai/connections/{cid}", headers=auth)


def test_approval_mode_setting(client, auth):
    assert client.get("/api/v1/ai/agent-models", headers=auth).json()["approval_mode"] == "manual"
    assert client.put("/api/v1/ai/agent-models", json={"approval_mode": "bebas"}, headers=auth).status_code == 422
    try:
        assert roles(client, auth, approval_mode="penuh")["approval_mode"] == "penuh"
    finally:
        roles(client, auth, approval_mode="manual")
