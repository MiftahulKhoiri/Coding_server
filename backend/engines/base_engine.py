"""Antarmuka bersama semua engine bahasa pemrograman."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


class EngineStatus:
    AVAILABLE = "AVAILABLE"
    NOT_INSTALLED = "NOT_INSTALLED"
    ERROR = "ERROR"


@dataclass
class Step:
    phase: str  # build | run
    argv: list[str]
    timeout: int
    cwd: Path
    env: dict[str, str] = field(default_factory=dict)
    address_space_limit: bool = False
    network: bool = False


@dataclass
class EngineContext:
    project_dir: Path
    file: Path  # path absolut file sumber
    build_dir: Path
    cache_dir: Path
    args: list[str]
    run_timeout: int
    build_timeout: int
    memory_mb: int
    network: bool = False

    @property
    def rel(self) -> str:
        return str(self.file.relative_to(self.project_dir))


# Cari executable juga di lokasi instalasi per-user (tanpa sudo) di Raspberry Pi.
EXTRA_PATHS = [
    str(Path.home() / ".local" / "bin"),
    str(Path.home() / ".dotnet"),
    str(Path.home() / "go" / "bin"),
    "/usr/local/go/bin",
    "/usr/lib/go/bin",
]


def find_executable(*names: str) -> str | None:
    """Cari executable dan kembalikan path ASLI (symlink diselesaikan) agar tetap valid di dalam sandbox."""
    path = os.environ.get("PATH", "") + ":" + ":".join(EXTRA_PATHS)
    for n in names:
        exe = shutil.which(n, path=path)
        if exe:
            return os.path.realpath(exe)
    return None


class BaseEngine(ABC):
    language_id: str = ""
    name: str = ""
    extensions: tuple[str, ...] = ()
    executables: tuple[str, ...] = ()
    version_args: tuple[str, ...] = ("--version",)
    can_build: bool = True
    can_run: bool = True
    address_space_limit: bool = False
    _status_cache: tuple[float, dict] | None = None

    def executable(self) -> str | None:
        return find_executable(*self.executables) if self.executables else None

    def validate_environment(self) -> bool:
        return self.get_status()["status"] == EngineStatus.AVAILABLE

    def get_version(self) -> str | None:
        exe = self.executable()
        if not exe:
            return None
        try:
            r = subprocess.run([exe, *self.version_args], capture_output=True, text=True, timeout=20,
                               env={**os.environ, "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1"})
        except Exception as e:
            return f"error: {e}"
        out = (r.stdout or r.stderr).strip().splitlines()
        return out[0].strip() if out else None

    def get_status(self, refresh: bool = False) -> dict:
        now = time.time()
        if not refresh and self._status_cache and now - self._status_cache[0] < 300:
            return self._status_cache[1]
        exe = self.executable()
        if not exe:
            st = {"status": EngineStatus.NOT_INSTALLED, "version": None, "executable": None}
        else:
            ver = self.get_version()
            ok = bool(ver) and not ver.startswith("error:")
            st = {"status": EngineStatus.AVAILABLE if ok else EngineStatus.ERROR, "version": ver, "executable": exe}
        info = {
            "engine_id": self.language_id,
            "language": self.name,
            "extensions": list(self.extensions),
            "build": self.can_build,
            "run": self.can_run,
            **st,
        }
        self._status_cache = (now, info)
        return info

    def detect_project(self, project_dir: Path) -> bool:
        return any(project_dir.rglob(f"*{self.extensions[0]}")) if self.extensions else False

    def runtime_dirs(self) -> list[Path]:
        from backend.core.sandbox import runtime_root

        exe = self.executable()
        root = runtime_root(exe) if exe else None
        return [root] if root else []

    def require(self) -> str:
        exe = self.executable()
        if not exe:
            from backend.core.exceptions import ServiceUnavailable

            raise ServiceUnavailable(f"Engine {self.name} belum terpasang di server (NOT_INSTALLED)", code="engine_unavailable")
        return exe

    @abstractmethod
    def build_steps(self, ctx: EngineContext) -> list[Step]: ...

    @abstractmethod
    def run_steps(self, ctx: EngineContext) -> list[Step]: ...

    # helper
    def step(self, phase: str, argv: list[str], ctx: EngineContext, *, cwd: Path | None = None, env=None, network=False) -> Step:
        return Step(
            phase=phase,
            argv=argv,
            timeout=ctx.build_timeout if phase == "build" else ctx.run_timeout,
            cwd=cwd or ctx.file.parent,
            env=env or {},
            address_space_limit=self.address_space_limit,
            network=network or ctx.network,
        )


def java_main_class(source: str, stem: str) -> str:
    m = re.search(r"^\s*package\s+([\w.]+)\s*;", source, re.MULTILINE)
    return f"{m.group(1)}.{stem}" if m else stem
