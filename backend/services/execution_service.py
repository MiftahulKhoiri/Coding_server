"""Execution Manager: membuat job, mengantre, menjalankan engine dalam sandbox, streaming output."""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from backend.config import Settings
from backend.core.exceptions import AppError, NotFound
from backend.core.job_queue import JobQueue
from backend.core.logging import get_logger
from backend.core.process_manager import RunningProcess, run_step
from backend.core.sandbox import Limits, SandboxSpec, make_preexec, require_sandbox, wrap
from backend.database.db import Database
from backend.engines.base_engine import EngineContext
from backend.engines.registry import EngineRegistry

log = get_logger("execution")

TERMINAL_STATES = {"COMPLETED", "FAILED", "TIMEOUT", "CANCELLED"}


@dataclass
class Job:
    id: str
    project_id: str
    user_id: int
    action: str
    language: str
    file: str
    status: str = "QUEUED"
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    truncated: bool = False
    error: str = ""
    command: list[list[str]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    start_time: float | None = None
    end_time: float | None = None
    events: list[dict] = field(default_factory=list)
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    handle: RunningProcess = field(default_factory=RunningProcess)
    task: asyncio.Task | None = None
    preview_path: str | None = None
    out_bytes: int = 0

    @property
    def duration(self) -> float | None:
        if self.start_time is None:
            return None
        return round((self.end_time or time.time()) - self.start_time, 3)

    def public(self, include_output: bool = True) -> dict:
        d = {
            "process_id": self.id, "project_id": self.project_id, "user_id": self.user_id,
            "action": self.action, "language": self.language, "file": self.file, "status": self.status,
            "exit_code": self.exit_code, "command": self.command, "error": self.error,
            "created_at": self.created_at, "start_time": self.start_time, "end_time": self.end_time,
            "duration": self.duration, "truncated": self.truncated, "preview_path": self.preview_path,
        }
        if include_output:
            d["stdout"] = self.stdout
            d["stderr"] = self.stderr
        return d


class _CommandEngine:
    """Pengganti engine untuk submit_command: tanpa runtime tambahan di luar sistem."""

    language_id = "command"

    @staticmethod
    def extra_writable() -> list[Path]:
        return []

    @staticmethod
    def runtime_dirs() -> list[Path]:
        return []


class ExecutionService:
    def __init__(self, settings: Settings, db: Database, registry: EngineRegistry):
        self.s = settings
        self.db = db
        self.registry = registry
        self.queue = JobQueue(settings.max_concurrent_jobs, settings.max_queued_jobs, settings.min_free_memory_mb)
        self.jobs: dict[str, Job] = {}
        # Job yang tertinggal (server mati saat berjalan) ditandai gagal.
        self.db.execute(
            "UPDATE executions SET status='FAILED', error='Server berhenti saat job berjalan' "
            "WHERE status IN ('QUEUED','STARTING','RUNNING')"
        )

    # ---------- event ----------
    async def _emit(self, job: Job, event: dict) -> None:
        job.events.append(event)
        if len(job.events) > 5000:
            job.events = job.events[-4000:]
        for q in list(job.subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    async def _set_status(self, job: Job, status: str) -> None:
        job.status = status
        await self._emit(job, {"type": "status", "status": status, "time": time.time()})

    async def _output(self, job: Job, stream: str, text: str) -> None:
        limit = self.s.output_limit_bytes
        if job.out_bytes >= limit:
            if not job.truncated:
                job.truncated = True
                note = f"\n[output dipotong: melebihi {limit} byte]\n"
                job.stderr += note
                await self._emit(job, {"type": "stderr", "data": note})
            return
        room = limit - job.out_bytes
        enc = text.encode()
        if len(enc) > room:
            text = enc[:room].decode(errors="ignore")
        job.out_bytes += len(text.encode())
        if stream == "stdout":
            job.stdout += text
        else:
            job.stderr += text
        await self._emit(job, {"type": stream, "data": text})

    def subscribe(self, job: Job) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=10000)
        for e in job.events:
            q.put_nowait(e)
        if job.status in TERMINAL_STATES:
            q.put_nowait({"type": "end", "job": job.public(include_output=False)})
        else:
            job.subscribers.add(q)
        return q

    def unsubscribe(self, job: Job, q: asyncio.Queue) -> None:
        job.subscribers.discard(q)

    # ---------- persistensi ----------
    def _save(self, job: Job) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO executions(id, project_id, user_id, action, language, file, command, status, exit_code,"
            " stdout, stderr, truncated, error, created_at, start_time, end_time, duration) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (job.id, job.project_id, job.user_id, job.action, job.language, job.file, json.dumps(job.command), job.status,
             job.exit_code, job.stdout, job.stderr, int(job.truncated), job.error, job.created_at, job.start_time,
             job.end_time, job.duration),
        )

    # ---------- API ----------
    def get(self, process_id: str) -> Job | dict:
        job = self.jobs.get(process_id)
        if job:
            return job
        row = self.db.one("SELECT * FROM executions WHERE id=?", (process_id,))
        if not row:
            raise NotFound("Proses tidak ditemukan")
        row["process_id"] = row.pop("id")
        row["command"] = json.loads(row["command"] or "[]")
        row["truncated"] = bool(row["truncated"])
        return row

    def list(self, user: dict, project_id: str | None = None, limit: int = 50) -> list[dict]:
        where, params = [], []
        if "admin" not in user["perms"]:
            where.append("user_id=?")
            params.append(user["id"])
        if project_id:
            where.append("project_id=?")
            params.append(project_id)
        sql = "SELECT id, project_id, user_id, action, language, file, status, exit_code, created_at, start_time, end_time, duration, error FROM executions"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self.db.all(sql, tuple(params))
        for r in rows:
            r["process_id"] = r.pop("id")
            live = self.jobs.get(r["process_id"])
            if live:
                r["status"] = live.status
        return rows

    def active(self) -> list[dict]:
        return [j.public(include_output=False) for j in self.jobs.values() if j.status not in TERMINAL_STATES]

    async def submit(self, *, user: dict, project_id: str, project_dir: Path, file_rel: str, action: str,
                     language: str | None = None, args: list[str] | None = None, stdin: str | None = None,
                     interactive: bool = False, timeout: int | None = None) -> Job:
        from backend.services.file_service import FileService

        fs = FileService(self.s, self.db)
        src = fs.resolve(project_dir, file_rel, must_exist=True, allow_root=False)
        if not src.is_file():
            raise AppError("Target harus berupa file", code="not_a_file")
        engine = self.registry.get(language) if language else self.registry.for_file(src)
        if engine is None:
            raise AppError(f"Tidak ada engine untuk file '{src.name}'", code="no_engine")
        if src.suffix.lower() not in engine.extensions:
            raise AppError(f"Engine {engine.name} tidak mendukung ekstensi {src.suffix}", code="bad_extension")
        status = engine.get_status()
        if status["status"] != "AVAILABLE":
            raise AppError(f"Engine {engine.name}: {status['status']}", code="engine_unavailable", status_code=503)
        args = [str(a) for a in (args or [])][:64]
        self.queue.check_admission()

        job = Job(id=uuid.uuid4().hex[:16], project_id=project_id, user_id=user["id"], action=action,
                  language=engine.language_id, file=fs.rel_of(project_dir.resolve(), src))
        self.jobs[job.id] = job
        self._save(job)
        await self._emit(job, {"type": "status", "status": "QUEUED", "time": time.time()})

        if engine.language_id == "web":
            job.preview_path = job.file
            job.start_time = job.end_time = time.time()
            job.exit_code = 0
            await self._output(job, "stdout", f"Pratinjau siap: buka /preview untuk {job.file}\n")
            await self._finish(job, "COMPLETED")
            return job

        require_sandbox(self.s)
        build_dir = self.s.cache_dir / "builds" / project_id / engine.language_id / src.stem
        build_dir.mkdir(parents=True, exist_ok=True)
        ctx = EngineContext(
            project_dir=project_dir.resolve(), file=src.resolve(), build_dir=build_dir, cache_dir=self.s.cache_dir / "lang",
            args=args, run_timeout=min(timeout or self.s.run_timeout, self.s.run_timeout * 10),
            build_timeout=self.s.build_timeout, memory_mb=self.s.memory_limit_mb, network=self.s.sandbox_network,
        )
        try:
            ctx = engine.prepare_context(ctx)
            ctx.build_dir.mkdir(parents=True, exist_ok=True)
            steps = engine.build_steps(ctx) if action == "build" else engine.run_steps(ctx)
        except AppError:
            self.jobs.pop(job.id, None)
            raise
        job.command = [s.argv for s in steps]
        job.task = asyncio.create_task(self._run(job, engine, ctx, steps, stdin, interactive))
        return job

    async def submit_command(self, *, user: dict, project_id: str, project_dir: Path, argv: list[str],
                             action: str, label: str, env: dict[str, str] | None = None,
                             timeout: int | None = None) -> Job:
        """Jalankan satu perintah yang argv-nya DISUSUN SERVER (mis. perintah uji hasil deteksi).

        Memakai antrean, sandbox (fail-closed), batas sumber daya, riwayat & streaming yang sama
        dengan run/build biasa. Jangan pernah meneruskan argv mentah dari pengguna/model ke sini.
        """
        t = min(timeout or self.s.build_timeout, self.s.build_timeout)
        return await self.submit_commands(user=user, project_id=project_id, project_dir=project_dir,
                                          commands=[(list(argv), dict(env or {}))], action=action, label=label,
                                          timeout=t, network=self.s.sandbox_network)

    async def submit_commands(self, *, user: dict, project_id: str, project_dir: Path,
                              commands: list[tuple[list[str], dict[str, str]]], action: str, label: str,
                              timeout: int, network: bool = False) -> Job:
        """Seperti submit_command, tetapi beberapa perintah berurutan dalam satu job (berhenti di yang
        gagal). ``network`` hanya untuk perintah buatan server yang memang butuh internet (instal
        dependensi); program pengguna tetap memakai ``sandbox_network``."""
        from backend.engines.base_engine import Step

        if not commands:
            raise AppError("Tidak ada perintah untuk dijalankan", code="no_command")
        require_sandbox(self.s)
        self.queue.check_admission()
        root = project_dir.resolve()
        build_dir = self.s.cache_dir / "builds" / project_id / action
        build_dir.mkdir(parents=True, exist_ok=True)
        ctx = EngineContext(project_dir=root, file=root, build_dir=build_dir, cache_dir=self.s.cache_dir / "lang",
                            args=[], run_timeout=timeout, build_timeout=timeout, memory_mb=self.s.memory_limit_mb,
                            network=network)
        steps = [Step(phase="run", argv=list(argv), timeout=timeout, cwd=root, env=dict(env or {}), network=network)
                 for argv, env in commands]
        job = Job(id=uuid.uuid4().hex[:16], project_id=project_id, user_id=user["id"], action=action,
                  language=label, file="", command=[list(a) for a, _ in commands])
        self.jobs[job.id] = job
        self._save(job)
        await self._emit(job, {"type": "status", "status": "QUEUED", "time": time.time()})
        job.task = asyncio.create_task(self._run(job, _CommandEngine(), ctx, steps, None, False))
        return job

    async def wait(self, job: Job, timeout: float | None = None) -> Job:
        """Tunggu job selesai (status terminal). Bila pemanggil dibatalkan, job ikut dihentikan."""
        q = self.subscribe(job)
        try:
            async def _until_end() -> None:
                while True:
                    ev = await q.get()
                    if ev.get("type") == "end":
                        return
            await asyncio.wait_for(_until_end(), timeout)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            await self.stop(job.id)
            raise
        finally:
            self.unsubscribe(job, q)
        return job

    async def _run(self, job: Job, engine, ctx: EngineContext, steps, stdin, interactive) -> None:
        acquired = False
        try:
            await self.queue.acquire()
            acquired = True
        except asyncio.CancelledError:
            # A queued job may be cancelled while waiting for a semaphore slot.
            job.error = "Dibatalkan sebelum berjalan"
            await self._finish(job, "CANCELLED")
            return
        except AppError as e:
            job.error = e.message
            await self._finish(job, "FAILED")
            return

        try:
            if job.handle.cancel_event.is_set():
                await self._finish(job, "CANCELLED")
                return
            await self._set_status(job, "STARTING")
            job.start_time = time.time()
            sandbox_on = self.s.sandbox_enabled
            ctx.cache_dir.mkdir(parents=True, exist_ok=True)
            final_status = "COMPLETED"
            for i, step in enumerate(steps):
                if job.handle.cancel_event.is_set():
                    job.error = "Dihentikan oleh pengguna"
                    final_status = "CANCELLED"
                    break
                if job.status != "RUNNING":
                    await self._set_status(job, "RUNNING")
                if step.resolve is not None:
                    try:
                        step.argv = step.resolve()
                    except AppError as e:
                        job.error = e.message
                        final_status = "FAILED"
                        break
                    job.command = [s.argv for s in steps]
                await self._emit(job, {"type": "phase", "phase": step.phase, "index": i, "argv": step.argv})
                spec = SandboxSpec(
                    cwd=step.cwd,
                    writable=[ctx.project_dir, ctx.build_dir, ctx.cache_dir, *engine.extra_writable()],
                    readonly=engine.runtime_dirs(),
                    network=step.network,
                    env=step.env,
                )
                argv, env = wrap(step.argv, spec, enabled=sandbox_on)
                limits = Limits(timeout=step.timeout, memory_mb=ctx.memory_mb, address_space_limit=step.address_space_limit)
                last = i == len(steps) - 1
                res = await run_step(
                    argv, cwd=str(step.cwd), env=env, preexec=make_preexec(limits), timeout=step.timeout,
                    memory_limit_mb=ctx.memory_mb, on_output=lambda s, t: self._output(job, s, t), handle=job.handle,
                    stdin_data=stdin if (step.phase == "run" and last) else None,
                    interactive=interactive and step.phase == "run" and last,
                )
                job.exit_code = res.exit_code
                if res.reason == "timeout":
                    job.error = res.message
                    final_status = "TIMEOUT"
                    break
                if res.reason == "cancelled":
                    job.error = res.message
                    final_status = "CANCELLED"
                    break
                if res.reason in ("memory", "error"):
                    job.error = res.message
                    final_status = "FAILED"
                    break
                if res.exit_code != 0:
                    if step.phase == "build":
                        job.error = "Kompilasi/pemeriksaan gagal"
                    final_status = "FAILED"
                    break
            if job.error:
                await self._output(job, "stderr", f"\n[{job.error}]\n")
            await self._finish(job, final_status)
        except asyncio.CancelledError:
            # Cancellation after acquiring must still terminate any child process
            # and persist a terminal state before releasing the queue slot.
            job.handle.cancel_event.set()
            if job.handle.proc and job.handle.proc.returncode is None:
                from backend.core.process_manager import kill_tree
                kill_tree(job.handle.proc.pid)
                try:
                    await asyncio.wait_for(job.handle.proc.wait(), timeout=3)
                except asyncio.TimeoutError:
                    pass
            job.error = "Dibatalkan sebelum proses selesai"
            await self._finish(job, "CANCELLED")
            raise
        except Exception as e:  # jangan biarkan job menggantung
            log.exception("Job %s error", job.id)
            job.error = f"Kesalahan internal: {e}"
            await self._finish(job, "FAILED")
        finally:
            if acquired:
                self.queue.release()

    async def _finish(self, job: Job, status: str) -> None:
        job.end_time = time.time()
        await self._set_status(job, status)
        self._save(job)
        end = {"type": "end", "job": job.public(include_output=False)}
        for q in list(job.subscribers):
            try:
                q.put_nowait(end)
            except asyncio.QueueFull:
                pass
        job.subscribers.clear()
        # Simpan maksimal 200 job terakhir di memori.
        if len(self.jobs) > 200:
            for jid in [k for k, v in self.jobs.items() if v.status in TERMINAL_STATES][: len(self.jobs) - 200]:
                self.jobs.pop(jid, None)

    async def stop(self, process_id: str) -> dict:
        job = self.jobs.get(process_id)
        if not job:
            raise NotFound("Proses tidak aktif")
        if job.status in TERMINAL_STATES:
            return job.public(include_output=False)
        job.handle.cancel_event.set()
        if job.status == "QUEUED" and job.task:
            # Let _run own the state transition. If cancellation arrived before
            # the coroutine's first instruction, finalize here as a fallback.
            job.task.cancel()
            try:
                await job.task
            except asyncio.CancelledError:
                pass
            if job.status not in TERMINAL_STATES:
                job.error = "Dibatalkan sebelum berjalan"
                await self._finish(job, "CANCELLED")
        return job.public(include_output=False)

    async def send_input(self, process_id: str, data: str, eof: bool = False) -> bool:
        job = self.jobs.get(process_id)
        if not job or job.status in TERMINAL_STATES:
            return False
        return await job.handle.write_stdin(data, close=eof)

    async def shutdown(self) -> None:
        for job in self.jobs.values():
            if job.status not in TERMINAL_STATES:
                job.handle.cancel_event.set()
