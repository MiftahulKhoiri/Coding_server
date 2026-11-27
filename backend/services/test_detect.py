"""Deteksi perintah uji proyek (pytest/unittest, go test, npm test, make test).

Dipakai agen AI (tool ``run_tests``). Perintah TIDAK pernah berasal dari model: model hanya
memilih ``id`` dari daftar hasil deteksi, lalu server menyusun argv-nya sendiri. Semua
dijalankan lewat ExecutionService (antrean + sandbox + batas sumber daya yang sama).
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from backend.engines.base_engine import find_executable

_SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", "build", "dist", "target"}


@dataclass
class DetectedTest:
    id: str
    framework: str
    argv: list[str]
    env: dict[str, str] = field(default_factory=dict)
    note: str = ""

    def public(self) -> dict:
        return {"id": self.id, "framework": self.framework, "command": " ".join(self.argv), "note": self.note}


@lru_cache
def _python_has_pytest(python: str) -> bool:
    try:
        return subprocess.run([python, "-c", "import pytest"], capture_output=True, timeout=20).returncode == 0
    except Exception:
        return False


def _has_python_tests(root: Path) -> bool:
    n = 0
    for p in root.rglob("*.py"):
        if any(part in _SKIP for part in p.relative_to(root).parts):
            continue
        n += 1
        if p.name.startswith("test_") or p.name.endswith("_test.py"):
            return True
        if n > 5000:
            break
    return (root / "pytest.ini").is_file() or (root / "conftest.py").is_file()


def detect(root: Path, cache_dir: Path) -> list[DetectedTest]:
    from backend.services.deps_install import project_python, venv_has_module

    out: list[DetectedTest] = []
    sys_py = find_executable("python3", "python")
    venv = project_python(root)
    if sys_py and _has_python_tests(root):
        # .venv proyek (hasil install_deps) diutamakan; pytest di venv dicek lewat filesystem saja.
        py = str(venv) if venv else sys_py
        has_pytest = venv_has_module(venv, "pytest") if venv else _python_has_pytest(sys_py)
        where = ".venv proyek" if venv else "Python sistem"
        if has_pytest:
            out.append(DetectedTest("pytest", "pytest", [py, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                                   env={"PYTHONDONTWRITEBYTECODE": "1"}, note=where if venv else ""))
        out.append(DetectedTest("unittest", "unittest", [py, "-m", "unittest", "discover", "-v"],
                               env={"PYTHONDONTWRITEBYTECODE": "1"},
                               note="" if out else f"pytest tidak terpasang di {where} (pasang dengan install_deps)"))
    go = find_executable("go")
    if go and (root / "go.mod").is_file():
        out.append(DetectedTest("go", "go test", [go, "test", "./..."],
                               env={"GOCACHE": str(cache_dir / "go-build"), "GOPATH": str(cache_dir / "gopath"),
                                    "GOFLAGS": "-mod=mod", "GOTOOLCHAIN": "local"}))
    pkg = root / "package.json"
    npm = find_executable("npm")
    if npm and pkg.is_file():
        try:
            script = (json.loads(pkg.read_text(encoding="utf-8")).get("scripts") or {}).get("test")
        except (OSError, ValueError):
            script = None
        if script and "no test specified" not in script:
            out.append(DetectedTest("npm", "npm test", [npm, "test", "--silent"],
                                   env={"npm_config_cache": str(cache_dir / "npm")}, note=script[:120]))
    make = find_executable("make")
    mk = root / "Makefile"
    if make and mk.is_file():
        try:
            if any(line.startswith("test:") for line in mk.read_text(encoding="utf-8", errors="ignore").splitlines()):
                out.append(DetectedTest("make", "make test", [make, "test"]))
        except OSError:
            pass
    return out
