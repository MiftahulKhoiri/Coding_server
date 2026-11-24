"""AI Coding Agent: task persisten (rencana, log, checkpoint, persetujuan, laporan)."""
from fastapi import APIRouter, Depends, Query

from backend.dependencies import Services, current_user, project_dir, require, services
from backend.schemas.models import AgentTaskCreate, OkResponse

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/tools", summary="Daftar tool agen + apakah diizinkan untuk pengguna ini")
def tools(user: dict = Depends(current_user), svc: Services = Depends(services)):
    return {"tools": svc.agent.tools_for(user)}


# Endpoint yang memulai/melanjutkan task harus async: task dijalankan di event loop server.
@router.post("/tasks", status_code=201, summary="Buat task agen (langsung masuk antrean)")
async def create(body: AgentTaskCreate, user: dict = Depends(require("execute")), svc: Services = Depends(services)):
    project_dir(svc, body.project_id, user)
    return svc.agent.create(user, body.project_id, body.description, body.title, body.auto_apply, body.max_steps)


@router.get("/tasks")
def list_tasks(project_id: str | None = None, status: str | None = None, limit: int = Query(100, le=500),
               user: dict = Depends(require("read")), svc: Services = Depends(services)):
    return {"tasks": svc.agent.list(user, project_id, status, limit)}


@router.get("/tasks/{task_id}")
def get_task(task_id: str, user: dict = Depends(require("read")), svc: Services = Depends(services)):
    return svc.agent.get(user, task_id)


@router.get("/tasks/{task_id}/events", summary="Log task (polling: kirim after = id event terakhir)")
def events(task_id: str, after: int = 0, limit: int = Query(200, le=1000), user: dict = Depends(require("read")),
           svc: Services = Depends(services)):
    return {"events": svc.agent.events(user, task_id, after, limit)}


@router.get("/tasks/{task_id}/proposals", summary="Proposal perubahan file milik task ini")
def task_proposals(task_id: str, user: dict = Depends(require("read")), svc: Services = Depends(services)):
    t = svc.agent.get(user, task_id)
    return {"proposals": svc.ai.proposals(t["project_id"], None, None, task_id)}


@router.post("/tasks/{task_id}/cancel")
async def cancel(task_id: str, user: dict = Depends(require("execute")), svc: Services = Depends(services)):
    return await svc.agent.cancel(user, task_id)


@router.post("/tasks/{task_id}/pause")
async def pause(task_id: str, user: dict = Depends(require("execute")), svc: Services = Depends(services)):
    return svc.agent.pause(user, task_id)


@router.post("/tasks/{task_id}/resume", summary="Lanjutkan (PAUSED / WAITING_APPROVAL) atau ulangi (FAILED / CANCELLED)")
async def resume(task_id: str, user: dict = Depends(require("execute")), svc: Services = Depends(services)):
    return svc.agent.resume(user, task_id)


@router.delete("/tasks/{task_id}", response_model=OkResponse)
def delete(task_id: str, user: dict = Depends(require("execute")), svc: Services = Depends(services)):
    svc.agent.delete(user, task_id)
    return {"ok": True}
