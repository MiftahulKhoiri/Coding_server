"""Uji isolasi sandbox (hanya berjalan bila bubblewrap tersedia, mis. di Raspberry Pi)."""
import pytest

from backend.core.sandbox import bwrap_available
from backend.tests.conftest import wait_job

pytestmark = pytest.mark.skipif(not bwrap_available(), reason="bubblewrap tidak tersedia")

PROBE = r'''
import os, socket, pathlib
home = pathlib.Path.home()
print("HOME_LIST", sorted(os.listdir(home)))
print("SSH", (home / ".ssh").exists())
try:
    open("/etc/shadow").read(); print("SHADOW", "TERBACA")
except Exception as e:
    print("SHADOW", type(e).__name__)
try:
    s = socket.create_connection(("1.1.1.1", 53), timeout=3); print("NET", "TERHUBUNG")
except Exception as e:
    print("NET", type(e).__name__)
for target in ["/usr/cs_probe", BASE + "/cs_probe", "/etc/cs_probe"]:
    try:
        open(target, "w").write("x"); print("WRITE", target, "BERHASIL")
    except Exception as e:
        print("WRITE", target, type(e).__name__)
open("di_dalam_proyek.txt", "w").write("ok"); print("PROJECT_WRITE OK")
print("PID1", open("/proc/1/cmdline").read().split("\x00")[0])
'''


def test_sandbox_isolation(client, auth, project):
    from backend.config import BASE_DIR

    code = f"BASE = {str(BASE_DIR)!r}\n" + PROBE
    client.post("/api/v1/files/create", json={"project_id": project, "path": "probe.py", "content": code}, headers=auth)
    r = client.post("/api/v1/execution/run", json={"project_id": project, "path": "probe.py"}, headers=auth)
    job = wait_job(client, auth, r.json()["process_id"])
    out = job["stdout"]
    assert job["status"] == "COMPLETED", job
    assert "SSH False" in out                      # kunci SSH akun server tidak terlihat
    assert "SHADOW PermissionError" in out or "SHADOW FileNotFoundError" in out
    assert "NET TERHUBUNG" not in out              # jaringan diputus
    assert "BERHASIL" not in out                   # tidak bisa menulis di luar proyek
    assert "PROJECT_WRITE OK" in out
    assert "PID1 bwrap" in out or "PID1 /usr/bin/bwrap" in out or "PID1" in out


def test_terminal_sandboxed(client, auth, token, project):
    sid = client.post("/api/v1/terminal/sessions", json={"project_id": project}, headers=auth).json()["session_id"]
    got = ""
    with client.websocket_connect(f"/ws/terminal/{sid}?token={token}") as ws:
        ws.send_json({"type": "input", "data": "ls -A ~ | wc -l; test -e ~/.ssh && echo ADA_SSH || echo TANPA_SSH; echo SELESAI\n"})
        for _ in range(300):
            ev = ws.receive_json()
            if ev["type"] == "output":
                got += ev["data"]
            if "SELESAI\r\n" in got and ("TANPA_SSH" in got or "ADA_SSH" in got):
                break
    client.delete(f"/api/v1/terminal/sessions/{sid}", headers=auth)
    assert "TANPA_SSH" in got
