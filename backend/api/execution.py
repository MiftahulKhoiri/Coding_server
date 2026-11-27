import asyncio

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from backend.core.exceptions import AppError, Forbidden
from backend.dependencies import Services, current_user, project_dir, require, services, ws_user
from backend.schemas.models import InstallRequest, JobOut, RunRequest, StdinRequest

router = APIRouter(prefix="/execution", tags=["execution"])
ws_router = APIRouter(tags=["websocket"])


def _check_owner(job, user: dict) -> None:
    uid = job.user_id if hasattr(job, "user_id") else job["user_id"]
    if uid != user["id"] and "admin" not in user["perms"]:
        raise Forbidden("Bukan proses milikmu")


def _out(job) -> dict:
    return job.public() if hasattr(job, "public") else job


@router.post("/run", response_model=JobOut, status_code=202, summary="Jalankan file (build dulu bila perlu)")
async def run(body: RunRequest, user: dict = Depends(require("execute")), svc: Services = Depends(services)):
    root = project_dir(svc, body.project_id, user)
    job = await svc.execution.submit(user=user, project_id=body.project_id, project_dir=root, file_rel=body.path,
                                     action="run", language=body.language, args=body.args, stdin=body.stdin,
                                     interactive=body.interactive, timeout=body.timeout)
    svc.db.audit("execute", user=user, target=f"{body.project_id}:{body.path}", detail={"process_id": job.id})
    return job.public()


@router.post("/build", response_model=JobOut, status_code=202, summary="Kompilasi / periksa sintaks file")
async def build(body: RunRequest, user: dict = Depends(require("build")), svc: Services = Depends(services)):
    root = project_dir(svc, body.project_id, user)
    job = await svc.execution.submit(user=user, project_id=body.project_id, project_dir=root, file_rel=body.path,
                                     action="build", language=body.language)
    svc.db.audit("build", user=user, target=f"{body.project_id}:{body.path}", detail={"process_id": job.id})
    return job.public()


@router.get("/install", summary="Rencana instal dependensi yang terdeteksi di proyek (tanpa menjalankan)")
def install_plan(project_id: str, user: dict = Depends(require("read")), svc: Services = Depends(services)):
    from backend.services import deps_install

    root = project_dir(svc, project_id, user)
    kinds = deps_install.detect_kinds(root)
    plans = []
    for k in kinds:
        try:
            plans.append(deps_install.plan(root, svc.settings.cache_dir / "lang", k)[0].public())
        except AppError as e:
            plans.append({"kind": k, "error": e.message})
    venv = deps_install.project_python(root)
    return {"kinds": kinds, "plans": plans, "venv": str(venv.relative_to(root)) if venv else None,
            "network": svc.settings.install_network}


@router.post("/install", response_model=JobOut, status_code=202,
             summary="Instal dependensi proyek (pip → .venv, npm, go, composer) di sandbox dengan internet")
async def install(body: InstallRequest, user: dict = Depends(require("execute")), svc: Services = Depends(services)):
    from backend.services import deps_install

    if "write" not in user["perms"]:
        raise Forbidden("Instal dependensi butuh izin write (mengubah folder proyek)")
    root = project_dir(svc, body.project_id, user)
    plans = deps_install.plan(root, svc.settings.cache_dir / "lang", body.kind, body.packages)
    commands = [c for pl in plans for c in pl.commands]
    job = await svc.execution.submit_commands(
        user=user, project_id=body.project_id, project_dir=root, commands=commands, action="install",
        label="install:" + "+".join(pl.kind for pl in plans), timeout=svc.settings.install_timeout,
        network=svc.settings.install_network)
    svc.db.audit("install_deps", user=user, target=body.project_id,
                 detail={"process_id": job.id, "kinds": [pl.kind for pl in plans], "packages": body.packages})
    return job.public()


@router.get("", summary="Riwayat eksekusi")
def list_jobs(project_id: str | None = None, limit: int = Query(50, le=500), user: dict = Depends(current_user),
              svc: Services = Depends(services)):
    return {"executions": svc.execution.list(user, project_id, limit), "queue": svc.execution.queue.stats()}


@router.get("/artifacts/{project_id}")
def artifacts(project_id: str, user: dict = Depends(require("read")), svc: Services = Depends(services)):
    project_dir(svc, project_id, user)
    return {"artifacts": svc.build.artifacts(project_id)}


@router.delete("/artifacts/{project_id}")
def clean_artifacts(project_id: str, user: dict = Depends(require("build")), svc: Services = Depends(services)):
    project_dir(svc, project_id, user)
    return svc.build.clean(project_id)


@router.get("/{process_id}", response_model=JobOut)
def get_job(process_id: str, user: dict = Depends(current_user), svc: Services = Depends(services)):
    job = svc.execution.get(process_id)
    _check_owner(job, user)
    return _out(job)


@router.post("/{process_id}/stop", response_model=JobOut)
async def stop(process_id: str, user: dict = Depends(require("execute")), svc: Services = Depends(services)):
    job = svc.execution.get(process_id)
    _check_owner(job, user)
    await svc.execution.stop(process_id)
    return _out(svc.execution.get(process_id))


@router.post("/{process_id}/stdin")
async def stdin(process_id: str, body: StdinRequest, user: dict = Depends(require("execute")), svc: Services = Depends(services)):
    job = svc.execution.get(process_id)
    _check_owner(job, user)
    ok = await svc.execution.send_input(process_id, body.data, body.eof)
    if not ok:
        raise AppError("Proses tidak menerima input (sudah selesai atau bukan mode interaktif)", code="stdin_closed")
    return {"ok": True}


@ws_router.websocket("/ws/execution/{process_id}")
async def ws_execution(ws: WebSocket, process_id: str, token: str | None = None):
    """Stream output real-time. Pesan server: {type: status|stdout|stderr|phase|end}.
    Pesan klien: {type: "stdin", data, eof?} atau {type: "stop"}."""
    await ws.accept()
    svc: Services = ws.app.state.services
    try:
        user = ws_user(ws, token)
        job = svc.execution.get(process_id)
        _check_owner(job, user)
    except AppError as e:
        await ws.send_json({"type": "error", "code": e.code, "message": e.message})
        await ws.close(code=4401 if e.status_code == 401 else 4403)
        return
    if not hasattr(job, "subscribe") and not hasattr(job, "public"):
        await ws.send_json({"type": "end", "job": job})
        await ws.close()
        return
    if not hasattr(job, "public"):
        await ws.send_json({"type": "end", "job": job})
        await ws.close()
        return
    q = svc.execution.subscribe(job)

    async def reader():
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "stdin" and "execute" in user["perms"]:
                await svc.execution.send_input(process_id, str(msg.get("data", "")), bool(msg.get("eof")))
            elif msg.get("type") == "stop" and "execute" in user["perms"]:
                await svc.execution.stop(process_id)

    rtask = asyncio.create_task(reader())
    try:
        while True:
            ev = await q.get()
            await ws.send_json(ev)
            if ev.get("type") == "end":
                break
        await ws.close()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        rtask.cancel()
        svc.execution.unsubscribe(job, q)
