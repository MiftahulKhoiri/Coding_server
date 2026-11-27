"""Instal dependensi proyek di dalam sandbox (pip / npm / go / composer).

Kenapa modul ini ada: program pengguna dijalankan sandbox TANPA jaringan (``CS_SANDBOX_NETWORK=false``),
jadi skrip buatan agen seperti ``subprocess.run(["pip", "install", ...])`` selalu gagal ("name
resolution"), dan pip sistem Debian menolak instal global ("externally-managed-environment").

Solusinya: langkah instal dijalankan sebagai perintah yang argv-nya DISUSUN SERVER (tidak pernah
dari model/pengguna mentah), lewat ExecutionService yang sama (antrean, sandbox bubblewrap, batas
sumber daya), dan hanya langkah instal itu yang diberi jaringan (``CS_INSTALL_NETWORK``, bawaan aktif).
Yang bisa ditulis tetap hanya folder proyek + cache server; $HOME tetap tmpfs kosong.

* Python  → ``.venv`` di folder proyek (``python -m venv``) lalu ``pip install -r requirements.txt``
            (atau ``pip install -e .`` untuk pyproject.toml/setup.py). Engine Python & deteksi uji
            otomatis memakai ``.venv`` ini.
* Node.js → ``npm install`` (cache npm di cache server).
* Go      → ``go mod download``.
* PHP     → ``composer install`` (bila composer terpasang).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from backend.core.exceptions import AppError
from backend.engines.base_engine import find_executable

VENV_NAMES = (".venv", "venv")
MAX_PACKAGES = 20
# Nama paket: huruf/angka di awal (atau @scope/ untuk npm), lalu karakter penentu versi/extras.
# Tidak boleh opsi (-x/--index-url), path (./ /), URL, atau spasi → tidak ada injeksi argumen.
_PKG = re.compile(r"^(@[A-Za-z0-9][A-Za-z0-9._-]*/)?[A-Za-z0-9][A-Za-z0-9._/\-\[\],=<>!~*^]*(@[A-Za-z0-9.^~*<>=-]+)?$")


def project_python(root: Path) -> Path | None:
    """Interpreter virtualenv proyek (.venv/ atau venv/) bila ada.

    Path dikembalikan APA ADANYA (tidak di-resolve) supaya Python mengenali pyvenv.cfg; symlink-nya
    menunjuk ke /usr/bin/python3.x yang ikut di-bind read-only di sandbox.
    """
    for name in VENV_NAMES:
        p = root / name / "bin" / "python"
        if p.is_file() and (root / name / "pyvenv.cfg").is_file():
            return p
    return None


def venv_has_module(venv_python: Path, module: str) -> bool:
    """Cek modul terpasang di venv lewat filesystem saja.

    Sengaja TIDAK menjalankan python venv di luar sandbox: file .pth di site-packages bisa
    mengeksekusi kode saat interpreter start.
    """
    venv = venv_python.parent.parent
    for sp in venv.glob("lib/python3*/site-packages"):
        if (sp / module).is_dir() or (sp / f"{module}.py").is_file():
            return True
    return False


def check_packages(packages: list) -> list[str]:
    if not isinstance(packages, list):
        raise AppError("packages harus berupa daftar", code="bad_packages")
    if len(packages) > MAX_PACKAGES:
        raise AppError(f"Maksimal {MAX_PACKAGES} paket sekali instal", code="bad_packages")
    out = []
    for p in packages:
        p = str(p).strip()
        if not p or len(p) > 100 or "://" in p or ".." in p or not _PKG.match(p):
            raise AppError(f"Nama paket tidak valid: {p!r}", code="bad_packages")
        out.append(p)
    return out


@dataclass
class InstallPlan:
    kind: str  # python | node | go | php
    label: str
    manifest: str  # file yang memicu ("requirements.txt", ...) atau "" bila hanya paket tambahan
    commands: list[tuple[list[str], dict[str, str]]] = field(default_factory=list)
    note: str = ""

    def public(self) -> dict:
        return {"kind": self.kind, "label": self.label, "manifest": self.manifest, "note": self.note,
                "commands": [" ".join(a) for a, _ in self.commands]}


KINDS = ("python", "node", "go", "php")


def _python_plan(root: Path, cache: Path, packages: list[str]) -> InstallPlan:
    py = find_executable("python3", "python")
    if not py:
        raise AppError("Python 3 belum terpasang di server", code="engine_unavailable", status_code=503)
    env = {"PIP_CACHE_DIR": str(cache / "pip"), "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PIP_NO_INPUT": "1",
           "PYTHONDONTWRITEBYTECODE": "1"}
    vpy = project_python(root)
    cmds: list[tuple[list[str], dict[str, str]]] = []
    if vpy is None:
        vpy = root / ".venv" / "bin" / "python"
        cmds.append(([py, "-m", "venv", str(root / ".venv")], {}))
    pip = [str(vpy), "-m", "pip", "install"]
    manifest = ""
    if packages:
        cmds.append((pip + packages, env))
    elif (root / "requirements.txt").is_file():
        manifest = "requirements.txt"
        cmds.append((pip + ["-r", "requirements.txt"], env))
    elif (root / "pyproject.toml").is_file() or (root / "setup.py").is_file():
        manifest = "pyproject.toml" if (root / "pyproject.toml").is_file() else "setup.py"
        cmds.append((pip + ["-e", "."], env))
    else:
        raise AppError("Tidak ada requirements.txt / pyproject.toml / setup.py, dan tidak ada paket yang diminta",
                       code="no_manifest")
    return InstallPlan("python", "Python (pip → .venv proyek)", manifest, cmds,
                       note=f"interpreter: {vpy.relative_to(root)}")


def _node_plan(root: Path, cache: Path, packages: list[str]) -> InstallPlan:
    npm = find_executable("npm")
    if not npm:
        raise AppError("Node.js/npm belum terpasang di server", code="engine_unavailable", status_code=503)
    env = {"npm_config_cache": str(cache / "npm"), "npm_config_update_notifier": "false",
           "npm_config_fund": "false", "npm_config_audit": "false"}
    if not (root / "package.json").is_file():
        if not packages:
            raise AppError("Tidak ada package.json dan tidak ada paket yang diminta", code="no_manifest")
        (root / "package.json").write_text(json.dumps({"name": root.name.lower()[:50] or "proyek", "version": "1.0.0",
                                                       "private": True}, indent=2) + "\n", encoding="utf-8")
    argv = [npm, "install", "--no-audit", "--no-fund"] + packages
    return InstallPlan("node", "Node.js (npm install)", "package.json", [(argv, env)])


def _go_plan(root: Path, cache: Path, packages: list[str]) -> InstallPlan:
    go = find_executable("go")
    if not go:
        raise AppError("Go belum terpasang di server", code="engine_unavailable", status_code=503)
    if not (root / "go.mod").is_file():
        raise AppError("Tidak ada go.mod (buat dulu dengan modul yang benar)", code="no_manifest")
    env = {"GOCACHE": str(cache / "go-build"), "GOPATH": str(cache / "gopath"), "GOFLAGS": "-mod=mod",
           "GOTOOLCHAIN": "local"}
    cmds = [([go, "get", *packages], env)] if packages else []
    cmds.append(([go, "mod", "download"], env))
    return InstallPlan("go", "Go (go mod download)", "go.mod", cmds)


def _php_plan(root: Path, cache: Path, packages: list[str]) -> InstallPlan:
    composer = find_executable("composer")
    if not composer:
        raise AppError("Composer belum terpasang di server", code="engine_unavailable", status_code=503)
    env = {"COMPOSER_HOME": str(cache / "composer"), "COMPOSER_NO_INTERACTION": "1"}
    if packages:
        argv = [composer, "require", "--no-interaction", *packages]
    elif (root / "composer.json").is_file():
        argv = [composer, "install", "--no-interaction"]
    else:
        raise AppError("Tidak ada composer.json dan tidak ada paket yang diminta", code="no_manifest")
    return InstallPlan("php", "PHP (composer)", "composer.json", [(argv, env)])


_BUILDERS = {"python": _python_plan, "node": _node_plan, "go": _go_plan, "php": _php_plan}
_MANIFESTS = {
    "python": ("requirements.txt", "pyproject.toml", "setup.py"),
    "node": ("package.json",),
    "go": ("go.mod",),
    "php": ("composer.json",),
}


def detect_kinds(root: Path) -> list[str]:
    return [k for k, files in _MANIFESTS.items() if any((root / f).is_file() for f in files)]


def plan(root: Path, cache: Path, kind: str | None = None, packages: list | None = None) -> list[InstallPlan]:
    """Susun rencana instal. Tanpa ``kind``: semua manifest yang ada (atau tebak dari isi proyek bila
    hanya ``packages`` yang diberikan)."""
    pkgs = check_packages(packages or [])
    if kind is not None and kind not in KINDS:
        raise AppError(f"Jenis tidak dikenal: {kind}. Pilihan: {', '.join(KINDS)}", code="bad_kind")
    if kind:
        return [_BUILDERS[kind](root, cache, pkgs)]
    kinds = detect_kinds(root)
    if pkgs:
        if len(kinds) == 1:
            return [_BUILDERS[kinds[0]](root, cache, pkgs)]
        if not kinds:
            guess = "node" if any(root.glob("*.js")) and not any(root.glob("*.py")) else "python"
            return [_BUILDERS[guess](root, cache, pkgs)]
        raise AppError(f"Proyek punya beberapa jenis dependensi ({', '.join(kinds)}); sebutkan kind", code="bad_kind")
    if not kinds:
        raise AppError("Tidak ada file dependensi (requirements.txt, pyproject.toml, package.json, go.mod, "
                       "composer.json). Tulis dulu file itu atau sebutkan packages.", code="no_manifest")
    return [_BUILDERS[k](root, cache, []) for k in kinds]
