"""Antrean job dengan batas jumlah job bersamaan dan pemeriksaan RAM bebas."""
from __future__ import annotations

import asyncio

import psutil

from backend.core.exceptions import ServiceUnavailable


class JobQueue:
    def __init__(self, max_concurrent: int, max_queued: int, min_free_memory_mb: int):
        self.max_concurrent = max(1, max_concurrent)
        self.max_queued = max_queued
        self.min_free_memory_mb = min_free_memory_mb
        self._sem = asyncio.Semaphore(self.max_concurrent)
        self.waiting = 0
        self.running = 0

    def check_admission(self) -> None:
        if self.waiting >= self.max_queued:
            raise ServiceUnavailable(
                f"Antrean penuh ({self.waiting} job menunggu). Coba lagi nanti.", code="queue_full"
            )

    @staticmethod
    def free_memory_mb() -> int:
        return int(psutil.virtual_memory().available / 1024 / 1024)

    async def acquire(self, wait_memory_seconds: float = 30.0) -> None:
        self.waiting += 1
        try:
            await self._sem.acquire()
        finally:
            self.waiting -= 1
        # Tunda bila RAM hampir habis; tolak bila tetap kurang.
        waited = 0.0
        while self.free_memory_mb() < self.min_free_memory_mb:
            if waited >= wait_memory_seconds:
                self._sem.release()
                raise ServiceUnavailable(
                    f"RAM bebas tinggal {self.free_memory_mb()} MB (< {self.min_free_memory_mb} MB). "
                    "Job ditolak agar Raspberry Pi tetap stabil.",
                    code="low_memory",
                )
            await asyncio.sleep(1.0)
            waited += 1.0
        self.running += 1

    def release(self) -> None:
        self.running -= 1
        self._sem.release()

    def stats(self) -> dict:
        return {"max_concurrent": self.max_concurrent, "running": self.running, "waiting": self.waiting}
