"""Autentikasi, profil, & manajemen pengguna.

Akun admin utama (root)
-----------------------
Satu akun ditandai ``is_root=1`` (username ``CS_ADMIN_USERNAME``, bawaan ``admin``). Akun ini adalah
pintu pemulihan bila sandi akun lain terlupa, jadi:

* tidak bisa dihapus, dinonaktifkan, diganti nama, atau diturunkan perannya — oleh siapa pun;
* sandinya TIDAK bisa diubah lewat API/aplikasi; sumbernya selalu di server:
  ``CS_ADMIN_PASSWORD`` (deployment/configuration/coding_server.env) atau, bila kosong,
  ``workspace/metadata/initial_admin_password.txt``. Setiap server start, sandi root disinkronkan
  ke sumber itu, jadi mengubah sandi root = ubah nilai di server lalu restart service;
* hanya root yang boleh membuat/mengubah/menghapus akun lain berperan ``admin``.
"""
from __future__ import annotations

import json
import re
import secrets
import time

from backend.config import Settings
from backend.core.exceptions import AppError, Conflict, Forbidden, NotFound, Unauthorized
from backend.core.logging import get_logger
from backend.core.permissions import ROLES, effective_perms
from backend.core.security import create_token, decode_token, hash_password, verify_password
from backend.database.db import Database

log = get_logger("auth")

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ROOT_FILE = "initial_admin_password.txt"


def _root_forbidden(msg: str) -> Forbidden:
    return Forbidden(msg, code="root_protected")


class AuthService:
    def __init__(self, settings: Settings, db: Database):
        self.s = settings
        self.db = db

    # ---------------- akun admin utama (root) ----------------
    def _root_file(self):
        return self.s.metadata_dir / ROOT_FILE

    def stored_root_password(self) -> str | None:
        """Sandi root yang disimpan di server: CS_ADMIN_PASSWORD, lalu file initial_admin_password.txt."""
        if self.s.admin_password:
            return self.s.admin_password
        try:
            for line in self._root_file().read_text(encoding="utf-8").splitlines():
                if line.lower().startswith("password:"):
                    pw = line.split(":", 1)[1].strip()
                    return pw or None
        except OSError:
            pass
        return None

    def _write_root_file(self, username: str, password: str) -> None:
        path = self._root_file()
        path.write_text(f"username: {username}\npassword: {password}\n")
        path.chmod(0o600)
        log.warning("Sandi admin utama tersimpan di %s", path)

    def root(self) -> dict | None:
        return self.db.one("SELECT * FROM users WHERE is_root=1 ORDER BY id LIMIT 1")

    def bootstrap_admin(self) -> str | None:
        """Buat admin utama bila belum ada user, lalu pastikan status root & sandinya sinkron."""
        created = None
        if not self.db.one("SELECT id FROM users LIMIT 1"):
            password = self.stored_root_password() or secrets.token_urlsafe(12)
            self.create_user(self.s.admin_username, password, "admin", _root=True)
            if not self.s.admin_password and not self._root_file().is_file():
                self._write_root_file(self.s.admin_username, password)
            created = password
        self.ensure_root()
        return created

    def ensure_root(self) -> dict:
        """Pastikan tepat ada satu akun root yang aktif, berperan admin, dan sandinya = sandi di server."""
        row = self.root()
        if row is None:
            row = (self.db.one("SELECT * FROM users WHERE username=?", (self.s.admin_username,))
                   or self.db.one("SELECT * FROM users WHERE role='admin' ORDER BY id LIMIT 1"))
            if row is None:  # ada user tapi tidak ada admin sama sekali → buat root baru
                password = self.stored_root_password() or secrets.token_urlsafe(12)
                name = self.s.admin_username
                if self.db.one("SELECT id FROM users WHERE username=?", (name,)):
                    name = f"{name}-root"
                self.create_user(name, password, "admin", _root=True)
                if not self.s.admin_password and not self._root_file().is_file():
                    self._write_root_file(name, password)
                row = self.root()
            else:
                self.db.execute("UPDATE users SET is_root=1 WHERE id=?", (row["id"],))
                log.info("Akun '%s' ditetapkan sebagai admin utama (root)", row["username"])
        assert row is not None
        if row["role"] != "admin" or not row["is_active"]:
            self.db.execute("UPDATE users SET role='admin', is_active=1 WHERE id=?", (row["id"],))
        pw = self.stored_root_password()
        if pw is None:
            log.warning("Sandi admin utama belum tersimpan di server (CS_ADMIN_PASSWORD / %s); "
                        "sandi root dibiarkan apa adanya", self._root_file())
        elif not verify_password(pw, row["password_hash"]):
            self.db.execute("UPDATE users SET password_hash=?, updated_at=? WHERE id=?",
                            (hash_password(pw), time.time(), row["id"]))
            log.warning("Sandi admin utama '%s' disinkronkan ke sandi yang tersimpan di server", row["username"])
        return self.root()  # type: ignore[return-value]

    # ---------------- data publik ----------------
    @staticmethod
    def public(row: dict) -> dict:
        extra = json.loads(row.get("extra_perms") or "[]")
        return {
            "id": row["id"], "username": row["username"], "role": row["role"], "is_active": bool(row["is_active"]),
            "permissions": sorted(effective_perms(row["role"], extra)), "created_at": row["created_at"],
            "display_name": row.get("display_name") or "", "email": row.get("email") or "",
            "bio": row.get("bio") or "", "is_root": bool(row.get("is_root")),
            "updated_at": row.get("updated_at") or 0.0, "last_login_at": row.get("last_login_at"),
        }

    def _get(self, user_id: int) -> dict:
        row = self.db.one("SELECT * FROM users WHERE id=?", (user_id,))
        if not row:
            raise NotFound("User tidak ditemukan")
        return row

    def list_users(self) -> list[dict]:
        return [self.public(r) for r in self.db.all("SELECT * FROM users ORDER BY is_root DESC, id")]

    # ---------------- validasi ----------------
    @staticmethod
    def _check_username(username: str) -> str:
        username = username.strip()
        if not username or len(username) > 64 or not username.replace("_", "").replace("-", "").replace(".", "").isalnum():
            raise AppError("Username hanya boleh huruf, angka, _ - .", code="bad_username")
        return username

    @staticmethod
    def _check_password(password: str) -> None:
        if len(password) < 8:
            raise AppError("Password minimal 8 karakter", code="weak_password")
        if len(password) > 256:
            raise AppError("Password terlalu panjang", code="weak_password")

    @staticmethod
    def _profile_fields(display_name: str | None, email: str | None, bio: str | None) -> dict:
        out: dict = {}
        if display_name is not None:
            display_name = " ".join(display_name.split())
            if len(display_name) > 80:
                raise AppError("Nama tampilan maksimal 80 karakter", code="bad_profile")
            out["display_name"] = display_name
        if email is not None:
            email = email.strip()
            if email and (len(email) > 120 or not _EMAIL.match(email)):
                raise AppError("Format email tidak valid", code="bad_profile")
            out["email"] = email
        if bio is not None:
            bio = bio.strip()
            if len(bio) > 500:
                raise AppError("Bio maksimal 500 karakter", code="bad_profile")
            out["bio"] = bio
        return out

    @staticmethod
    def _is_root(actor: dict | None) -> bool:
        return bool(actor and actor.get("is_root"))

    # ---------------- CRUD pengguna ----------------
    def create_user(self, username: str, password: str, role: str = "developer", extra_perms: list[str] | None = None,
                    *, actor: dict | None = None, display_name: str = "", email: str = "", _root: bool = False) -> dict:
        username = self._check_username(username)
        self._check_password(password)
        if role not in ROLES:
            raise AppError("Peran tidak dikenal", code="bad_role")
        if role == "admin" and actor is not None and not self._is_root(actor):
            raise _root_forbidden("Hanya admin utama yang boleh membuat akun admin")
        prof = self._profile_fields(display_name, email, None)
        if self.db.one("SELECT id FROM users WHERE username=?", (username,)):
            raise Conflict("Username sudah dipakai")
        now = time.time()
        self.db.execute(
            "INSERT INTO users(username, password_hash, role, extra_perms, is_active, created_at, display_name, email,"
            " is_root, updated_at) VALUES(?,?,?,?,1,?,?,?,?,?)",
            (username, hash_password(password), role, json.dumps(extra_perms or []), now,
             prof.get("display_name", ""), prof.get("email", ""), int(_root), now),
        )
        return self.public(self.db.one("SELECT * FROM users WHERE username=?", (username,)))

    def update_user(self, user_id: int, role: str | None = None, is_active: bool | None = None,
                    password: str | None = None, *, actor: dict | None = None, display_name: str | None = None,
                    email: str | None = None) -> dict:
        row = self._get(user_id)
        if row["is_root"]:
            if role is not None and role != "admin":
                raise _root_forbidden("Peran admin utama tidak bisa diubah")
            if is_active is not None and not is_active:
                raise _root_forbidden("Admin utama tidak bisa dinonaktifkan")
            if password is not None:
                raise _root_forbidden("Sandi admin utama hanya bisa diubah di server (CS_ADMIN_PASSWORD), lalu restart")
            if actor is not None and actor["id"] != row["id"] and (display_name is not None or email is not None):
                raise _root_forbidden("Profil admin utama hanya bisa diubah oleh admin utama sendiri")
        elif actor is not None and not self._is_root(actor):
            if row["role"] == "admin" and row["id"] != actor["id"]:
                raise _root_forbidden("Hanya admin utama yang boleh mengubah akun admin lain")
            if role == "admin":
                raise _root_forbidden("Hanya admin utama yang boleh menjadikan akun sebagai admin")
        if actor is not None and actor["id"] == row["id"]:
            if is_active is not None and not is_active:
                raise AppError("Tidak bisa menonaktifkan akun sendiri", code="self_protected")
            if role is not None and role != row["role"]:
                raise AppError("Tidak bisa mengubah peran akun sendiri", code="self_protected")
        sets: dict = {}
        if role is not None:
            if role not in ROLES:
                raise AppError("Peran tidak dikenal", code="bad_role")
            sets["role"] = role
        if is_active is not None:
            sets["is_active"] = int(is_active)
        if password is not None:
            self._check_password(password)
            sets["password_hash"] = hash_password(password)
        sets.update(self._profile_fields(display_name, email, None))
        if sets:
            sets["updated_at"] = time.time()
            cols = ", ".join(f"{k}=?" for k in sets)
            self.db.execute(f"UPDATE users SET {cols} WHERE id=?", (*sets.values(), user_id))
        return self.public(self._get(user_id))

    def delete_user(self, actor: dict, user_id: int) -> dict:
        """Hapus akun. Proyek miliknya dipindahkan ke admin utama supaya tidak ada data yang hilang."""
        row = self._get(user_id)
        if row["is_root"]:
            raise _root_forbidden("Admin utama tidak bisa dihapus")
        if row["id"] == actor["id"]:
            raise AppError("Tidak bisa menghapus akun sendiri", code="self_protected")
        if row["role"] == "admin" and not self._is_root(actor):
            raise _root_forbidden("Hanya admin utama yang boleh menghapus akun admin")
        root = self.root()
        moved = 0
        with self.db.tx() as c:
            if root:
                moved = c.execute("UPDATE projects SET owner_id=? WHERE owner_id=?", (root["id"], user_id)).rowcount
            for table in ("favorites", "recent_files", "git_credentials"):
                c.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
            c.execute("DELETE FROM users WHERE id=?", (user_id,))
        return {"username": row["username"], "projects_moved": moved}

    # ---------------- profil sendiri ----------------
    def update_profile(self, user: dict, display_name: str | None = None, email: str | None = None,
                       bio: str | None = None) -> dict:
        sets = self._profile_fields(display_name, email, bio)
        if sets:
            sets["updated_at"] = time.time()
            cols = ", ".join(f"{k}=?" for k in sets)
            self.db.execute(f"UPDATE users SET {cols} WHERE id=?", (*sets.values(), user["id"]))
        return self.public(self._get(user["id"]))

    def change_password(self, user: dict, old: str, new: str) -> None:
        row = self._get(user["id"])
        if row["is_root"]:
            raise _root_forbidden("Sandi admin utama hanya bisa diubah di server (CS_ADMIN_PASSWORD), lalu restart")
        if not verify_password(old, row["password_hash"]):
            raise Unauthorized("Password lama salah", code="bad_credentials")
        if old == new:
            raise AppError("Password baru harus berbeda dari yang lama", code="weak_password")
        self.update_user(user["id"], password=new)

    # ---------------- token ----------------
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
        self.db.execute("UPDATE users SET last_login_at=? WHERE id=?", (time.time(), row["id"]))
        return self._issue(self._get(row["id"]))

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
