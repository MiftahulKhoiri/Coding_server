from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from backend.dependencies import Services, current_user, project_dir, require, services
from backend.schemas.models import DbCreate, DbImport, DbQuery, DbRef

router = APIRouter(prefix="/database", tags=["database"])


def _path(svc: Services, user: dict, name: str, project_id: str | None, must_exist: bool = True):
    root = project_dir(svc, project_id, user) if project_id else None
    return svc.database.resolve(user, name, root, must_exist=must_exist)


@router.get("/list")
def list_dbs(project_id: str | None = None, user: dict = Depends(require("read")), svc: Services = Depends(services)):
    root = project_dir(svc, project_id, user) if project_id else None
    return {"databases": svc.database.list(user, root)}


@router.post("/create", status_code=201)
def create(body: DbCreate, user: dict = Depends(require("write")), svc: Services = Depends(services)):
    root = project_dir(svc, body.project_id, user) if body.project_id else None
    return svc.database.create(user, body.name, root)


@router.post("/query", summary="Eksekusi SQL. mode=read (read-only) atau write; destruktif butuh confirm=true")
def query(body: DbQuery, user: dict = Depends(current_user), svc: Services = Depends(services)):
    from backend.core.exceptions import Forbidden

    need = "write" if body.mode == "write" else "read"
    if need not in user["perms"]:
        raise Forbidden(f"Butuh izin {need}")
    p = _path(svc, user, body.database, body.project_id)
    res = svc.database.query(p, body.sql, body.params, body.mode, body.confirm)
    if body.mode == "write":
        svc.db.audit("db_write", user=user, target=body.database, detail=body.sql[:500])
    return res


@router.get("/schema")
def schema(database: str, project_id: str | None = None, user: dict = Depends(require("read")), svc: Services = Depends(services)):
    return svc.database.schema(_path(svc, user, database, project_id))


@router.get("/export", response_class=PlainTextResponse)
def export_csv(database: str, table: str, project_id: str | None = None, user: dict = Depends(require("read")),
               svc: Services = Depends(services)):
    return PlainTextResponse(svc.database.export_csv(_path(svc, user, database, project_id), table), media_type="text/csv")


@router.post("/import")
def import_csv(body: DbImport, user: dict = Depends(require("write")), svc: Services = Depends(services)):
    return svc.database.import_csv(_path(svc, user, body.database, body.project_id), body.table, body.csv, body.create_table)


@router.post("/backup")
def backup(body: DbRef, user: dict = Depends(require("read")), svc: Services = Depends(services)):
    dest = svc.database.backup(_path(svc, user, body.database, body.project_id))
    return {"backup": dest.name, "size": dest.stat().st_size}
