"""Antrean job dengan batas jumlah job bersamaan dan pemeriksaan RAM bebas."""
from __future__ import annotations

import asyncio

import psutil

from backend.core.exceptions import ServiceUnavailable


class JobQueue:
    def __init__(self, max_concurrent: int, max_queued: int, min_free_memory_mb: int):
        self.max_concurrent = max(1, max_concurrent)
        self.max_queued = max(0, max_queued)
        self.min_free_memory_mb = max(0, min_free_memory_mb)
        self._sem = asyncio.Semaphore(self.max_concurrent)
        self.waiting = 0
        self.running = 0
        self._admission_lock = asyncio.Lock()

    def check_admission(self) -> None:
        if self.waiting >= self.max_queued:
            raise ServiceUnavailable(
                f"Antrean penuh ({self.waiting} job menunggu). Coba lagi nanti.", code="queue_full"
            )

    @staticmethod
    def free_memory_mb() -> int:
        return int(psutil.virtual_memory().available / 1024 / 1024)

    async def acquire(self, wait_memory_seconds: float = 30.0) -> None:
        # Lock menjaga admission count dan pengecekan kapasitas tetap atomik.
        async with self._admission_lock:
            if self.waiting >= self.max_queued and self._sem.locked():
                raise ServiceUnavailable(
                    f"Antrean penuh ({self.waiting} job menunggu). Coba lagi nanti.", code="queue_full"
                )
            self.waiting += 1

        acquired = False
        try:
            await self._sem.acquire()
            acquired = True
            waited = 0.0
            while self.free_memory_mb() < self.min_free_memory_mb:
                if waited >= wait_memory_seconds:
                    raise ServiceUnavailable(
                        f"RAM bebas tinggal {self.free_memory_mb()} MB (< {self.min_free_memory_mb} MB). "
                        "Job ditolak agar Raspberry Pi tetap stabil.",
                        code="low_memory",
                    )
                await asyncio.sleep(min(1.0, max(0.0, wait_memory_seconds - waited)))
                waited += 1.0
            self.running += 1
        except BaseException:
            if acquired:
                self._sem.release()
            raise
        finally:
            async with self._admission_lock:
                self.waiting = max(0, self.waiting - 1)

    def release(self) -> None:
        # Pemanggil hanya boleh release setelah acquire berhasil.
        if self.running <= 0:
            raise RuntimeError("JobQueue.release() tanpa acquire aktif")
        self.running -= 1
        self._sem.release()

    def stats(self) -> dict:
        return {"max_concurrent": self.max_concurrent, "running": self.running, "waiting": self.waiting}
