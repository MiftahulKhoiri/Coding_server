import time

from fastapi import APIRouter, Depends, Query

from backend.dependencies import Services, current_user, project_dir, require, services
from backend.schemas.models import (FavoriteRequest, FileContent, FileCreate, FileEntry, FileMove, FileRename,
                                    FileWrite, FormatRequest, OkResponse, RestoreRequest)

router = APIRouter(prefix="/files", tags=["files"])


@router.get("/tree", response_model=FileEntry)
def tree(project_id: str, path: str = "", depth: int = Query(1, ge=1, le=20), user: dict = Depends(require("read")),
         svc: Services = Depends(services)):
    return svc.files.tree(project_dir(svc, project_id, user), path, depth)


@router.get("/read", response_model=FileContent)
def read(project_id: str, path: str, user: dict = Depends(require("read")), svc: Services = Depends(services)):
    root = project_dir(svc, project_id, user)
    res = svc.files.read(root, path)
    svc.db.execute("INSERT OR REPLACE INTO recent_files(user_id, project_id, path, opened_at) VALUES(?,?,?,?)",
                   (user["id"], project_id, res["path"], time.time()))
    return res


@router.get("/info", response_model=FileEntry)
def info(project_id: str, path: str = "", user: dict = Depends(require("read")), svc: Services = Depends(services)):
    return svc.files.info(project_dir(svc, project_id, user), path)


@router.post("/create", response_model=FileEntry, status_code=201)
def create(body: FileCreate, user: dict = Depends(require("write")), svc: Services = Depends(services)):
    root = project_dir(svc, body.project_id, user)
    res = svc.files.create(body.project_id, root, body.path, body.type, body.content, actor=user)
    svc.projects.touch(body.project_id)
    return res


@router.put("/write", response_model=FileEntry)
def write(body: FileWrite, user: dict = Depends(require("write")), svc: Services = Depends(services)):
    root = project_dir(svc, body.project_id, user)
    res = svc.files.write(body.project_id, root, body.path, body.content, actor=user, expected_sha256=body.expected_sha256)
    svc.projects.touch(body.project_id)
    return res


@router.post("/rename", response_model=FileEntry)
def rename(body: FileRename, user: dict = Depends(require("write")), svc: Services = Depends(services)):
    return svc.files.rename(project_dir(svc, body.project_id, user), body.path, body.new_name)


@router.post("/copy", response_model=FileEntry)
def copy(body: FileMove, user: dict = Depends(require("write")), svc: Services = Depends(services)):
    return svc.files.move(project_dir(svc, body.project_id, user), body.path, body.destination, copy=True, overwrite=body.overwrite)


@router.post("/move", response_model=FileEntry)
def move(body: FileMove, user: dict = Depends(require("write")), svc: Services = Depends(services)):
    return svc.files.move(project_dir(svc, body.project_id, user), body.path, body.destination, overwrite=body.overwrite)


@router.delete("/delete", response_model=OkResponse)
def delete(project_id: str, path: str, recursive: bool = False, user: dict = Depends(require("delete")),
           svc: Services = Depends(services)):
    svc.files.delete(project_id, project_dir(svc, project_id, user), path, recursive=recursive, actor=user)
    svc.db.audit("file_delete", user=user, target=f"{project_id}:{path}")
    return {"ok": True, "message": "Dihapus"}


@router.get("/search", response_model=list[dict])
def search(project_id: str, q: str = Query(min_length=1), content: bool = False, path: str = "",
           user: dict = Depends(require("read")), svc: Services = Depends(services)):
    return svc.files.search(project_dir(svc, project_id, user), q, content=content, path=path)


@router.get("/list", summary="Semua path file proyek (untuk Buka file cepat); tanpa .git, node_modules, .venv, cache")
def list_files(project_id: str, user: dict = Depends(require("read")), svc: Services = Depends(services)):
    return svc.files.list_files(project_dir(svc, project_id, user))


@router.post("/format", summary="Format kode (clang-format, ruff, prettier, gofmt) — mengembalikan teks, tidak menulis file")
async def format_code(body: FormatRequest, user: dict = Depends(require("write")), svc: Services = Depends(services)):
    root = project_dir(svc, body.project_id, user)
    file = svc.files.resolve(root, body.path, allow_root=False)
    return await svc.fmt.format(root, file, body.content, body.tab_size)


@router.get("/format/status", summary="Formatter yang terpasang di server")
def format_status(_: dict = Depends(current_user), svc: Services = Depends(services)):
    return svc.fmt.status()


@router.get("/history")
def history(project_id: str, path: str | None = None, user: dict = Depends(require("read")), svc: Services = Depends(services)):
    project_dir(svc, project_id, user)
    return {"history": svc.files.history(project_id, path)}


@router.get("/history/{history_id}")
def history_content(history_id: int, project_id: str, user: dict = Depends(require("read")), svc: Services = Depends(services)):
    project_dir(svc, project_id, user)
    row, content = svc.files.history_content(project_id, history_id)
    return {**row, "content": content}


@router.post("/restore", response_model=FileEntry)
def restore(body: RestoreRequest, user: dict = Depends(require("write")), svc: Services = Depends(services)):
    return svc.files.restore(body.project_id, project_dir(svc, body.project_id, user), body.history_id, user)


@router.get("/recent")
def recent(user: dict = Depends(current_user), svc: Services = Depends(services)):
    return {"files": svc.db.all("SELECT project_id, path, opened_at FROM recent_files WHERE user_id=? ORDER BY opened_at DESC LIMIT 30",
                                (user["id"],))}


@router.get("/favorites")
def favorites(user: dict = Depends(current_user), svc: Services = Depends(services)):
    return {"files": svc.db.all("SELECT project_id, path, created_at FROM favorites WHERE user_id=? ORDER BY created_at DESC",
                                (user["id"],))}


@router.post("/favorites", response_model=OkResponse)
def add_favorite(body: FavoriteRequest, user: dict = Depends(require("read")), svc: Services = Depends(services)):
    root = project_dir(svc, body.project_id, user)
    rel = svc.files.info(root, body.path)["path"]
    svc.db.execute("INSERT OR REPLACE INTO favorites(user_id, project_id, path, created_at) VALUES(?,?,?,?)",
                   (user["id"], body.project_id, rel, time.time()))
    return {"ok": True}


@router.delete("/favorites", response_model=OkResponse)
def remove_favorite(project_id: str, path: str, user: dict = Depends(current_user), svc: Services = Depends(services)):
    svc.db.execute("DELETE FROM favorites WHERE user_id=? AND project_id=? AND path=?", (user["id"], project_id, path))
    return {"ok": True}
