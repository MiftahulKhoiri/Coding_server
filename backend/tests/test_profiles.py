"""Profil pengguna & perlindungan akun admin utama (root)."""


def _login(client, username, password):
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _root_id(client, auth):
    users = client.get("/api/v1/auth/users", headers=auth).json()
    root = [u for u in users if u["is_root"]]
    assert len(root) == 1 and root[0]["username"] == "admin"
    return root[0]["id"]


def test_me_has_profile_fields(client, auth):
    me = client.get("/api/v1/auth/me", headers=auth).json()
    assert me["is_root"] is True
    for k in ("display_name", "email", "bio", "last_login_at"):
        assert k in me
    assert me["last_login_at"]


def test_update_own_profile(client, auth):
    r = client.patch("/api/v1/auth/me", json={"display_name": "  Admin   Utama ", "email": "admin@contoh.id",
                                             "bio": "pemilik server"}, headers=auth)
    assert r.status_code == 200, r.text
    me = r.json()
    assert me["display_name"] == "Admin Utama" and me["email"] == "admin@contoh.id" and me["bio"] == "pemilik server"
    bad = client.patch("/api/v1/auth/me", json={"email": "bukan-email"}, headers=auth)
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "bad_profile"


def test_root_cannot_be_changed(client, auth):
    rid = _root_id(client, auth)
    for body in ({"role": "developer"}, {"is_active": False}, {"password": "sandi-baru-123"}):
        r = client.patch(f"/api/v1/auth/users/{rid}", json=body, headers=auth)
        assert r.status_code == 403, body
        assert r.json()["error"]["code"] == "root_protected"
    r = client.delete(f"/api/v1/auth/users/{rid}", headers=auth)
    assert r.status_code == 403 and r.json()["error"]["code"] == "root_protected"
    r = client.post("/api/v1/auth/password", json={"old_password": "admin-pass-123", "new_password": "sandi-baru-123"},
                    headers=auth)
    assert r.status_code == 403 and r.json()["error"]["code"] == "root_protected"
    # sandi root tetap yang tersimpan di server
    _login(client, "admin", "admin-pass-123")


def test_user_lifecycle_and_recovery(client, auth):
    r = client.post("/api/v1/auth/users", json={"username": "budi", "password": "budi-pass-1", "role": "developer",
                                                "display_name": "Budi"}, headers=auth)
    assert r.status_code == 201, r.text
    budi = r.json()
    assert budi["display_name"] == "Budi" and budi["is_root"] is False
    hb = _login(client, "budi", "budi-pass-1")
    # profil & sandi sendiri
    assert client.patch("/api/v1/auth/me", json={"display_name": "Budi S"}, headers=hb).json()["display_name"] == "Budi S"
    r = client.post("/api/v1/auth/password", json={"old_password": "budi-pass-1", "new_password": "budi-pass-2"}, headers=hb)
    assert r.status_code == 200, r.text
    # "lupa sandi": admin utama mereset sandi budi
    r = client.patch(f"/api/v1/auth/users/{budi['id']}", json={"password": "budi-reset-3"}, headers=auth)
    assert r.status_code == 200
    hb = _login(client, "budi", "budi-reset-3")
    # proyek budi dipindah ke root saat akun dihapus
    p = client.post("/api/v1/projects", json={"name": "punya-budi"}, headers=hb)
    assert p.status_code == 201, p.text
    pid = p.json()["id"]
    r = client.delete(f"/api/v1/auth/users/{budi['id']}", headers=auth)
    assert r.status_code == 200 and r.json()["projects_moved"] == 1
    assert client.get("/api/v1/auth/me", headers=hb).status_code == 401
    assert client.get(f"/api/v1/projects/{pid}", headers=auth).status_code == 200
    client.delete(f"/api/v1/projects/{pid}", headers=auth)


def test_only_root_manages_admins(client, auth):
    r = client.post("/api/v1/auth/users", json={"username": "admin2", "password": "admin2-pass", "role": "admin"},
                    headers=auth)
    assert r.status_code == 201, r.text
    a2 = r.json()
    h2 = _login(client, "admin2", "admin2-pass")
    r = client.post("/api/v1/auth/users", json={"username": "admin3", "password": "admin3-pass", "role": "admin"},
                    headers=h2)
    assert r.status_code == 403 and r.json()["error"]["code"] == "root_protected"
    r = client.post("/api/v1/auth/users", json={"username": "dev9", "password": "dev9-pass-1"}, headers=h2)
    assert r.status_code == 201
    dev9 = r.json()["id"]
    assert client.patch(f"/api/v1/auth/users/{dev9}", json={"role": "admin"}, headers=h2).status_code == 403
    assert client.patch(f"/api/v1/auth/users/{dev9}", json={"is_active": False}, headers=h2).status_code == 200
    rid = _root_id(client, auth)
    assert client.patch(f"/api/v1/auth/users/{rid}", json={"display_name": "x"}, headers=h2).status_code == 403
    # tidak bisa menonaktifkan / menghapus diri sendiri
    assert client.patch(f"/api/v1/auth/users/{a2['id']}", json={"is_active": False}, headers=h2).status_code == 400
    assert client.delete(f"/api/v1/auth/users/{a2['id']}", headers=h2).status_code == 400
    assert client.delete(f"/api/v1/auth/users/{dev9}", headers=h2).status_code == 200
    assert client.delete(f"/api/v1/auth/users/{a2['id']}", headers=auth).status_code == 200


def test_root_password_resynced_from_server(client):
    """Sandi root yang diutak-atik langsung di database kembali ke sandi server saat ensure_root()."""
    from backend.core.security import hash_password, verify_password

    svc = client.app.state.services
    root = svc.auth.root()
    svc.db.execute("UPDATE users SET password_hash=?, role='viewer', is_active=0 WHERE id=?",
                   (hash_password("dibobol-123"), root["id"]))
    svc.auth.ensure_root()
    row = svc.auth.root()
    assert verify_password("admin-pass-123", row["password_hash"])
    assert row["role"] == "admin" and row["is_active"] == 1
