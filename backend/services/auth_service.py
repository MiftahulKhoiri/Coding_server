"""Autentikasi & manajemen pengguna."""
from __future__ import annotations

import json
import secrets
import time

from backend.config import Settings
from backend.core.exceptions import AppError, Conflict, NotFound, Unauthorized
from backend.core.logging import get_logger
from backend.core.permissions import ROLES, effective_perms
from backend.core.security import create_token, decode_token, hash_password, verify_password
from backend.database.db import Database

log = get_logger("auth")


class AuthService:
    def __init__(self, settings: Settings, db: Database):
        self.s = settings
        self.db = db

    def bootstrap_admin(self) -> str | None:
        """Buat admin pertama bila belum ada user. Password acak ditulis ke file 0600."""
        if self.db.one("SELECT id FROM users LIMIT 1"):
            return None
        password = self.s.admin_password or secrets.token_urlsafe(12)
        self.create_user(self.s.admin_username, password, "admin")
        if not self.s.admin_password:
            path = self.s.metadata_dir / "initial_admin_password.txt"
            path.write_text(f"username: {self.s.admin_username}\npassword: {password}\n")
            path.chmod(0o600)
            log.warning("Admin awal dibuat. Password tersimpan di %s", path)
        return password

    def create_user(self, username: str, password: str, role: str = "developer", extra_perms: list[str] | None = None) -> dict:
        username = username.strip()
        if not username or len(username) > 64 or not username.replace("_", "").replace("-", "").replace(".", "").isalnum():
            raise AppError("Username hanya boleh huruf, angka, _ - .", code="bad_username")
        if len(password) < 8:
            raise AppError("Password minimal 8 karakter", code="weak_password")
        if role not in ROLES:
            raise AppError("Peran tidak dikenal", code="bad_role")
        if self.db.one("SELECT id FROM users WHERE username=?", (username,)):
            raise Conflict("Username sudah dipakai")
        self.db.execute(
            "INSERT INTO users(username, password_hash, role, extra_perms, is_active, created_at) VALUES(?,?,?,?,1,?)",
            (username, hash_password(password), role, json.dumps(extra_perms or []), time.time()),
        )
        return self.public(self.db.one("SELECT * FROM users WHERE username=?", (username,)))

    @staticmethod
    def public(row: dict) -> dict:
        extra = json.loads(row.get("extra_perms") or "[]")
        return {
            "id": row["id"], "username": row["username"], "role": row["role"], "is_active": bool(row["is_active"]),
            "permissions": sorted(effective_perms(row["role"], extra)), "created_at": row["created_at"],
        }

    def list_users(self) -> list[dict]:
        return [self.public(r) for r in self.db.all("SELECT * FROM users ORDER BY id")]

    def update_user(self, user_id: int, role: str | None = None, is_active: bool | None = None, password: str | None = None) -> dict:
        row = self.db.one("SELECT * FROM users WHERE id=?", (user_id,))
        if not row:
            raise NotFound("User tidak ditemukan")
        if role is not None:
            if role not in ROLES:
                raise AppError("Peran tidak dikenal", code="bad_role")
            self.db.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
        if is_active is not None:
            self.db.execute("UPDATE users SET is_active=? WHERE id=?", (int(is_active), user_id))
        if password is not None:
            if len(password) < 8:
                raise AppError("Password minimal 8 karakter", code="weak_password")
            self.db.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(password), user_id))
        return self.public(self.db.one("SELECT * FROM users WHERE id=?", (user_id,)))

    def change_password(self, user: dict, old: str, new: str) -> None:
        row = self.db.one("SELECT * FROM users WHERE id=?", (user["id"],))
        if not verify_password(old, row["password_hash"]):
            raise Unauthorized("Password lama salah", code="bad_credentials")
        self.update_user(user["id"], password=new)

    def _issue(self, row: dict) -> dict:
        access, _, exp = create_token(self.s.secret_key, user_id=row["id"], username=row["username"], kind="access",
                                      ttl_seconds=self.s.access_token_minutes * 60)
        refresh, _, rexp = create_token(self.s.secret_key, user_id=row["id"], username=row["username"], kind="refresh",
                                        ttl_seconds=self.s.refresh_token_days * 86400)
        return {"access_token": access, "refresh_token": refresh, "token_type": "bearer", "expires_at": exp,
                "refresh_expires_at": rexp, "user": self.public(row)}

    def login(self, username: str, password: str) -> dict:
        row = self.db.one("SELECT * FROM users WHERE username=?", (username.strip(),))
        # Selalu hitung hash agar waktu respons tidak membocorkan keberadaan user.
        ok = verify_password(password, row["password_hash"] if row else "scrypt$16384$8$1$AAAA$AAAA")
        if not row or not ok:
            raise Unauthorized("Username atau password salah", code="bad_credentials")
        if not row["is_active"]:
            raise Unauthorized("Akun dinonaktifkan", code="inactive")
        return self._issue(row)

    def refresh(self, refresh_token: str) -> dict:
        payload = decode_token(self.s.secret_key, refresh_token, kind="refresh")
        if self.is_revoked(payload["jti"]):
            raise Unauthorized("Token sudah dicabut", code="token_revoked")
        row = self.db.one("SELECT * FROM users WHERE id=?", (int(payload["sub"]),))
        if not row or not row["is_active"]:
            raise Unauthorized("User tidak aktif", code="inactive")
        self.revoke(payload["jti"], payload["exp"])  # refresh token sekali pakai (rotasi)
        return self._issue(row)

    def revoke(self, jti: str, exp: int) -> None:
        self.db.execute("INSERT OR IGNORE INTO revoked_tokens(jti, exp) VALUES(?,?)", (jti, exp))
        self.db.execute("DELETE FROM revoked_tokens WHERE exp < ?", (int(time.time()),))

    def is_revoked(self, jti: str) -> bool:
        return self.db.one("SELECT 1 AS x FROM revoked_tokens WHERE jti=?", (jti,)) is not None

    def user_from_access_token(self, token: str) -> dict:
        payload = decode_token(self.s.secret_key, token, kind="access")
        if self.is_revoked(payload["jti"]):
            raise Unauthorized("Token sudah dicabut", code="token_revoked")
        row = self.db.one("SELECT * FROM users WHERE id=?", (int(payload["sub"]),))
        if not row or not row["is_active"]:
            raise Unauthorized("User tidak aktif", code="inactive")
        u = self.public(row)
        u["perms"] = set(u["permissions"])
        u["jti"] = payload["jti"]
        u["exp"] = payload["exp"]
        return u
