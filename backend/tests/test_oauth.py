"""Menautkan akun GitHub/Google (device flow) dengan penyedia tiruan; email profil hanya dari akun tertaut."""
import time

import httpx
import pytest

from backend.services import oauth_service

STATE = {"polls": 0, "deny": False, "gh_id": 101}


def handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    body = dict(httpx.QueryParams(request.content.decode())) if request.content else {}
    if url == "https://github.com/login/device/code":
        assert body["client_id"] == "gh-client"
        return httpx.Response(200, json={"device_code": "dev1", "user_code": "ABCD-1234", "interval": 0,
                                         "verification_uri": "https://github.com/login/device", "expires_in": 60,
                                         "scope_echo": body["scope"]})
    if url == "https://github.com/login/oauth/access_token":
        STATE["polls"] += 1
        if STATE["deny"]:
            return httpx.Response(200, json={"error": "access_denied"})
        if STATE["polls"] < 2:
            return httpx.Response(200, json={"error": "authorization_pending"})
        return httpx.Response(200, json={"access_token": "gho_token", "token_type": "bearer"})
    if url == "https://api.github.com/user":
        assert request.headers["authorization"] == "Bearer gho_token"
        return httpx.Response(200, json={"id": STATE["gh_id"], "login": "budiku", "name": "Budi Santoso",
                                         "avatar_url": "https://avatars/x"})
    if url == "https://api.github.com/user/emails":
        return httpx.Response(200, json=[{"email": "lain@contoh.id", "verified": True, "primary": False},
                                         {"email": "budi@contoh.id", "verified": True, "primary": True},
                                         {"email": "belum@contoh.id", "verified": False, "primary": False},
                                         {"email": "1+budiku@users.noreply.github.com", "verified": True}])
    if url == "https://oauth2.googleapis.com/device/code":
        return httpx.Response(200, json={"device_code": "gdev", "user_code": "GGG-HHH", "interval": 0,
                                         "verification_url": "https://www.google.com/device", "expires_in": 60})
    if url == "https://oauth2.googleapis.com/token":
        assert body["client_secret"] == "g-secret"
        return httpx.Response(200, json={"access_token": "ya29", "id_token": "x"})
    if url == "https://openidconnect.googleapis.com/v1/userinfo":
        return httpx.Response(200, json={"sub": "g-77", "email": "budi.g@gmail.com", "email_verified": True,
                                         "name": "Budi G", "picture": "https://pic"})
    return httpx.Response(404, json={"error": "tidak dikenal"})


@pytest.fixture(autouse=True)
def fake_oauth(monkeypatch):
    monkeypatch.setattr(oauth_service, "http_client",
                        lambda timeout=20.0: httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=timeout))
    STATE.update(polls=0, deny=False, gh_id=101)
    yield


def login_new(client, auth, name):
    client.app.state.services.login_limiter._hits.clear()
    assert client.post("/api/v1/auth/users", json={"username": name, "password": name + "-pass-1"}, headers=auth).status_code == 201
    r = client.post("/api/v1/auth/login", json={"username": name, "password": name + "-pass-1"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def wait_flow(client, h, fid, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        f = client.get(f"/api/v1/auth/identities/flows/{fid}", headers=h).json()
        if f["status"] != "pending":
            return f
        time.sleep(0.1)
    raise AssertionError("alur tidak selesai")


def test_config_is_root_only_and_required(client, auth):
    h = login_new(client, auth, "oauthdev")
    r = client.post("/api/v1/auth/identities/github/link", json={}, headers=h)
    assert r.status_code == 409 and r.json()["error"]["code"] == "oauth_not_configured"
    assert client.put("/api/v1/auth/oauth/config", json={"github_client_id": "x"}, headers=h).status_code == 403
    out = client.put("/api/v1/auth/oauth/config", json={"github_client_id": "gh-client", "google_client_id": "g-client",
                                                         "google_client_secret": "g-secret"}, headers=auth).json()
    assert out == {"github_client_id": "gh-client", "google_client_id": "g-client", "google_secret_set": True}
    assert "g-secret" not in str(client.get("/api/v1/auth/oauth/config", headers=auth).json())
    assert client.get("/api/v1/auth/oauth/providers", headers=h).json() == {"github": True, "google": True}


def test_github_link_sets_verified_email_git_push_and_author(client, auth, project):
    client.put("/api/v1/auth/oauth/config", json={"github_client_id": "gh-client", "google_client_id": "g-client",
                                                  "google_client_secret": "g-secret"}, headers=auth)
    h = login_new(client, auth, "ghuser")
    f = client.post("/api/v1/auth/identities/github/link", json={"allow_push": True}, headers=h).json()
    assert f["user_code"] == "ABCD-1234" and f["verification_uri"].startswith("https://github.com/")
    f = wait_flow(client, h, f["flow_id"])
    assert f["status"] == "linked", f
    me = client.get("/api/v1/auth/me", headers=h).json()
    assert me["email"] == "budi@contoh.id" and me["email_verified"] is True and me["display_name"] == "Budi Santoso"
    ids = client.get("/api/v1/auth/identities", headers=h).json()
    assert ids["verified_emails"] == ["budi@contoh.id", "lain@contoh.id"]  # yang belum terverifikasi & noreply tidak ikut
    assert ids["identities"][0]["git_push"] is True
    creds = client.get("/api/v1/git/credentials", headers=h).json()
    assert any(c["host"] == "github.com" and c["username"] == "budiku" for c in creds.get("credentials", creds)), creds
    # ganti ke email terverifikasi lain boleh; email asing ditolak
    assert client.patch("/api/v1/auth/me", json={"email": "lain@contoh.id"}, headers=h).json()["email"] == "lain@contoh.id"
    assert client.patch("/api/v1/auth/me", json={"email": "orang@lain.id"}, headers=h).status_code == 400
    # akun GitHub yang sama tidak bisa ditautkan ke pengguna lain
    h2 = login_new(client, auth, "ghuser2")
    f2 = wait_flow(client, h2, client.post("/api/v1/auth/identities/github/link", json={}, headers=h2).json()["flow_id"])
    assert f2["status"] == "error" and "pengguna lain" in f2["message"], f2
    # lepas tautan: email tidak lagi terverifikasi, kredensial Git dari tautan ikut dihapus
    assert client.delete("/api/v1/auth/identities/github", headers=h).status_code == 200
    me = client.get("/api/v1/auth/me", headers=h).json()
    assert me["email_verified"] is False
    creds = client.get("/api/v1/git/credentials", headers=h).json()
    assert not any(c["host"] == "github.com" for c in creds.get("credentials", creds))


def test_google_link_and_denied(client, auth):
    client.put("/api/v1/auth/oauth/config", json={"github_client_id": "gh-client", "google_client_id": "g-client",
                                                  "google_client_secret": "g-secret"}, headers=auth)
    h = login_new(client, auth, "guser")
    f = wait_flow(client, h, client.post("/api/v1/auth/identities/google/link", json={}, headers=h).json()["flow_id"])
    assert f["status"] == "linked" and f["identity"]["emails"] == ["budi.g@gmail.com"]
    assert client.get("/api/v1/auth/me", headers=h).json()["email"] == "budi.g@gmail.com"
    STATE.update(deny=True, gh_id=202)
    f = wait_flow(client, h, client.post("/api/v1/auth/identities/github/link", json={}, headers=h).json()["flow_id"])
    assert f["status"] == "denied"
    other = login_new(client, auth, "intip")
    assert client.get(f"/api/v1/auth/identities/flows/{f['flow_id']}", headers=other).status_code == 404
