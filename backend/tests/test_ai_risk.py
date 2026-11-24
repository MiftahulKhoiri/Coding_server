import pytest

from backend.services.ai_risk import HIGH, LOW, MEDIUM, classify_change


@pytest.mark.parametrize("path,action,old,new,level", [
    ("README.md", "write", "a\n", "b\n", LOW),
    ("docs/guide.txt", "write", None, "hai\n", LOW),
    ("src/app.py", "write", "x = 1\n", "x  =  1\n", LOW),
    ("src/app.py", "write", "x = 1\n", "x = 2\n", MEDIUM),
    ("src/app.py", "write", "", "import subprocess\nsubprocess.run(['ls'])\n", HIGH),
    ("scripts/deploy.sh", "write", "", "echo hi\n", HIGH),
    ("backend/auth_service.py", "write", "a", "b", HIGH),
    (".github/workflows/ci.yml", "write", "a", "b", HIGH),
    ("db/migrations/001.sql", "write", None, "CREATE TABLE t(x);\n", HIGH),
    ("src/app.py", "delete", "x", None, HIGH),
    ("q.sql", "write", "", "DELETE FROM users;\n", HIGH),
    ("q.sql", "write", "", "DELETE FROM users WHERE id=1;\n", MEDIUM),
])
def test_classify(path, action, old, new, level):
    assert classify_change(path, action, old, new)[0] == level


def test_high_risk_requires_confirmation(client, auth, project):
    svc = client.app.state.services
    root = svc.projects.project_dir(project)
    user = svc.auth.user_from_access_token(auth["Authorization"][7:])
    row = svc.ai.propose(user, project, "run.sh", "write", "echo hai\n", "uji", root=root)
    assert row["risk"] == HIGH
    url = f"/api/v1/ai/proposals/{row['id']}/decide"
    r = client.post(url, json={"project_id": project, "approve": True}, headers=auth)
    assert r.status_code == 409 and r.json()["error"]["code"] == "high_risk_confirmation_required"
    r = client.post(url, json={"project_id": project, "approve": True, "confirm_high_risk": True}, headers=auth)
    assert r.status_code == 200 and r.json()["status"] == "approved"
    assert (root / "run.sh").read_text() == "echo hai\n"
    lst = client.get("/api/v1/ai/proposals", params={"project_id": project}, headers=auth).json()["proposals"]
    assert lst[0]["risk"] == HIGH and lst[0]["risk_reasons"]
