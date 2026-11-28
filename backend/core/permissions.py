"""Hak akses berbasis peran. AI tidak pernah mendapat hak melebihi pengguna pemiliknya."""
from __future__ import annotations

from enum import Enum


class Perm(str, Enum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXECUTE = "execute"
    BUILD = "build"
    TERMINAL = "terminal"
    ADMIN = "admin"          # melihat & membantu semua proyek/task/terminal pengguna lain
    USERS = "users"          # kelola akun non-admin
    AI_MANAGE = "ai_manage"  # pengaturan AI: koneksi, model, konteks, lepas model, Uji Model, profil
    SYSTEM = "system"        # backup/restore, proses & audit server — hanya admin utama (root)


ALL = {p.value for p in Perm}
ROOT_ONLY = {"system"}
# Hak yang hanya boleh diberikan (sebagai hak tambahan) oleh admin utama.
ROOT_GRANT_ONLY = {"admin", "users", "system"}

ROLES: dict[str, set[str]] = {
    # Admin biasa: semua kecuali hak sistem (khusus admin utama).
    "admin": ALL - ROOT_ONLY,
    "developer": {"read", "write", "delete", "execute", "build", "terminal"},
    "runner": {"read", "execute", "build"},
    "viewer": {"read"},
    # Peran untuk agen AI: tidak boleh terminal/admin; hapus perlu persetujuan.
    "ai": {"read", "write", "execute", "build"},
}


def perms_for_role(role: str) -> set[str]:
    return set(ROLES.get(role, set()))


def effective_perms(role: str, extra: list[str] | None = None, is_root: bool = False) -> set[str]:
    if is_root:
        return set(ALL)
    perms = perms_for_role(role)
    if extra:
        perms |= {p for p in extra if p in ALL - ROOT_ONLY}
    return perms


def intersect_for_ai(user_perms: set[str]) -> set[str]:
    """Hak agen AI = irisan hak pengguna dengan hak peran 'ai'."""
    return user_perms & ROLES["ai"]
