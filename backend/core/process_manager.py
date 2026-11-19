"""Menjalankan proses dengan timeout, batas memori (watchdog RSS), batas output, dan pembatalan."""
from __future__ import annotations

import asyncio
import codecs
import os
import signal
import time
from dataclasses import dataclass
from typing import Awaitable, Callable

import psutil

OutputCallback = Callable[[str, str], Awaitable[None]]  # (stream, text)


@dataclass
class StepResult:
    exit_code: int | None
    reason: str  # ok | timeout | cancelled | memory | error
    duration: float
    message: str = ""


def _tree_rss_mb(pid: int) -> float:
    try:
        p = psutil.Process(pid)
        procs = [p] + p.children(recursive=True)
    except psutil.Error:
        return 0.0
    total = 0
    for c in procs:
        try:
            total += c.memory_info().rss
        except psutil.Error:
            pass
    return total / 1024 / 1024


def kill_tree(pid: int, sig: int = signal.SIGKILL) -> None:
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
    except psutil.Error:
        children = []
    try:
        os.killpg(pid, sig)
    except (ProcessLookupError, PermissionError):
        pass
    for c in children:
        try:
            c.send_signal(sig)
        except psutil.Error:
            pass


class RunningProcess:
    def __init__(self) -> None:
        self.proc: asyncio.subprocess.Process | None = None
        self.cancel_event = asyncio.Event()
        self.stdin_lock = asyncio.Lock()

    async def write_stdin(self, data: str, close: bool = False) -> bool:
        p = self.proc
        if p is None or p.stdin is None or p.stdin.is_closing():
            return False
        async with self.stdin_lock:
            try:
                if data:
                    p.stdin.write(data.encode())
                    await p.stdin.drain()
                if close:
                    p.stdin.close()
                return True
            except (BrokenPipeError, ConnectionResetError):
                return False


async def run_step(
    argv: list[str],
    *,
    cwd: str,
    env: dict[str, str],
    preexec,
    timeout: float,
    memory_limit_mb: int,
    on_output: OutputCallback,
    handle: RunningProcess,
    stdin_data: str | None = None,
    interactive: bool = False,
) -> StepResult:
    start = time.monotonic()
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            preexec_fn=preexec,
            start_new_session=True,
        )
    except FileNotFoundError as e:
        return StepResult(None, "error", 0.0, f"Executable tidak ditemukan: {e.filename}")
    except OSError as e:
        return StepResult(None, "error", 0.0, f"Gagal menjalankan proses: {e}")
    handle.proc = proc

    if stdin_data:
        await handle.write_stdin(stdin_data, close=not interactive)
    elif not interactive and proc.stdin:
        proc.stdin.close()

    async def pump(stream: asyncio.StreamReader, name: str) -> None:
        dec = codecs.getincrementaldecoder("utf-8")(errors="replace")
        while True:
            chunk = await stream.read(4096)
            if not chunk:
                tail = dec.decode(b"", final=True)
                if tail:
                    await on_output(name, tail)
                return
            text = dec.decode(chunk)
            if text:
                await on_output(name, text)

    reason = "ok"
    message = ""

    async def watchdog() -> str:
        nonlocal message
        while True:
            await asyncio.sleep(0.5)
            if handle.cancel_event.is_set():
                return "cancelled"
            if time.monotonic() - start > timeout:
                message = f"Melebihi batas waktu {int(timeout)} detik"
                return "timeout"
            rss = _tree_rss_mb(proc.pid)
            if rss > memory_limit_mb:
                message = f"Memakai {rss:.0f} MB RAM, melebihi batas {memory_limit_mb} MB"
                return "memory"

    pumps = asyncio.gather(pump(proc.stdout, "stdout"), pump(proc.stderr, "stderr"))  # type: ignore[arg-type]
    waiter = asyncio.ensure_future(proc.wait())
    dog = asyncio.ensure_future(watchdog())
    done, _ = await asyncio.wait({waiter, dog}, return_when=asyncio.FIRST_COMPLETED)
    if dog in done and waiter not in done:
        reason = dog.result()
        kill_tree(proc.pid, signal.SIGTERM)
        try:
            await asyncio.wait_for(asyncio.shield(waiter), 2.0)
        except asyncio.TimeoutError:
            kill_tree(proc.pid, signal.SIGKILL)
            await waiter
    else:
        dog.cancel()
    try:
        await asyncio.wait_for(pumps, 5.0)
    except asyncio.TimeoutError:
        pumps.cancel()
    # Bersihkan sisa proses anak (mis. proses latar belakang yang ditinggal program).
    kill_tree(proc.pid, signal.SIGKILL)
    if reason == "cancelled":
        message = "Dihentikan oleh pengguna"
    return StepResult(proc.returncode, reason, time.monotonic() - start, message)
