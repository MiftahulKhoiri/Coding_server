"""Menautkan akun GitHub / Google ke profil (OAuth 2.0 *device flow*).

Device flow dipakai karena server Pi biasanya hanya di jaringan rumah (HTTP, tanpa domain publik): tidak perlu URL
callback. Alur: aplikasi meminta kode → pengguna membuka github.com/login/device atau google.com/device di browser,
memasukkan kode, menyetujui → server (memeriksa berkala) menerima token, membaca email TERVERIFIKASI dari penyedia,
lalu menyimpan tautan. Email profil hanya boleh diambil dari akun tertaut ("email aktif").

GitHub dengan izin push (scope `repo`): token ikut disimpan terenkripsi sebagai kredensial Git github.com sehingga
`git push` dari Git Manager langsung bisa tanpa membuat token manual.

Pengaturan (admin utama): Client ID GitHub OAuth App (centang "Enable Device Flow"), Client ID + secret Google
OAuth client jenis "TVs and Limited Input devices". Bisa juga lewat env CS_GITHUB_CLIENT_ID, CS_GOOGLE_CLIENT_ID,
CS_GOOGLE_CLIENT_SECRET.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass, field

import httpx

from backend.core.exceptions import AppError, Conflict, NotFound
from backend.core.logging import get_logger

log = get_logger("oauth")

PROVIDERS = ("github", "google")
FLOW_KEEP = 1800


def http_client(timeout: float = 20.0) -> httpx.AsyncClient:  # diganti di pengujian
    return httpx.AsyncClient(timeout=timeout, headers={"Accept": "application/json", "User-Agent": "coding-server"})


@dataclass
class Flow:
    id: str
    user_id: int
    provider: str
    device_code: str
    user_code: str
    verification_uri: str
    interval: int
    expires_at: float
    allow_push: bool
    status: str = "pending"  # pending | linked | denied | expired | error
    message: str = ""
    identity: dict | None = None
    created: float = field(default_factory=time.time)
    task: asyncio.Task | None = None

    def public(self) -> dict:
        return {"flow_id": self.id, "provider": self.provider, "user_code": self.user_code,
                "verification_uri": self.verification_uri, "interval": self.interval,
                "expires_in": max(0, int(self.expires_at - time.time())), "status": self.status,
                "message": self.message, "identity": self.identity}


class OAuthService:
    def __init__(self, db, secrets, auth, git):
        self.db, self.secrets, self.auth, self.git = db, secrets, auth, git
        self.flows: dict[str, Flow] = {}

    # ---------- konfigurasi ----------
    def _meta(self, key: str) -> str:
        row = self.db.one("SELECT value FROM meta WHERE key=?", (key,))
        return row["value"] if row else ""

    def config(self) -> dict:
        gh = os.environ.get("CS_GITHUB_CLIENT_ID") or self._meta("oauth_github_client_id")
        gc = os.environ.get("CS_GOOGLE_CLIENT_ID") or self._meta("oauth_google_client_id")
        enc = self._meta("oauth_google_client_secret")
        gs = os.environ.get("CS_GOOGLE_CLIENT_SECRET") or (self.secrets.decrypt(enc) if enc else "") or ""
        return {"github_client_id": gh, "google_client_id": gc, "google_client_secret": gs}

    def public_config(self) -> dict:
        c = self.config()
        return {"github_client_id": c["github_client_id"], "google_client_id": c["google_client_id"],
                "google_secret_set": bool(c["google_client_secret"])}

    def providers(self) -> dict:
        c = self.config()
        return {"github": bool(c["github_client_id"]), "google": bool(c["google_client_id"] and c["google_client_secret"])}

    def save_config(self, github_client_id: str | None, google_client_id: str | None, google_client_secret: str | None) -> dict:
        with self.db.tx() as cx:
            for key, val in (("oauth_github_client_id", github_client_id), ("oauth_google_client_id", google_client_id)):
                if val is not None:
                    cx.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?,?)", (key, val.strip()))
            if google_client_secret is not None:
                v = google_client_secret.strip()
                cx.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?,?)",
                           ("oauth_google_client_secret", self.secrets.encrypt(v) if v else ""))
        return self.public_config()

    # ---------- tautan tersimpan ----------
    @staticmethod
    def _identity_out(r: dict) -> dict:
        return {"provider": r["provider"], "login": r["login"], "name": r["name"], "emails": json.loads(r["emails"] or "[]"),
                "avatar_url": r["avatar_url"], "git_push": bool(r["git_token"]), "linked_at": r["linked_at"]}

    def identities(self, user: dict) -> list[dict]:
        rows = self.db.all("SELECT * FROM user_identities WHERE user_id=? ORDER BY provider", (user["id"],))
        return [self._identity_out(r) for r in rows]

    def verified_emails(self, user_id: int) -> list[str]:
        out: list[str] = []
        for r in self.db.all("SELECT emails FROM user_identities WHERE user_id=?", (user_id,)):
            out += [e for e in json.loads(r["emails"] or "[]") if e not in out]
        return out

    def unlink(self, user: dict, provider: str) -> None:
        row = self.db.one("SELECT * FROM user_identities WHERE user_id=? AND provider=?", (user["id"], provider))
        if not row:
            raise NotFound("Akun belum tertaut")
        with self.db.tx() as cx:
            cx.execute("DELETE FROM user_identities WHERE id=?", (row["id"],))
            if row["git_token"]:
                cx.execute("DELETE FROM git_credentials WHERE user_id=? AND host='github.com'", (user["id"],))
            # email profil yang berasal dari akun ini tidak lagi terverifikasi
            u = cx.execute("SELECT email FROM users WHERE id=?", (user["id"],)).fetchone()
            if u and u["email"] in json.loads(row["emails"] or "[]"):
                cx.execute("UPDATE users SET email_verified=0, updated_at=? WHERE id=?", (time.time(), user["id"]))
        self.db.audit("identity_unlink", user=user, target=provider)

    # ---------- device flow ----------
    def _gc(self) -> None:
        now = time.time()
        for fid in [k for k, f in self.flows.items() if f.status != "pending" and now - f.created > FLOW_KEEP]:
            self.flows.pop(fid, None)

    async def start(self, user: dict, provider: str, allow_push: bool = False) -> dict:
        if provider not in PROVIDERS:
            raise NotFound("Penyedia tidak dikenal")
        if not self.providers()[provider]:
            raise AppError(f"Login {provider.title()} belum diatur admin utama (Pengaturan → Akun tertaut → Atur)",
                           code="oauth_not_configured", status_code=409)
        self._gc()
        for f in self.flows.values():  # satu alur aktif per pengguna & penyedia
            if f.user_id == user["id"] and f.provider == provider and f.status == "pending" and f.task:
                f.task.cancel()
                f.status, f.message = "error", "Dibatalkan: alur baru dimulai"
        c = self.config()
        async with http_client() as h:
            if provider == "github":
                scope = "read:user user:email" + (" repo" if allow_push else "")
                r = await h.post("https://github.com/login/device/code", data={"client_id": c["github_client_id"], "scope": scope})
                d = self._json(r, "GitHub")
                flow = Flow(uuid.uuid4().hex, user["id"], provider, d["device_code"], d["user_code"],
                            d.get("verification_uri", "https://github.com/login/device"), int(d.get("interval", 5)),
                            time.time() + int(d.get("expires_in", 900)), allow_push)
            else:
                r = await h.post("https://oauth2.googleapis.com/device/code",
                                 data={"client_id": c["google_client_id"], "scope": "openid email profile"})
                d = self._json(r, "Google")
                flow = Flow(uuid.uuid4().hex, user["id"], provider, d["device_code"], d["user_code"],
                            d.get("verification_url") or d.get("verification_uri", "https://www.google.com/device"),
                            int(d.get("interval", 5)), time.time() + int(d.get("expires_in", 1800)), False)
        self.flows[flow.id] = flow
        flow.task = asyncio.create_task(self._poll(flow, dict(user)))
        return flow.public()

    def flow(self, user: dict, flow_id: str) -> dict:
        f = self.flows.get(flow_id)
        if not f or f.user_id != user["id"]:
            raise NotFound("Alur penautan tidak ditemukan")
        return f.public()

    @staticmethod
    def _json(r: httpx.Response, name: str) -> dict:
        try:
            d = r.json()
        except ValueError:
            d = {}
        if r.status_code >= 400 or "error" in d and "device_code" not in d and "access_token" not in d:
            msg = d.get("error_description") or d.get("error") or f"HTTP {r.status_code}"
            if d.get("error") in ("invalid_client", "unauthorized_client", "device_flow_disabled", "Not Found") \
                    or r.status_code == 404:
                msg = f"Client ID {name} salah atau device flow belum diaktifkan ({d.get('error')})"
            raise AppError(f"{name}: {msg}", code="oauth_error", status_code=502)
        return d

    async def _poll(self, f: Flow, user: dict) -> None:
        c = self.config()
        interval = f.interval
        try:
            async with http_client() as h:
                while time.time() < f.expires_at:
                    await asyncio.sleep(interval)
                    if f.provider == "github":
                        r = await h.post("https://github.com/login/oauth/access_token", data={
                            "client_id": c["github_client_id"], "device_code": f.device_code,
                            "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
                    else:
                        r = await h.post("https://oauth2.googleapis.com/token", data={
                            "client_id": c["google_client_id"], "client_secret": c["google_client_secret"],
                            "device_code": f.device_code, "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
                    try:
                        d = r.json()
                    except ValueError:
                        d = {}
                    err = d.get("error")
                    if err == "authorization_pending":
                        continue
                    if err == "slow_down":
                        interval += 5
                        continue
                    if err in ("access_denied",):
                        f.status, f.message = "denied", "Penautan ditolak di browser"
                        return
                    if err in ("expired_token",):
                        break
                    if err or "access_token" not in d:
                        f.status, f.message = "error", d.get("error_description") or err or f"HTTP {r.status_code}"
                        return
                    token = d["access_token"]
                    profile = await (self._github_profile(h, token) if f.provider == "github" else self._google_profile(h, token))
                    f.identity = self.link(user, f.provider, profile, token if f.allow_push else None)
                    f.status, f.message = "linked", "Akun tertaut"
                    return
            f.status, f.message = "expired", "Kode kedaluwarsa, mulai lagi"
        except asyncio.CancelledError:
            raise
        except AppError as e:
            f.status, f.message = "error", e.message
        except Exception as e:  # jaringan dll.
            log.warning("OAuth %s gagal: %s", f.provider, e)
            f.status, f.message = "error", f"Gagal menghubungi {f.provider}: {e}"

    async def _github_profile(self, h: httpx.AsyncClient, token: str) -> dict:
        hdr = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
        u = self._json(await h.get("https://api.github.com/user", headers=hdr), "GitHub")
        emails = await h.get("https://api.github.com/user/emails", headers=hdr)
        lst = emails.json() if emails.status_code == 200 else []
        verified = [e["email"] for e in sorted(lst, key=lambda e: not e.get("primary")) if e.get("verified")
                    and not e["email"].endswith("@users.noreply.github.com")]
        return {"id": str(u["id"]), "login": u.get("login", ""), "name": u.get("name") or u.get("login", ""),
                "emails": verified, "avatar_url": u.get("avatar_url", "")}

    async def _google_profile(self, h: httpx.AsyncClient, token: str) -> dict:
        u = self._json(await h.get("https://openidconnect.googleapis.com/v1/userinfo",
                                   headers={"Authorization": f"Bearer {token}"}), "Google")
        emails = [u["email"]] if u.get("email") and u.get("email_verified") else []
        return {"id": str(u["sub"]), "login": u.get("email", ""), "name": u.get("name", ""), "emails": emails,
                "avatar_url": u.get("picture", "")}

    def link(self, user: dict, provider: str, profile: dict, git_token: str | None) -> dict:
        other = self.db.one("SELECT user_id FROM user_identities WHERE provider=? AND provider_user_id=?",
                            (provider, profile["id"]))
        if other and other["user_id"] != user["id"]:
            raise Conflict(f"Akun {provider.title()} ini sudah tertaut ke pengguna lain")
        now = time.time()
        with self.db.tx() as cx:
            cx.execute("DELETE FROM user_identities WHERE user_id=? AND provider=?", (user["id"], provider))
            cx.execute("INSERT INTO user_identities(user_id, provider, provider_user_id, login, name, emails, avatar_url, "
                       "git_token, linked_at) VALUES(?,?,?,?,?,?,?,?,?)",
                       (user["id"], provider, profile["id"], profile["login"], profile["name"],
                        json.dumps(profile["emails"]), profile["avatar_url"], int(bool(git_token)), now))
            row = cx.execute("SELECT email, email_verified, display_name FROM users WHERE id=?", (user["id"],)).fetchone()
            sets: dict = {}
            if profile["emails"] and not (row["email_verified"] and row["email"]):
                sets.update(email=profile["emails"][0], email_verified=1)
            elif row["email"] in profile["emails"]:
                sets["email_verified"] = 1
            if not row["display_name"] and profile["name"]:
                sets["display_name"] = profile["name"][:80]
            if sets:
                sets["updated_at"] = now
                cx.execute(f"UPDATE users SET {', '.join(k + '=?' for k in sets)} WHERE id=?", (*sets.values(), user["id"]))
        if git_token and provider == "github":
            self.git.set_credential(user, "github.com", profile["login"] or "x-access-token", git_token)
        self.db.audit("identity_link", user=user, target=provider, detail={"login": profile["login"]})
        return self._identity_out(self.db.one("SELECT * FROM user_identities WHERE user_id=? AND provider=?",
                                              (user["id"], provider)))
