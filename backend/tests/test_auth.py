def test_health_public(client):
    r = client.get("/api/v1/system/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_requires_token(client):
    assert client.get("/api/v1/projects").status_code == 401


def test_bad_login(client):
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "salah"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "bad_credentials"


def test_me_and_refresh_logout(client):
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin-pass-123"})
    tok = r.json()
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    me = client.get("/api/v1/auth/me", headers=h).json()
    assert me["username"] == "admin" and "admin" in me["permissions"]
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": tok["refresh_token"]})
    assert r2.status_code == 200
    # refresh token sekali pakai
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": tok["refresh_token"]}).status_code == 401
    assert client.post("/api/v1/auth/logout", json={}, headers=h).status_code == 200
    assert client.get("/api/v1/auth/me", headers=h).status_code == 401


def test_viewer_permissions(client, auth):
    r = client.post("/api/v1/auth/users", json={"username": "lihat", "password": "lihat-pass-1", "role": "viewer"}, headers=auth)
    assert r.status_code in (201, 409)
    tok = client.post("/api/v1/auth/login", json={"username": "lihat", "password": "lihat-pass-1"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    r = client.post("/api/v1/projects", json={"name": "x"}, headers=h)
    assert r.status_code == 403
    assert client.get("/api/v1/auth/users", headers=h).status_code == 403


def test_password_hash_roundtrip():
    from backend.core.security import hash_password, verify_password

    h = hash_password("rahasia123")
    assert verify_password("rahasia123", h)
    assert not verify_password("salah", h)


def test_rate_limiter():
    import pytest

    from backend.core.exceptions import TooManyRequests
    from backend.core.security import RateLimiter

    rl = RateLimiter(3, 60)
    for _ in range(3):
        rl.hit("k")
    with pytest.raises(TooManyRequests):
        rl.hit("k")
