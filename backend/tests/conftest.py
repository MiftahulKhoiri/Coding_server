import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="cs_test_"))
os.environ.setdefault("CS_WORKSPACE_DIR", str(_TMP / "workspace"))
os.environ.setdefault("CS_LOGS_DIR", str(_TMP / "logs"))
os.environ.setdefault("CS_BACKUPS_DIR", str(_TMP / "backups"))
os.environ.setdefault("CS_ADMIN_PASSWORD", "admin-pass-123")
os.environ.setdefault("CS_RUN_TIMEOUT", "20")
os.environ.setdefault("CS_MIN_FREE_MEMORY_MB", "64")

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def token(client):
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin-pass-123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def project(client, auth):
    r = client.post("/api/v1/projects", json={"name": "uji", "language": "python"}, headers=auth)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    yield pid
    client.delete(f"/api/v1/projects/{pid}", headers=auth)


def wait_job(client, auth, pid, timeout=180):
    import time

    end = time.time() + timeout
    while time.time() < end:
        r = client.get(f"/api/v1/execution/{pid}", headers=auth)
        if r.json()["status"] in ("COMPLETED", "FAILED", "TIMEOUT", "CANCELLED"):
            return r.json()
        time.sleep(0.2)
    raise AssertionError("job tidak selesai")
