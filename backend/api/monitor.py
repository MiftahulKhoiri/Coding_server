"""Ringkasan dashboard untuk aplikasi Android."""
from fastapi import APIRouter, Depends

from backend.dependencies import Services, current_user, services

router = APIRouter(prefix="/monitor", tags=["monitor"])


@router.get("/dashboard")
def dashboard(user: dict = Depends(current_user), svc: Services = Depends(services)):
    res = svc.monitor.resources()
    projects = svc.projects.list(user)
    recent = svc.db.all(
        "SELECT project_id, path, opened_at FROM recent_files WHERE user_id=? ORDER BY opened_at DESC LIMIT 10", (user["id"],))
    return {
        "info": svc.monitor.info(),
        "resources": res,
        "projects_count": len(projects),
        "recent_projects": projects[:5],
        "recent_files": recent,
        "active_executions": svc.execution.active(),
        "jobs": svc.execution.queue.stats(),
        "terminal_sessions": len(svc.terminal.list(user)),
    }
