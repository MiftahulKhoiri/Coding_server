"""Instal dependensi proyek (install_deps): rencana, validasi paket, venv proyek dipakai saat run."""
from pathlib import Path

import pytest

from backend.core.exceptions import AppError
from backend.services import deps_install

from .conftest import wait_job


def _write(client, auth, pid, path, content):
    r = client.post("/api/v1/files/create", json={"project_id": pid, "path": path, "type": "file", "content": content},
                    headers=auth)
    assert r.status_code in (200, 201), r.text


@pytest.mark.parametrize("pkg", ["flask", "requests>=2,<3", "streamlit==1.28.0", "uvicorn[standard]",
                                 "@types/node", "lodash@4.17.21", "github.com/gin-gonic/gin"])
def test_valid_packages(pkg):
    assert deps_install.check_packages([pkg]) == [pkg]


@pytest.mark.parametrize("pkg", ["-r", "--index-url=http://x", "./lokal", "/etc/passwd", "git+https://x/y",
                                 "a b", "../x", "", "x" * 101])
def test_rejected_packages(pkg):
    with pytest.raises(AppError):
        deps_install.check_packages([pkg])


def test_plan_python_creates_venv_step(tmp_path: Path):
    (tmp_path / "requirements.txt").write_text("flask\n")
    pl = deps_install.plan(tmp_path, tmp_path / "cache")
    assert [p.kind for p in pl] == ["python"]
    cmds = pl[0].commands
    assert cmds[0][0][1:3] == ["-m", "venv"]
    assert cmds[1][0][-2:] == ["-r", "requirements.txt"] and cmds[1][0][0].endswith(".venv/bin/python")
    assert "PIP_CACHE_DIR" in cmds[1][1]


def test_plan_without_manifest(tmp_path: Path):
    with pytest.raises(AppError) as e:
        deps_install.plan(tmp_path, tmp_path / "cache")
    assert e.value.code == "no_manifest"
    # hanya packages → tebak python
    assert deps_install.plan(tmp_path, tmp_path / "c", packages=["rich"])[0].kind == "python"


def test_install_endpoint_and_venv_used(client, auth, project):
    # requirements kosong: tidak butuh internet, tapi .venv tetap dibuat
    _write(client, auth, project, "requirements.txt", "# kosong\n")
    _write(client, auth, project, "cek.py", "import sys\nprint('PREFIX', sys.prefix)\n")
    plan = client.get(f"/api/v1/execution/install?project_id={project}", headers=auth).json()
    assert plan["kinds"] == ["python"] and plan["venv"] is None
    r = client.post("/api/v1/execution/install", json={"project_id": project}, headers=auth)
    assert r.status_code == 202, r.text
    job = wait_job(client, auth, r.json()["process_id"], timeout=300)
    assert job["status"] == "COMPLETED", job
    assert client.get(f"/api/v1/execution/install?project_id={project}", headers=auth).json()["venv"] == ".venv/bin/python"
    r = client.post("/api/v1/execution/run", json={"project_id": project, "path": "cek.py"}, headers=auth)
    out = wait_job(client, auth, r.json()["process_id"])
    assert out["status"] == "COMPLETED", out
    assert out["stdout"].strip().endswith("/.venv"), out["stdout"]


def test_install_rejects_bad_package(client, auth, project):
    r = client.post("/api/v1/execution/install", json={"project_id": project, "packages": ["--index-url=x"]},
                    headers=auth)
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_packages"


def test_agent_tool_registered():
    from backend.services import agent_tools

    t = agent_tools.TOOLS["install_deps"]
    assert t.perm == "execute" and "packages" in t.args
