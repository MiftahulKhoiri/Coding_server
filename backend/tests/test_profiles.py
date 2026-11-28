"""Profil pengguna & perlindungan akun admin utama (root)."""


def _login(client, username, password):
    client.app.state.services.login_limiter._hits.clear()  # banyak login di satu sesi tes ≠ serangan brute force
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
    r = client.patch("/api/v1/auth/me", json={"display_name": "  Admin   Utama ", "bio": "pemilik server"}, headers=auth)
    assert r.status_code == 200, r.text
    me = r.json()
    assert me["display_name"] == "Admin Utama" and me["bio"] == "pemilik server"
    bad = client.patch("/api/v1/auth/me", json={"email": "bukan-email"}, headers=auth)
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "bad_profile"
    # email aktif saja: email yang tidak berasal dari akun tertaut ditolak (lihat test_oauth.py)
    bad = client.patch("/api/v1/auth/me", json={"email": "admin@contoh.id"}, headers=auth)
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "email_unverified"
    assert client.patch("/api/v1/auth/me", json={"email": ""}, headers=auth).json()["email_verified"] is False


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


def test_avatar_upload_get_delete(client, auth):
    import io

    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    r = client.put("/api/v1/auth/me/avatar", files={"file": ("a.png", io.BytesIO(png), "image/png")}, headers=auth)
    assert r.status_code == 200, r.text
    me = r.json()
    assert me["avatar_version"]
    g = client.get(f"/api/v1/auth/users/{me['id']}/avatar", headers=auth)
    assert g.status_code == 200 and g.headers["content-type"] == "image/png" and g.content == png
    bad = client.put("/api/v1/auth/me/avatar", files={"file": ("x.png", io.BytesIO(b"<svg>"), "image/png")}, headers=auth)
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "bad_avatar"
    big = client.put("/api/v1/auth/me/avatar",
                     files={"file": ("b.jpg", io.BytesIO(b"\xff\xd8\xff" + b"0" * (2 * 1024 * 1024)), "image/jpeg")},
                     headers=auth)
    assert big.status_code == 413
    assert client.get(f"/api/v1/auth/users/{me['id']}/avatar").status_code == 401
    d = client.delete("/api/v1/auth/me/avatar", headers=auth)
    assert d.status_code == 200 and d.json()["avatar_version"] is None
    assert client.get(f"/api/v1/auth/users/{me['id']}/avatar", headers=auth).status_code == 404


def test_permission_groups(client, auth):
    """Root: semua. Admin biasa: kelola pengguna & AI, tanpa hak sistem. Developer: tanpa kelola pengguna/AI/sistem."""
    me = client.get("/api/v1/auth/me", headers=auth).json()
    assert {"system", "users", "ai_manage", "admin"} <= set(me["permissions"])
    for name, role in (("adm5", "admin"), ("dev5", "developer")):
        assert client.post("/api/v1/auth/users", json={"username": name, "password": name + "-pass-1", "role": role},
                           headers=auth).status_code == 201
    ha, hd = _login(client, "adm5", "adm5-pass-1"), _login(client, "dev5", "dev5-pass-1")
    pa = set(client.get("/api/v1/auth/me", headers=ha).json()["permissions"])
    pd = set(client.get("/api/v1/auth/me", headers=hd).json()["permissions"])
    assert "system" not in pa and {"users", "ai_manage", "admin"} <= pa
    assert not pd & {"system", "users", "ai_manage", "admin"} and {"read", "write", "terminal"} <= pd
    # sistem (backup/proses/audit) hanya root
    for url in ("/api/v1/backup", "/api/v1/system/processes", "/api/v1/system/audit"):
        assert client.get(url, headers=auth).status_code == 200, url
        assert client.get(url, headers=ha).status_code == 403, url
    # kelola pengguna: admin boleh, developer tidak
    assert client.get("/api/v1/auth/users", headers=ha).status_code == 200
    assert client.get("/api/v1/auth/users", headers=hd).status_code == 403
    # pengaturan AI: developer tidak boleh
    r = client.post("/api/v1/ai/unload-all", headers=hd)
    assert r.status_code == 403 and r.json()["error"]["code"] == "permission_denied"
    users = {u["username"]: u["id"] for u in client.get("/api/v1/auth/users", headers=auth).json()}
    for name in ("adm5", "dev5"):
        client.delete(f"/api/v1/auth/users/{users[name]}", headers=auth)


def test_extra_perms_guard(client):
    auth_svc = client.app.state.services.auth
    import pytest
    from backend.core.exceptions import AppError
    with pytest.raises(AppError):
        auth_svc.create_user("x1", "x1-pass-123", "developer", ["system"])
    root = auth_svc.root()
    adm = auth_svc.create_user("x2", "x2-pass-123", "admin", actor={**root, "is_root": 1})
    with pytest.raises(AppError):
        auth_svc.create_user("x3", "x3-pass-123", "developer", ["users"], actor=adm)
    u = auth_svc.create_user("x4", "x4-pass-123", "developer", ["ai_manage"], actor=adm)
    assert "ai_manage" in u["permissions"]
    for n in ("x2", "x4"):
        auth_svc.delete_user({**root, "is_root": 1}, auth_svc.db.one("SELECT id FROM users WHERE username=?", (n,))["id"])
