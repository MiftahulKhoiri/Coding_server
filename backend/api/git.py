from fastapi import APIRouter, Depends

from backend.dependencies import Services, project_dir, require, services
from backend.schemas.models import (GitAdd, GitBranch, GitCheckout, GitClone, GitCommit, GitCredential, GitProject,
                                    GitRemoteOp, GitRemoteSet, OkResponse)

router = APIRouter(prefix="/git", tags=["git"])


@router.get("/status")
async def status(project_id: str, user: dict = Depends(require("read")), svc: Services = Depends(services)):
    return await svc.git.status(project_dir(svc, project_id, user), user)


@router.post("/init")
async def init(body: GitProject, user: dict = Depends(require("write")), svc: Services = Depends(services)):
    return await svc.git.init(project_dir(svc, body.project_id, user), user)


@router.post("/add")
async def add(body: GitAdd, user: dict = Depends(require("write")), svc: Services = Depends(services)):
    return await svc.git.add(project_dir(svc, body.project_id, user), user, body.paths)


@router.post("/commit")
async def commit(body: GitCommit, user: dict = Depends(require("write")), svc: Services = Depends(services)):
    r = await svc.git.commit(project_dir(svc, body.project_id, user), user, body.message, body.add_all)
    svc.db.audit("git_commit", user=user, target=body.project_id)
    return r


@router.get("/log")
async def log(project_id: str, limit: int = 50, user: dict = Depends(require("read")), svc: Services = Depends(services)):
    return {"commits": await svc.git.log(project_dir(svc, project_id, user), user, limit)}


@router.get("/branches")
async def branches(project_id: str, user: dict = Depends(require("read")), svc: Services = Depends(services)):
    return await svc.git.branches(project_dir(svc, project_id, user), user)


@router.post("/branch")
async def branch(body: GitBranch, user: dict = Depends(require("write")), svc: Services = Depends(services)):
    return await svc.git.create_branch(project_dir(svc, body.project_id, user), user, body.name, body.checkout)


@router.post("/checkout")
async def checkout(body: GitCheckout, user: dict = Depends(require("write")), svc: Services = Depends(services)):
    return await svc.git.checkout(project_dir(svc, body.project_id, user), user, body.ref)


@router.get("/diff")
async def diff(project_id: str, staged: bool = False, path: str | None = None, user: dict = Depends(require("read")),
               svc: Services = Depends(services)):
    return await svc.git.diff(project_dir(svc, project_id, user), user, staged, path)


@router.get("/head-file", summary="Isi file di HEAD (penanda baris berubah di editor)")
async def head_file(project_id: str, path: str, user: dict = Depends(require("read")), svc: Services = Depends(services)):
    return await svc.git.head_file(project_dir(svc, project_id, user), user, path)


@router.post("/remote")
async def remote(body: GitRemoteSet, user: dict = Depends(require("write")), svc: Services = Depends(services)):
    return await svc.git.set_remote(project_dir(svc, body.project_id, user), user, body.name, body.url)


@router.post("/pull")
async def pull(body: GitRemoteOp, user: dict = Depends(require("write")), svc: Services = Depends(services)):
    r = await svc.git.pull(project_dir(svc, body.project_id, user), user, body.remote, body.branch)
    svc.db.audit("git_pull", user=user, target=body.project_id)
    return r


@router.post("/push")
async def push(body: GitRemoteOp, user: dict = Depends(require("write")), svc: Services = Depends(services)):
    r = await svc.git.push(project_dir(svc, body.project_id, user), user, body.remote, body.branch)
    svc.db.audit("git_push", user=user, target=body.project_id)
    return r


@router.post("/clone", status_code=201)
async def clone(body: GitClone, user: dict = Depends(require("write")), svc: Services = Depends(services)):
    name = body.name or body.url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
    project = svc.projects.create(user, name, f"Clone dari {body.url}", "", template=False)
    try:
        r = await svc.git.clone(svc.projects.project_dir(project["id"]), user, body.url, body.branch)
        if not r["ok"]:
            from backend.core.exceptions import AppError

            raise AppError("Clone gagal", code="git_error", details={"stderr": r["stderr"][-2000:]})
    except Exception:
        svc.projects.delete(project["id"], user)
        raise
    svc.db.audit("git_clone", user=user, target=project["id"], detail=body.url)
    return {"project": project, **r}


@router.get("/credentials")
def credentials(user: dict = Depends(require("write")), svc: Services = Depends(services)):
    return {"credentials": svc.git.list_credentials(user)}


@router.post("/credentials", response_model=OkResponse)
def set_credential(body: GitCredential, user: dict = Depends(require("write")), svc: Services = Depends(services)):
    svc.git.set_credential(user, body.host, body.username, body.token)
    svc.db.audit("git_credential_set", user=user, target=body.host)
    return {"ok": True, "message": "Kredensial disimpan terenkripsi"}


@router.delete("/credentials", response_model=OkResponse)
def delete_credential(host: str, user: dict = Depends(require("write")), svc: Services = Depends(services)):
    svc.git.delete_credential(user, host)
    return {"ok": True}
