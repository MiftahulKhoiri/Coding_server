"""Klasifikasi risiko perubahan file oleh AI (LOW / MEDIUM / HIGH).

Dipakai Approval Center: perubahan HIGH tidak pernah diterapkan otomatis dan butuh
konfirmasi eksplisit (``confirm_high_risk``) saat disetujui. Ini heuristik berbasis path dan
baris yang ditambahkan — tujuannya menyorot perubahan yang perlu dibaca teliti, bukan
menjamin perubahan LOW pasti aman.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath

LOW, MEDIUM, HIGH = "LOW", "MEDIUM", "HIGH"
_ORDER = {LOW: 0, MEDIUM: 1, HIGH: 2}

_DOC_EXT = {".md", ".markdown", ".rst", ".txt", ".adoc"}
_SHELL_EXT = {".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd"}
_HIGH_NAMES = {"dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml",
               "makefile", ".env", "sudoers", "crontab", "id_rsa", "authorized_keys"}
_HIGH_PARTS = {".github", "migrations", "migration", "alembic", "systemd", "deployment", "deploy", "infra",
               "terraform", "k8s", "kubernetes", "ansible", ".ssh"}
_HIGH_WORDS = re.compile(r"auth|login|passw|secret|token|credential|permission|security|crypt|sandbox|jwt|oauth",
                         re.I)
_HIGH_CODE = [
    (re.compile(r"\b(subprocess|os\.system|os\.popen|Runtime\.getRuntime|ProcessBuilder|child_process|exec\s*\()"),
     "menjalankan perintah shell/proses"),
    (re.compile(r"\brm\s+-[a-z]*r[a-z]*f|\bshutil\.rmtree|\bmkfs\b|\bdd\s+if="), "penghapusan massal / perintah destruktif"),
    (re.compile(r"\b(DROP|TRUNCATE)\s+(TABLE|DATABASE)\b|\bALTER\s+TABLE\b|\bDELETE\s+FROM\b(?![^;\n]*\bWHERE\b)", re.I),
     "perubahan skema / penghapusan data SQL"),
    (re.compile(r"\b(requests|httpx|urllib|fetch|axios|socket|curl|wget)\b[.\s(]"), "akses jaringan"),
    (re.compile(r"\beval\s*\(|\bpickle\.loads|\byaml\.load\s*\((?![^)]*SafeLoader)"), "eksekusi/deserialisasi dinamis"),
    (re.compile(r"chmod\s+[0-7]*7[0-7]*|\bsudo\b|setuid"), "hak akses sistem"),
]


def _bump(cur: str, new: str) -> str:
    return new if _ORDER[new] > _ORDER[cur] else cur


def _added_lines(old: str | None, new: str | None) -> list[str]:
    old_set = set((old or "").splitlines())
    return [line for line in (new or "").splitlines() if line not in old_set]


def classify_change(path: str, action: str, old: str | None, new: str | None) -> tuple[str, list[str]]:
    """Kembalikan (level, alasan)."""
    reasons: list[str] = []
    level = MEDIUM
    p = PurePosixPath(path)
    name = p.name.lower()
    parts = {x.lower() for x in p.parts[:-1]}

    if action == "delete":
        return HIGH, ["menghapus file"]
    if p.suffix.lower() in _SHELL_EXT:
        level = _bump(level, HIGH); reasons.append("skrip shell")
    if name in _HIGH_NAMES or name.endswith((".service", ".timer", ".env")) or name.startswith(".env"):
        level = _bump(level, HIGH); reasons.append("konfigurasi sistem/infrastruktur")
    if parts & _HIGH_PARTS:
        level = _bump(level, HIGH); reasons.append(f"folder sensitif ({', '.join(sorted(parts & _HIGH_PARTS))})")
    if _HIGH_WORDS.search(path):
        level = _bump(level, HIGH); reasons.append("berkaitan dengan autentikasi/izin/keamanan")

    added = _added_lines(old, new)
    if p.suffix.lower() not in _DOC_EXT:
        text = "\n".join(added)
        for rx, why in _HIGH_CODE:
            if rx.search(text):
                level = _bump(level, HIGH); reasons.append(why)

    if level == MEDIUM:
        if p.suffix.lower() in _DOC_EXT or "docs" in parts:
            level = LOW; reasons.append("dokumentasi")
        elif old is not None and new is not None and old.split() == new.split():
            level = LOW; reasons.append("hanya spasi/format")
        else:
            reasons.append("perubahan kode biasa")
    return level, list(dict.fromkeys(reasons))
