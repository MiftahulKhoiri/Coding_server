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
    ADMIN = "admin"


ALL = {p.value for p in Perm}

ROLES: dict[str, set[str]] = {
    "admin": set(ALL),
    "developer": {"read", "write", "delete", "execute", "build", "terminal"},
    "runner": {"read", "execute", "build"},
    "viewer": {"read"},
    # Peran untuk agen AI: tidak boleh terminal/admin; hapus perlu persetujuan.
    "ai": {"read", "write", "execute", "build"},
}


def perms_for_role(role: str) -> set[str]:
    return set(ROLES.get(role, set()))


def effective_perms(role: str, extra: list[str] | None = None) -> set[str]:
    perms = perms_for_role(role)
    if extra:
        perms |= {p for p in extra if p in ALL}
    return perms


def intersect_for_ai(user_perms: set[str]) -> set[str]:
    """Hak agen AI = irisan hak pengguna dengan hak peran 'ai'."""
    return user_perms & ROLES["ai"]
