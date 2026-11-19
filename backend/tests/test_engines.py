import pytest

from backend.engines.registry import get_registry
from backend.tests.conftest import wait_job

PROGRAMS = {
    "python": ("main.py", 'import sys\nprint("hasil", sum(range(10)))\nprint("err", file=sys.stderr)\n', "hasil 45"),
    "javascript": ("main.js", 'console.log("hasil", [1,2,3].reduce((a,b)=>a+b));\n', "hasil 6"),
    "php": ("main.php", '<?php echo "hasil " . array_sum([1,2,3]) . "\\n";', "hasil 6"),
    "go": ("main.go", 'package main\nimport "fmt"\nfunc main(){ fmt.Println("hasil", 7*6) }\n', "hasil 42"),
    "c": ("main.c", '#include <stdio.h>\nint main(void){ printf("hasil %d\\n", 6*7); return 0; }\n', "hasil 42"),
    "cpp": ("main.cpp", '#include <iostream>\nint main(){ std::cout << "hasil " << 6*7 << std::endl; }\n', "hasil 42"),
    "java": ("Main.java", 'public class Main { public static void main(String[] a){ System.out.println("hasil " + (6*7)); } }\n', "hasil 42"),
    "csharp": ("Program.cs", 'Console.WriteLine("hasil " + (6*7));\n', "hasil 42"),
    "sql": ("q.sql", "CREATE TABLE t(x INTEGER);\nINSERT INTO t VALUES (42);\nSELECT x AS hasil FROM t;\n", "42"),
    "shell": ("main.sh", 'echo "hasil $((6*7))"\n', "hasil 42"),
}
ERRORS = {
    "python": ("bad.py", "print(\n"),
    "c": ("bad.c", "int main( { return 0 }\n"),
    "cpp": ("bad.cpp", "int main( { return 0 }\n"),
    "java": ("Bad.java", "public class Bad { void x( }\n"),
    "go": ("bad.go", "package main\nfunc main( {}\n"),
    "javascript": ("bad.js", "function (\n"),
}


def test_engine_statuses_are_real(client, auth):
    r = client.get("/api/v1/system/engines", params={"refresh": True}, headers=auth).json()["engines"]
    ids = {e["engine_id"]: e for e in r}
    for lang in ["python", "javascript", "php", "go", "c", "cpp", "java", "csharp", "sql", "web", "shell"]:
        assert lang in ids
        assert ids[lang]["status"] in ("AVAILABLE", "NOT_INSTALLED", "ERROR")
    assert ids["python"]["status"] == "AVAILABLE"


def available(lang):
    return get_registry().get(lang).get_status()["status"] == "AVAILABLE"


@pytest.mark.parametrize("lang", list(PROGRAMS))
def test_run_language(client, auth, project, lang):
    if not available(lang):
        pytest.skip(f"{lang} NOT_INSTALLED di mesin ini")
    fname, code, expect = PROGRAMS[lang]
    client.post("/api/v1/files/create", json={"project_id": project, "path": f"{lang}/{fname}", "content": code}, headers=auth)
    r = client.post("/api/v1/execution/run", json={"project_id": project, "path": f"{lang}/{fname}"}, headers=auth)
    assert r.status_code == 202, r.text
    job = wait_job(client, auth, r.json()["process_id"])
    assert job["status"] == "COMPLETED", job
    assert job["exit_code"] == 0
    assert expect in job["stdout"], job
    assert "An issue was encountered" not in job["stdout"]


@pytest.mark.parametrize("lang", list(ERRORS))
def test_compile_error(client, auth, project, lang):
    if not available(lang):
        pytest.skip(f"{lang} NOT_INSTALLED")
    fname, code = ERRORS[lang]
    client.post("/api/v1/files/create", json={"project_id": project, "path": f"err_{lang}/{fname}", "content": code}, headers=auth)
    r = client.post("/api/v1/execution/build", json={"project_id": project, "path": f"err_{lang}/{fname}"}, headers=auth)
    job = wait_job(client, auth, r.json()["process_id"])
    assert job["status"] == "FAILED"
    assert job["exit_code"] != 0
    assert job["stderr"] or job["stdout"]


def test_stdin_and_args(client, auth, project):
    client.post("/api/v1/files/create", json={"project_id": project, "path": "io.py",
                                              "content": "import sys\nprint(sys.argv[1:], input())\n"}, headers=auth)
    r = client.post("/api/v1/execution/run", json={"project_id": project, "path": "io.py", "args": ["a", "b c"],
                                                   "stdin": "halo\n"}, headers=auth)
    job = wait_job(client, auth, r.json()["process_id"])
    assert "['a', 'b c'] halo" in job["stdout"]


def test_timeout(client, auth, project):
    client.post("/api/v1/files/create", json={"project_id": project, "path": "slow.py",
                                              "content": "import time\nwhile True: time.sleep(1)\n"}, headers=auth)
    r = client.post("/api/v1/execution/run", json={"project_id": project, "path": "slow.py", "timeout": 2}, headers=auth)
    job = wait_job(client, auth, r.json()["process_id"], timeout=30)
    assert job["status"] == "TIMEOUT"


def test_cancel(client, auth, project):
    import time

    client.post("/api/v1/files/create", json={"project_id": project, "path": "loop.py",
                                              "content": "import time\nprint('mulai', flush=True)\nwhile True: time.sleep(0.1)\n"}, headers=auth)
    r = client.post("/api/v1/execution/run", json={"project_id": project, "path": "loop.py"}, headers=auth)
    pid = r.json()["process_id"]
    for _ in range(50):
        if client.get(f"/api/v1/execution/{pid}", headers=auth).json()["status"] == "RUNNING":
            break
        time.sleep(0.1)
    time.sleep(0.5)
    client.post(f"/api/v1/execution/{pid}/stop", headers=auth)
    job = wait_job(client, auth, pid, timeout=20)
    assert job["status"] == "CANCELLED"


def test_memory_limit(client, auth, project):
    client.post("/api/v1/files/create", json={"project_id": project, "path": "mem.py",
                                              "content": "x = bytearray(3 * 1024 * 1024 * 1024)\nprint('tidak boleh sampai sini')\n"}, headers=auth)
    r = client.post("/api/v1/execution/run", json={"project_id": project, "path": "mem.py"}, headers=auth)
    job = wait_job(client, auth, r.json()["process_id"])
    assert job["status"] == "FAILED"
    assert "tidak boleh" not in job["stdout"]


def test_output_streaming_ws(client, auth, token, project):
    client.post("/api/v1/files/create", json={"project_id": project, "path": "stream.py",
                                              "content": "for i in range(3): print('baris', i, flush=True)\n"}, headers=auth)
    r = client.post("/api/v1/execution/run", json={"project_id": project, "path": "stream.py"}, headers=auth)
    pid = r.json()["process_id"]
    out, statuses = "", []
    with client.websocket_connect(f"/ws/execution/{pid}?token={token}") as ws:
        while True:
            ev = ws.receive_json()
            if ev["type"] == "stdout":
                out += ev["data"]
            if ev["type"] == "status":
                statuses.append(ev["status"])
            if ev["type"] == "end":
                break
    assert "baris 2" in out
    assert statuses[-1] == "COMPLETED"


def test_web_preview(client, auth):
    r = client.post("/api/v1/projects", json={"name": "web", "language": "web"}, headers=auth)
    pid = r.json()["id"]
    r = client.post("/api/v1/execution/run", json={"project_id": pid, "path": "index.html"}, headers=auth)
    job = wait_job(client, auth, r.json()["process_id"])
    assert job["status"] == "COMPLETED" and job["preview_path"] == "index.html"
    url = client.post("/api/v1/preview/token", params={"project_id": pid}, headers=auth).json()["url"]
    page = client.get(url)
    assert page.status_code == 200 and "Halo dari CODING_SERVER" in page.text
    css = client.get(url.replace("index.html", "style.css"))
    assert css.status_code == 200 and "text/css" in css.headers["content-type"]
    assert client.get(url.replace("index.html", "../../etc/passwd")).status_code in (401, 403, 404)
