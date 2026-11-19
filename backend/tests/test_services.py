import shutil

import pytest


def test_terminal_session(client, auth, token, project):
    r = client.post("/api/v1/terminal/sessions", json={"project_id": project}, headers=auth)
    assert r.status_code == 201, r.text
    sid = r.json()["session_id"]
    got = ""
    with client.websocket_connect(f"/ws/terminal/{sid}?token={token}") as ws:
        ws.send_json({"type": "input", "data": "echo TERM_$((40+2))\n"})
        for _ in range(200):
            ev = ws.receive_json()
            if ev["type"] == "output":
                got += ev["data"]
            if "TERM_42" in got:
                break
        ws.send_json({"type": "resize", "cols": 100, "rows": 30})
    assert "TERM_42" in got
    sessions = client.get("/api/v1/terminal/sessions", headers=auth).json()
    assert any(s["session_id"] == sid for s in sessions)
    assert client.delete(f"/api/v1/terminal/sessions/{sid}", headers=auth).status_code == 200


def test_database_manager(client, auth):
    b = "/api/v1/database"
    assert client.post(f"{b}/create", json={"name": "uji"}, headers=auth).status_code in (201, 409)
    r = client.post(f"{b}/query", json={"database": "uji", "sql": "CREATE TABLE t(id INTEGER PRIMARY KEY, n TEXT);"}, headers=auth)
    assert r.status_code == 400  # mode baca menolak perubahan
    r = client.post(f"{b}/query", json={"database": "uji", "mode": "write",
                                        "sql": "CREATE TABLE IF NOT EXISTS t(id INTEGER PRIMARY KEY, n TEXT); INSERT INTO t(n) VALUES('a'),('b');"}, headers=auth)
    assert r.status_code == 200, r.text
    r = client.post(f"{b}/query", json={"database": "uji", "sql": "SELECT n FROM t ORDER BY id"}, headers=auth).json()
    assert r["results"][0]["rows"][:2] == [["a"], ["b"]]
    r = client.post(f"{b}/query", json={"database": "uji", "mode": "write", "sql": "DELETE FROM t WHERE n='a'"}, headers=auth)
    assert r.status_code == 409 and r.json()["error"]["code"] == "confirmation_required"
    r = client.post(f"{b}/query", json={"database": "uji", "mode": "write", "sql": "DELETE FROM t WHERE n='a'", "confirm": True}, headers=auth)
    assert r.status_code == 200
    sch = client.get(f"{b}/schema", params={"database": "uji"}, headers=auth).json()
    assert any(o["name"] == "t" for o in sch["objects"])
    csv = client.get(f"{b}/export", params={"database": "uji", "table": "t"}, headers=auth).text
    assert csv.startswith("id,n")
    r = client.post(f"{b}/import", json={"database": "uji", "table": "impor", "csv": "a,b\n1,2\n3,4\n"}, headers=auth)
    assert r.json()["inserted"] == 2
    assert client.post(f"{b}/backup", json={"database": "uji"}, headers=auth).status_code == 200
    assert client.post(f"{b}/query", json={"database": "uji", "sql": "ATTACH '/etc/x.db' AS x"}, headers=auth).status_code == 400


@pytest.mark.skipif(not shutil.which("git"), reason="git tidak ada")
def test_git_flow(client, auth, project):
    b = "/api/v1/git"
    assert client.get(f"{b}/status", params={"project_id": project}, headers=auth).status_code == 400
    assert client.post(f"{b}/init", json={"project_id": project}, headers=auth).json()["ok"]
    st = client.get(f"{b}/status", params={"project_id": project}, headers=auth).json()
    assert any(f["path"] == "main.py" for f in st["files"])
    r = client.post(f"{b}/commit", json={"project_id": project, "message": "awal", "add_all": True}, headers=auth).json()
    assert r["ok"], r
    log = client.get(f"{b}/log", params={"project_id": project}, headers=auth).json()["commits"]
    assert log[0]["message"] == "awal"
    assert client.post(f"{b}/branch", json={"project_id": project, "name": "fitur"}, headers=auth).json()["ok"]
    assert client.get(f"{b}/branches", params={"project_id": project}, headers=auth).json()["current"] == "fitur"
    assert client.post(f"{b}/branch", json={"project_id": project, "name": "--bahaya"}, headers=auth).status_code == 400
    client.put("/api/v1/files/write", json={"project_id": project, "path": "main.py", "content": "print('ubah')\n"}, headers=auth)
    d = client.get(f"{b}/diff", params={"project_id": project}, headers=auth).json()
    assert "ubah" in d["stdout"]
    assert client.post(f"{b}/remote", json={"project_id": project, "url": "git@github.com:x/y.git"}, headers=auth).status_code == 400
    assert client.post(f"{b}/remote", json={"project_id": project, "url": "https://github.com/x/y.git"}, headers=auth).json()["ok"]
    r = client.post(f"{b}/credentials", json={"host": "github.com", "username": "u", "token": "ghp_rahasia"}, headers=auth)
    assert r.status_code == 200
    creds = client.get(f"{b}/credentials", headers=auth).json()["credentials"]
    assert creds and "ghp_rahasia" not in str(creds)


@pytest.mark.parametrize("url", ["http://127.0.0.1:8800/", "http://localhost/", "http://169.254.169.254/latest/meta-data",
                                 "http://192.168.1.1/", "http://[::1]/", "file:///etc/passwd"])
def test_http_ssrf_blocked(client, auth, url):
    r = client.post("/api/v1/http/request", json={"method": "GET", "url": url}, headers=auth)
    assert r.status_code in (400, 403), r.text


def test_http_collections(client, auth):
    r = client.post("/api/v1/http/collections", json={"name": "contoh", "method": "GET", "url": "https://example.com"}, headers=auth)
    assert r.status_code == 201
    cols = client.get("/api/v1/http/collections", headers=auth).json()["collections"]
    assert cols[0]["requests"][0]["name"] == "contoh"


def test_system_monitor(client, auth):
    info = client.get("/api/v1/system/info", headers=auth).json()
    assert info["architecture"] and info["cpu_count"] >= 1
    res = client.get("/api/v1/system/resources", headers=auth).json()
    assert 0 <= res["memory"]["percent"] <= 100 and res["disk"]["total"] > 0
    dash = client.get("/api/v1/monitor/dashboard", headers=auth).json()
    assert "resources" in dash


def test_backup_and_restore(client, auth, project):
    client.put("/api/v1/files/write", json={"project_id": project, "path": "main.py", "content": "print('versi1')\n"}, headers=auth)
    r = client.post("/api/v1/backup", json={"label": "uji"}, headers=auth)
    assert r.status_code == 201, r.text
    name = r.json()["name"]
    assert client.get(f"/api/v1/backup/{name}/verify", headers=auth).json()["valid"]
    client.put("/api/v1/files/write", json={"project_id": project, "path": "main.py", "content": "print('rusak')\n"}, headers=auth)
    assert client.post("/api/v1/backup/restore", json={"name": name}, headers=auth).status_code == 409
    r = client.post("/api/v1/backup/restore", json={"name": name, "confirm": True}, headers=auth)
    assert r.status_code == 200, r.text
    c = client.get("/api/v1/files/read", params={"project_id": project, "path": "main.py"}, headers=auth).json()["content"]
    assert c == "print('versi1')\n"


def test_backup_corruption_detected(client, auth, tmp_path):
    from backend.main import app

    svc = app.state.services
    info = svc.backup.create_sync("korup")
    p = svc.backup.path_of(info["name"])
    data = bytearray(p.read_bytes())
    data[len(data) // 2] ^= 0xFF
    p.write_bytes(bytes(data))
    with pytest.raises(Exception):
        svc.backup.verify(info["name"])


def test_ai_proposals(client, auth, project):
    r = client.post("/api/v1/ai/proposals", json={"project_id": project, "path": "ai.py", "content": "print('ai')\n",
                                                  "reason": "contoh"}, headers=auth)
    assert r.status_code == 201
    prop = r.json()
    assert not client.get("/api/v1/files/read", params={"project_id": project, "path": "ai.py"}, headers=auth).status_code == 200
    r = client.post(f"/api/v1/ai/proposals/{prop['id']}/decide", json={"project_id": project, "approve": True}, headers=auth)
    assert r.json()["status"] == "approved"
    assert client.get("/api/v1/files/read", params={"project_id": project, "path": "ai.py"}, headers=auth).json()["content"] == "print('ai')\n"
    st = client.get("/api/v1/ai/status", headers=auth).json()
    assert "terminal" not in st["ai_permissions"]


def test_openapi_contract(client):
    spec = client.get("/openapi.json").json()
    for path in ["/api/v1/auth/login", "/api/v1/projects", "/api/v1/files/tree", "/api/v1/execution/run",
                 "/api/v1/terminal/sessions", "/api/v1/database/query", "/api/v1/git/status", "/api/v1/system/health",
                 "/api/v1/http/request", "/api/v1/backup"]:
        assert path in spec["paths"], path
