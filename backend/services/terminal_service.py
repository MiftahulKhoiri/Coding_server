"""Terminal interaktif berbasis PTY, dijalankan di dalam sandbox bwrap (bila tersedia).

Shell hanya melihat folder proyek (read-write) + sistem (read-only); $HOME diganti tmpfs
sehingga kunci SSH/token milik akun server tidak terlihat.
"""
from __future__ import annotations

import asyncio
import fcntl
import os
import pty
import signal
import struct
import termios
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from backend.config import Settings
from backend.core.exceptions import NotFound, ServiceUnavailable
from backend.core.logging import get_logger
from backend.core.process_manager import kill_tree
from backend.core.sandbox import Limits, SandboxSpec, wrap
from backend.engines.registry import get_registry

log = get_logger("terminal")


@dataclass
class TerminalSession:
    session_id: str
    owner_id: int
    project_id: str
    working_directory: str
    created_at: float
    last_activity: float
    pid: int
    fd: int
    status: str = "running"
    history: list[str] = field(default_factory=list)
    scrollback: bytearray = field(default_factory=bytearray)
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    exit_code: int | None = None
    _line: str = ""

    def public(self) -> dict:
        return {
            "session_id": self.session_id, "owner_id": self.owner_id, "project_id": self.project_id,
            "working_directory": self.working_directory, "created_at": self.created_at,
            "last_activity": self.last_activity, "status": self.status, "exit_code": self.exit_code,
            "history": self.history[-50:],
        }


class TerminalService:
    def __init__(self, settings: Settings):
        self.s = settings
        self.sessions: dict[str, TerminalSession] = {}
        self._reaper: asyncio.Task | None = None

    def start_reaper(self) -> None:
        if self._reaper is None:
            self._reaper = asyncio.create_task(self._reap_loop())

    async def _reap_loop(self) -> None:
        while True:
            await asyncio.sleep(30)
            now = time.time()
            for s in list(self.sessions.values()):
                idle = now - s.last_activity
                if s.status != "running" and idle > 300:
                    self.sessions.pop(s.session_id, None)
                elif s.status == "running" and idle > self.s.terminal_idle_timeout and not s.subscribers:
                    log.info("Menutup sesi terminal idle %s", s.session_id)
                    self.close(s.session_id)

    def list(self, user: dict) -> list[dict]:
        return [s.public() for s in self.sessions.values() if s.owner_id == user["id"] or "admin" in user["perms"]]

    def get(self, session_id: str, user: dict) -> TerminalSession:
        s = self.sessions.get(session_id)
        if not s or (s.owner_id != user["id"] and "admin" not in user["perms"]):
            raise NotFound("Sesi terminal tidak ditemukan")
        return s

    def create(self, user: dict, project_id: str, project_dir: Path, cwd: Path, cols: int = 80, rows: int = 24) -> TerminalSession:
        running = [s for s in self.sessions.values() if s.status == "running"]
        if len(running) >= self.s.max_terminal_sessions:
            raise ServiceUnavailable("Jumlah sesi terminal maksimum tercapai", code="too_many_sessions")
        registry = get_registry()
        ro = []
        for e in registry.all():
            for d in e.runtime_dirs():
                if d not in ro:
                    ro.append(d)
        spec = SandboxSpec(
            cwd=cwd, writable=[project_dir.resolve(), self.s.cache_dir / "lang"], readonly=ro,
            network=self.s.terminal_network, new_session=False,
            env={"PS1": r"\[\e[32m\]coding_server\[\e[0m\]:\[\e[34m\]\w\[\e[0m\]$ ", "HISTFILE": "/dev/null",
                 "GOCACHE": str(self.s.cache_dir / "lang" / "go-build"), "GOPATH": str(self.s.cache_dir / "lang" / "gopath"),
                 "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1",
                 "DOTNET_CLI_HOME": str(self.s.cache_dir / "lang" / "dotnet-home")},
        )
        (self.s.cache_dir / "lang").mkdir(parents=True, exist_ok=True)
        argv, env = wrap(["/bin/bash", "--noprofile", "--norc", "-i"], spec, enabled=self.s.sandbox_enabled)
        limits = Limits(timeout=self.s.terminal_idle_timeout, memory_mb=self.s.memory_limit_mb, cpu_seconds=24 * 3600)
        pid, fd = pty.fork()
        if pid == 0:  # anak
            try:
                os.chdir(cwd)
                os.nice(5)
                import resource

                resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
                fs = 1024 * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_FSIZE, (fs, fs))
                os.execvpe(argv[0], argv, env)
            except Exception as e:  # pragma: no cover
                os.write(2, f"gagal memulai shell: {e}\n".encode())
            finally:
                os._exit(127)
        _ = limits
        self._resize(fd, cols, rows)
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        now = time.time()
        sess = TerminalSession(uuid.uuid4().hex[:16], user["id"], project_id, str(cwd), now, now, pid, fd)
        self.sessions[sess.session_id] = sess
        asyncio.get_running_loop().add_reader(fd, self._on_readable, sess)
        log.info("Sesi terminal %s dibuat oleh %s di %s", sess.session_id, user["username"], cwd)
        return sess

    @staticmethod
    def _resize(fd: int, cols: int, rows: int) -> None:
        try:
            fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", max(rows, 2), max(cols, 10), 0, 0))
        except OSError:
            pass

    def resize(self, sess: TerminalSession, cols: int, rows: int) -> None:
        self._resize(sess.fd, cols, rows)
        try:
            os.kill(sess.pid, signal.SIGWINCH)
        except ProcessLookupError:
            pass

    def _on_readable(self, sess: TerminalSession) -> None:
        try:
            data = os.read(sess.fd, 65536)
        except BlockingIOError:
            return
        except OSError:
            data = b""
        if not data:
            self._ended(sess)
            return
        sess.last_activity = time.time()
        sess.scrollback.extend(data)
        if len(sess.scrollback) > 200_000:
            del sess.scrollback[: len(sess.scrollback) - 150_000]
        for q in list(sess.subscribers):
            try:
                q.put_nowait({"type": "output", "data": data.decode("utf-8", errors="replace")})
            except asyncio.QueueFull:
                pass

    def _ended(self, sess: TerminalSession) -> None:
        if sess.status != "running":
            return
        try:
            asyncio.get_running_loop().remove_reader(sess.fd)
        except Exception:
            pass
        try:
            _, st = os.waitpid(sess.pid, os.WNOHANG)
            sess.exit_code = os.waitstatus_to_exitcode(st) if st else None
        except ChildProcessError:
            pass
        try:
            os.close(sess.fd)
        except OSError:
            pass
        sess.status = "exited"
        for q in list(sess.subscribers):
            q.put_nowait({"type": "exit", "exit_code": sess.exit_code})

    def write(self, sess: TerminalSession, data: str) -> None:
        if sess.status != "running":
            return
        sess.last_activity = time.time()
        for ch in data:  # catat riwayat perintah (perkiraan dari input baris)
            if ch in "\r\n":
                if sess._line.strip():
                    sess.history.append(sess._line.strip())
                    sess.history = sess.history[-200:]
                sess._line = ""
            elif ch == "\x7f":
                sess._line = sess._line[:-1]
            elif ch.isprintable():
                sess._line += ch
        try:
            os.write(sess.fd, data.encode())
        except OSError:
            self._ended(sess)

    def signal(self, sess: TerminalSession, sig: str) -> None:
        mapping = {"SIGINT": "\x03", "SIGTSTP": "\x1a", "EOF": "\x04"}
        if sig in mapping:
            self.write(sess, mapping[sig])

    def close(self, session_id: str) -> None:
        sess = self.sessions.get(session_id)
        if not sess:
            return
        if sess.status == "running":
            kill_tree(sess.pid, signal.SIGHUP)
            kill_tree(sess.pid, signal.SIGKILL)
            self._ended(sess)
        try:
            os.waitpid(sess.pid, os.WNOHANG)
        except ChildProcessError:
            pass
        sess.status = "closed"
        self.sessions.pop(session_id, None)

    def shutdown(self) -> None:
        for sid in list(self.sessions):
            self.close(sid)
        if self._reaper:
            self._reaper.cancel()
