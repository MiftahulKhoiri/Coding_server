import time

from fastapi import APIRouter, Depends

from backend.config import VERSION
from backend.dependencies import Services, current_user, require, services

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health", summary="Status backend (tanpa autentikasi)")
def health(svc: Services = Depends(services)):
    try:
        svc.db.one("SELECT 1 AS ok")
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "version": VERSION, "time": time.time(), "database": db_ok,
            "sandbox": svc.settings.sandbox_enabled, "name": "CODING_SERVER"}


@router.get("/info")
def info(_: dict = Depends(current_user), svc: Services = Depends(services)):
    return svc.monitor.info()


@router.get("/resources")
def resources(_: dict = Depends(current_user), svc: Services = Depends(services)):
    r = svc.monitor.resources()
    r["jobs"] = svc.execution.queue.stats()
    return r


@router.get("/engines", summary="Status setiap engine bahasa (diperiksa nyata)")
def engines(refresh: bool = False, _: dict = Depends(current_user), svc: Services = Depends(services)):
    return {"engines": svc.registry.statuses(refresh=refresh)}


@router.get("/processes")
def processes(_: dict = Depends(require("admin")), svc: Services = Depends(services)):
    return {"processes": svc.monitor.processes(), "jobs": svc.execution.active(),
            "terminals": len(svc.terminal.sessions)}


@router.get("/audit")
def audit(limit: int = 100, _: dict = Depends(require("admin")), svc: Services = Depends(services)):
    return {"entries": svc.db.all("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (min(limit, 1000),))}
