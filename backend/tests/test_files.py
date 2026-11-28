import os


def test_project_crud(client, auth):
    r = client.post("/api/v1/projects", json={"name": "Proyek C", "language": "c"}, headers=auth)
    assert r.status_code == 201
    pid = r.json()["id"]
    assert any(p["id"] == pid for p in client.get("/api/v1/projects", headers=auth).json())
    r = client.put(f"/api/v1/projects/{pid}", json={"description": "desk"}, headers=auth)
    assert r.json()["description"] == "desk"
    tree = client.get("/api/v1/files/tree", params={"project_id": pid}, headers=auth).json()
    assert [c["name"] for c in tree["children"]] == ["main.c"]
    assert client.delete(f"/api/v1/projects/{pid}", headers=auth).status_code == 200
    assert client.get(f"/api/v1/projects/{pid}", headers=auth).status_code == 404


def test_file_crud_and_history(client, auth, project):
    base = "/api/v1/files"
    r = client.post(f"{base}/create", json={"project_id": project, "path": "src", "type": "folder"}, headers=auth)
    assert r.status_code == 201
    r = client.post(f"{base}/create", json={"project_id": project, "path": "src/a.py", "content": "print(1)\n"}, headers=auth)
    assert r.status_code == 201
    assert client.post(f"{base}/create", json={"project_id": project, "path": "src/a.py"}, headers=auth).status_code == 409
    rd = client.get(f"{base}/read", params={"project_id": project, "path": "src/a.py"}, headers=auth).json()
    assert rd["content"] == "print(1)\n" and rd["language"] == "python"
    # tulis dengan pemeriksaan konflik
    r = client.put(f"{base}/write", json={"project_id": project, "path": "src/a.py", "content": "print(2)\n",
                                          "expected_sha256": rd["sha256"]}, headers=auth)
    assert r.status_code == 200
    r = client.put(f"{base}/write", json={"project_id": project, "path": "src/a.py", "content": "x",
                                          "expected_sha256": rd["sha256"]}, headers=auth)
    assert r.status_code == 409
    hist = client.get(f"{base}/history", params={"project_id": project, "path": "src/a.py"}, headers=auth).json()["history"]
    assert hist and hist[0]["action"] == "write"
    r = client.post(f"{base}/restore", json={"project_id": project, "history_id": hist[0]["id"]}, headers=auth)
    assert r.status_code == 200
    assert client.get(f"{base}/read", params={"project_id": project, "path": "src/a.py"}, headers=auth).json()["content"] == "print(1)\n"
    # rename, copy, move
    assert client.post(f"{base}/rename", json={"project_id": project, "path": "src/a.py", "new_name": "b.py"}, headers=auth).status_code == 200
    assert client.post(f"{base}/copy", json={"project_id": project, "path": "src/b.py", "destination": "c.py"}, headers=auth).status_code == 200
    assert client.post(f"{base}/move", json={"project_id": project, "path": "c.py", "destination": "src"}, headers=auth).status_code == 200
    names = sorted(e["name"] for e in client.get(f"{base}/tree", params={"project_id": project, "path": "src"}, headers=auth).json()["children"])
    assert names == ["b.py", "c.py"]
    # search nama & isi
    assert len(client.get(f"{base}/search", params={"project_id": project, "q": "*.py"}, headers=auth).json()) >= 3
    hits = client.get(f"{base}/search", params={"project_id": project, "q": "print(1)", "content": True}, headers=auth).json()
    assert hits and hits[0]["line"] == 1
    # hapus folder butuh recursive
    assert client.delete(f"{base}/delete", params={"project_id": project, "path": "src"}, headers=auth).status_code == 409
    assert client.delete(f"{base}/delete", params={"project_id": project, "path": "src", "recursive": True}, headers=auth).status_code == 200
    # favorit & recent
    assert client.post(f"{base}/favorites", json={"project_id": project, "path": "main.py"}, headers=auth).status_code == 200
    assert client.get(f"{base}/favorites", headers=auth).json()["files"]


def test_path_traversal_blocked(client, auth, project):
    base = "/api/v1/files"
    for bad in ["../x.py", "a/../../x", "/etc/passwd", "..", "src/../../etc"]:
        r = client.get(f"{base}/read", params={"project_id": project, "path": bad}, headers=auth)
        assert r.status_code in (403, 404), (bad, r.text)
    r = client.post(f"{base}/create", json={"project_id": project, "path": "../escape.txt", "content": "x"}, headers=auth)
    assert r.status_code == 403
    assert client.delete(f"{base}/delete", params={"project_id": project, "path": ""}, headers=auth).status_code == 403


def test_symlink_escape_blocked(client, auth, project):
    from backend.main import app

    root = app.state.services.projects.project_dir(project)
    os.symlink("/etc", root / "etc_link")
    os.symlink("/etc/hostname", root / "host_link")
    r = client.get("/api/v1/files/read", params={"project_id": project, "path": "etc_link/hostname"}, headers=auth)
    assert r.status_code == 403
    r = client.get("/api/v1/files/read", params={"project_id": project, "path": "host_link"}, headers=auth)
    assert r.status_code == 403
    r = client.put("/api/v1/files/write", json={"project_id": project, "path": "host_link", "content": "x"}, headers=auth)
    assert r.status_code == 403
    # menghapus symlink hanya menghapus link-nya
    assert client.delete("/api/v1/files/delete", params={"project_id": project, "path": "host_link"}, headers=auth).status_code == 200
    assert os.path.exists("/etc/hostname")


def test_other_user_cannot_access_project(client, auth, project):
    client.post("/api/v1/auth/users", json={"username": "dev2", "password": "dev2-pass-1", "role": "developer"}, headers=auth)
    tok = client.post("/api/v1/auth/login", json={"username": "dev2", "password": "dev2-pass-1"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/v1/files/tree", params={"project_id": project}, headers=h).status_code == 403


def test_list_files_for_quick_open(client, auth, project):
    for path in ("main.py", "src/app/util.py", "node_modules/x/index.js", ".git/config", ".venv/bin/python"):
        assert client.put("/api/v1/files/write", json={"project_id": project, "path": path, "content": "x"},
                          headers=auth).status_code == 200
    r = client.get("/api/v1/files/list", params={"project_id": project}, headers=auth)
    assert r.status_code == 200, r.text
    files = r.json()["files"]
    assert "main.py" in files and "src/app/util.py" in files
    assert not any(f.startswith(("node_modules/", ".git/", ".venv/")) for f in files), files
    assert r.json()["truncated"] is False


def test_history_keeps_last_versions(client, auth, project):
    svc = client.app.state.services.files
    keep = svc.HISTORY_KEEP
    for i in range(keep + 5):
        assert client.put("/api/v1/files/write", json={"project_id": project, "path": "simpan.txt", "content": f"v{i}"},
                          headers=auth).status_code == 200
    h = client.get("/api/v1/files/history", params={"project_id": project, "path": "simpan.txt"}, headers=auth).json()["history"]
    assert len(h) == keep
    snaps = list((client.app.state.services.settings.history_dir / project).iterdir())
    rows = svc.db.all("SELECT snapshot FROM file_history WHERE project_id=?", (project,))
    assert {p.name for p in snaps} == {r["snapshot"] for r in rows}  # file snapshot lama ikut terhapus


def test_grep_and_replace_all(client, auth, project):
    def put(path, content):
        assert client.put("/api/v1/files/write", json={"project_id": project, "path": path, "content": content},
                          headers=auth).status_code == 200
    put("a.py", "def hitung(x):\n    return x\n\nprint(hitung(2), Hitung)\n")
    put("lib/b.js", "const hitungan = 1; hitung(3);\n")
    put("node_modules/z.js", "hitung()\n")  # dilewati
    g = client.post("/api/v1/files/grep", json={"project_id": project, "query": "hitung", "whole_word": True,
                                                 "case_sensitive": True}, headers=auth).json()
    hits = {(m["path"], m["line"], m["column"]) for m in g["matches"]}
    assert hits == {("a.py", 1, 5), ("a.py", 4, 7), ("lib/b.js", 1, 21)}, hits
    assert g["files"] == 2
    gi = client.post("/api/v1/files/grep", json={"project_id": project, "query": "hitung"}, headers=auth).json()
    assert len(gi["matches"]) == 5  # tanpa whole-word & case: + "hitungan" + "Hitung"
    bad = client.post("/api/v1/files/grep", json={"project_id": project, "query": "(", "regex": True}, headers=auth)
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "bad_regex"
    # ganti (regex dengan grup) hanya di a.py
    r = client.post("/api/v1/files/replace", json={"project_id": project, "query": r"hitung\((\w+)\)", "regex": True,
                                                   "replacement": r"jumlah(\1)", "paths": ["a.py"]}, headers=auth).json()
    assert r == {"files": [{"path": "a.py", "count": 2}], "total": 2}, r
    a = client.get("/api/v1/files/read", params={"project_id": project, "path": "a.py"}, headers=auth).json()["content"]
    assert a == "def jumlah(x):\n    return x\n\nprint(jumlah(2), Hitung)\n"
    # ganti teks biasa: "\1" tidak ditafsirkan sebagai grup
    r = client.post("/api/v1/files/replace", json={"project_id": project, "query": "hitungan", "replacement": r"x\1"},
                    headers=auth).json()
    assert r["total"] == 1
    b = client.get("/api/v1/files/read", params={"project_id": project, "path": "lib/b.js"}, headers=auth).json()["content"]
    assert b.startswith("const x\\1 = 1;")
    h = client.get("/api/v1/files/history", params={"project_id": project, "path": "a.py"}, headers=auth).json()["history"]
    assert any("ganti semua" in x["note"] for x in h)
