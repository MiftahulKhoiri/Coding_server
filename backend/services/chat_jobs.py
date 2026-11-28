"""Jawaban AI Chat sebagai pekerjaan di server, terlepas dari koneksi aplikasi.

Sebelumnya jawaban berjalan di dalam koneksi WebSocket: aplikasi ditutup / HP mati = jawaban dibatalkan, dan bila
koneksi putus tanpa pemberitahuan (HP mati mendadak) model lokal tetap sibuk sehingga pertanyaan berikutnya macet.
Sekarang setiap jawaban adalah ChatJob:
* tetap berjalan sampai selesai walau aplikasi ditutup; hasilnya disimpan ke percakapan (oleh AIService.chat_stream);
* aplikasi bisa menyambung lagi (attach) dan menerima ulang semua event dari awal, lalu lanjut secara langsung;
* hanya dihentikan oleh tombol Stop, "Paksa lepas" model, atau batas waktu.
Satu pengguna hanya punya satu jawaban berjalan (model lokal Pi melayani satu permintaan pada satu waktu).
"""
from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator, Callable

from backend.core.exceptions import AppError
from backend.core.logging import get_logger

log = get_logger("chat_jobs")

KEEP_FINISHED = 600       # detik: job selesai masih bisa di-attach (replay) sebelum dibuang
MAX_EVENTS = 50_000       # batas buffer replay (token streaming)
END = object()            # penanda akhir untuk pelanggan


class ChatJob:
    def __init__(self, user_id: int, conversation_id: int | None):
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.events: list[dict] = []
        self.subscribers: set[asyncio.Queue] = set()
        self.done = False
        self.started = time.time()
        self.finished: float | None = None
        self.task: asyncio.Task | None = None

    def publish(self, ev: dict) -> None:
        if ev.get("type") == "conversation":
            self.conversation_id = ev.get("id")
        elif ev.get("conversation_id") and not self.conversation_id:
            self.conversation_id = ev["conversation_id"]
        if len(self.events) < MAX_EVENTS:
            self.events.append(ev)
        for q in list(self.subscribers):
            q.put_nowait(ev)

    def finish(self) -> None:
        self.done = True
        self.finished = time.time()
        for q in list(self.subscribers):
            q.put_nowait(END)

    async def follow(self) -> AsyncIterator[dict]:
        """Semua event dari awal (replay) lalu event baru sampai job selesai."""
        q: asyncio.Queue = asyncio.Queue()
        for ev in self.events:
            q.put_nowait(ev)
        if self.done:
            q.put_nowait(END)
        else:
            self.subscribers.add(q)
        try:
            while True:
                ev = await q.get()
                if ev is END:
                    return
                yield ev
        finally:
            self.subscribers.discard(q)


class ChatJobs:
    def __init__(self):
        self.jobs: list[ChatJob] = []

    def _gc(self) -> None:
        now = time.time()
        self.jobs = [j for j in self.jobs if not j.done or (j.finished or now) > now - KEEP_FINISHED]

    def running_for_user(self, user_id: int) -> ChatJob | None:
        return next((j for j in self.jobs if j.user_id == user_id and not j.done), None)

    def for_conversation(self, conversation_id: int, user_id: int) -> ChatJob | None:
        """Job terbaru percakapan ini (berjalan, atau selesai < 10 menit lalu)."""
        self._gc()
        cands = [j for j in self.jobs if j.conversation_id == conversation_id and j.user_id == user_id]
        return cands[-1] if cands else None

    def generating(self, conversation_id: int) -> bool:
        return any(j.conversation_id == conversation_id and not j.done for j in self.jobs)

    def start(self, user: dict, conversation_id: int | None, run: Callable[[], AsyncIterator[dict]]) -> ChatJob:
        self._gc()
        busy = self.running_for_user(user["id"])
        if busy:
            raise AppError("AI masih menjawab pertanyaan sebelumnya. Tunggu selesai atau tekan Stop.",
                           code="busy", status_code=409, details={"conversation_id": busy.conversation_id})
        job = ChatJob(user["id"], conversation_id)

        async def runner() -> None:
            try:
                async for ev in run():
                    job.publish(ev)
            except asyncio.CancelledError:
                job.publish({"type": "stopped"})
            except AppError as e:
                job.publish({"type": "error", "code": e.code, "message": e.message})
            except Exception as e:  # jangan biarkan pelanggan menunggu tanpa akhir
                log.exception("Chat AI gagal")
                job.publish({"type": "error", "code": "internal", "message": str(e)})
            finally:
                job.finish()

        job.task = asyncio.create_task(runner())
        self.jobs.append(job)
        return job

    def stop(self, job: ChatJob) -> bool:
        if job.task and not job.done:
            job.task.cancel()
            return True
        return False

    async def cancel_all(self) -> int:
        """Untuk "Paksa lepas semua model": hentikan semua jawaban yang sedang berjalan."""
        running = [j for j in self.jobs if not j.done and j.task]
        for j in running:
            j.task.cancel()
        for j in running:
            try:
                await asyncio.wait_for(asyncio.shield(j.task), 10)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass
        return len(running)
