import asyncio

import pytest

from backend.core.exceptions import ServiceUnavailable
from backend.core.job_queue import JobQueue


def test_cancelled_waiter_does_not_leak_queue_capacity(monkeypatch):
    async def scenario():
        monkeypatch.setattr(JobQueue, "free_memory_mb", staticmethod(lambda: 1024))
        queue = JobQueue(max_concurrent=1, max_queued=1, min_free_memory_mb=1)
        await queue.acquire()
        blocked = asyncio.create_task(queue.acquire())
        await asyncio.sleep(0)
        assert queue.stats() == {"max_concurrent": 1, "running": 1, "waiting": 1}
        blocked.cancel()
        with pytest.raises(asyncio.CancelledError):
            await blocked
        assert queue.stats() == {"max_concurrent": 1, "running": 1, "waiting": 0}
        queue.release()
        await queue.acquire()
        queue.release()

    asyncio.run(scenario())


def test_memory_rejection_releases_acquired_slot(monkeypatch):
    async def scenario():
        monkeypatch.setattr(JobQueue, "free_memory_mb", staticmethod(lambda: 0))
        queue = JobQueue(max_concurrent=1, max_queued=1, min_free_memory_mb=10)
        with pytest.raises(ServiceUnavailable) as exc:
            await queue.acquire(wait_memory_seconds=0)
        assert exc.value.code == "low_memory"
        assert queue.stats() == {"max_concurrent": 1, "running": 0, "waiting": 0}
        monkeypatch.setattr(JobQueue, "free_memory_mb", staticmethod(lambda: 1024))
        await queue.acquire(wait_memory_seconds=0)
        queue.release()
        assert queue.stats() == {"max_concurrent": 1, "running": 0, "waiting": 0}

    asyncio.run(scenario())


def test_queue_limit_counts_waiting_jobs_not_running_jobs(monkeypatch):
    async def scenario():
        monkeypatch.setattr(JobQueue, "free_memory_mb", staticmethod(lambda: 1024))
        queue = JobQueue(max_concurrent=1, max_queued=1, min_free_memory_mb=1)
        await queue.acquire()
        waiter = asyncio.create_task(queue.acquire())
        await asyncio.sleep(0)
        with pytest.raises(ServiceUnavailable) as exc:
            await queue.acquire()
        assert exc.value.code == "queue_full"
        queue.release()
        await waiter
        queue.release()
        assert queue.stats() == {"max_concurrent": 1, "running": 0, "waiting": 0}

    asyncio.run(scenario())
