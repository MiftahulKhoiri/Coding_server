"""Isolasi proses dengan bubblewrap (bwrap) + batas sumber daya (rlimit).

Pembatasan direktori saja BUKAN sandbox. Bila bwrap tersedia, setiap program pengguna
dijalankan di namespace terpisah:
  * filesystem sistem read-only, $HOME diganti tmpfs kosong (kunci SSH, token, dsb tidak terlihat)
  * hanya folder proyek (dan cache compiler) yang bisa ditulis
  * jaringan diputus (kecuali diizinkan), PID/IPC/UTS terpisah, mati bersama induk
"""
from __future__ import annotations

import os
import resource
import shutil
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from backend.core.exceptions import ServiceUnavailable


@lru_cache
def bwrap_path() -> str | None:
    return shutil.which("bwrap")


@lru_cache
def bwrap_available() -> bool:
    exe = bwrap_path()
    if not exe:
        return False
    try:
        r = subprocess.run(
            [exe, "--ro-bind", "/", "/", "--unshare-all", "--die-with-parent", "true"],
            capture_output=True, timeout=10,
        )
        return r.returncode == 0
    except Exception:
        return False



def require_sandbox(settings) -> None:
    """Fail closed: never silently run user code without isolation in auto/bwrap modes."""
    if settings.sandbox == "none":
        return
    if not bwrap_available():
        raise ServiceUnavailable(
            "Bubblewrap sandbox tidak tersedia. Instal/aktifkan bwrap; mode tanpa sandbox hanya boleh dipilih secara eksplisit (CS_SANDBOX=none).",
            code="sandbox_unavailable",
        )


def runtime_root(executable: str) -> Path | None:
    """Folder instalasi runtime yang berada di $HOME (mis. ~/.dotnet, ~/.local/opt/php)."""
    real = Path(os.path.realpath(executable))
    parent = real.parent
    if parent.name == "bin":
        parent = parent.parent
    home = Path.home()
    try:
        parent.relative_to(home)
    except ValueError:
        return None
    return parent


@dataclass
class Limits:
    timeout: int = 60
    memory_mb: int = 1024
    address_space_limit: bool = False  # RLIMIT_AS; tidak cocok untuk JVM/V8/Go/.NET
    cpu_seconds: int | None = None
    file_size_mb: int = 256
    nice: int = 10


def make_preexec(limits: Limits):
    def _preexec() -> None:  # dijalankan di proses anak sebelum exec
        try:
            os.nice(limits.nice)
        except OSError:
            pass
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        fs = limits.file_size_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_FSIZE, (fs, fs))
        cpu = limits.cpu_seconds or (limits.timeout * 2 + 5)
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 5))
        if limits.address_space_limit:
            mem = limits.memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem, mem))

    return _preexec


@dataclass
class SandboxSpec:
    cwd: Path
    writable: list[Path] = field(default_factory=list)
    readonly: list[Path] = field(default_factory=list)
    network: bool = False
    env: dict[str, str] = field(default_factory=dict)
    new_session: bool = True


BASE_ENV = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "TERM": "xterm-256color",
}


def wrap(argv: list[str], spec: SandboxSpec, *, enabled: bool) -> tuple[list[str], dict[str, str]]:
    """Kembalikan (argv final, env) untuk dijalankan."""
    home = str(Path.home())
    env = dict(BASE_ENV)
    env["HOME"] = home
    env.update(spec.env)
    extra_paths = [str(p / "bin") if (p / "bin").is_dir() else str(p) for p in spec.readonly if p.is_dir()]
    if extra_paths:
        env["PATH"] = ":".join(extra_paths + [env["PATH"]])
    if not enabled:
        return argv, env

    args: list[str] = [bwrap_path() or "bwrap"]
    args += ["--ro-bind", "/usr", "/usr"]
    for d in ("/bin", "/sbin", "/lib", "/lib64", "/lib32"):
        if os.path.islink(d):
            args += ["--symlink", os.readlink(d), d]
        elif os.path.isdir(d):
            args += ["--ro-bind", d, d]
    args += ["--ro-bind", "/etc", "/etc"]
    for d in ("/opt", "/run/systemd/resolve", "/srv"):
        args += ["--ro-bind-try", d, d]
    args += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/dev/shm", "--tmpfs", "/tmp", "--tmpfs", home]
    for p in spec.readonly:
        args += ["--ro-bind", str(p), str(p)]
    for p in spec.writable:
        p.mkdir(parents=True, exist_ok=True)
        args += ["--bind", str(p), str(p)]
    args += ["--unshare-all"]
    if spec.network:
        args += ["--share-net"]
    args += ["--die-with-parent"]
    if spec.new_session:
        args += ["--new-session"]
    args += ["--clearenv"]
    for k, v in env.items():
        args += ["--setenv", k, v]
    args += ["--chdir", str(spec.cwd), "--"]
    return args + argv, env
