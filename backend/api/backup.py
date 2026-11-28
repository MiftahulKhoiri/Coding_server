from fastapi import APIRouter, Depends

from backend.core.exceptions import Conflict
from backend.dependencies import Services, require, services
from backend.schemas.models import BackupCreate, BackupRestore

router = APIRouter(prefix="/backup", tags=["backup"])


@router.get("")
def list_backups(_: dict = Depends(require("system")), svc: Services = Depends(services)):
    return {"backups": svc.backup.list(), "retention": svc.settings.backup_retention}


@router.post("", status_code=201)
async def create(body: BackupCreate, user: dict = Depends(require("system")), svc: Services = Depends(services)):
    res = await svc.backup.create(body.label)
    svc.db.audit("backup_create", user=user, target=res["name"])
    return res


@router.get("/{name}/verify")
def verify(name: str, _: dict = Depends(require("system")), svc: Services = Depends(services)):
    return svc.backup.verify(name)


@router.post("/restore")
async def restore(body: BackupRestore, user: dict = Depends(require("system")), svc: Services = Depends(services)):
    if not body.confirm:
        raise Conflict("Restore menimpa data sekarang (data lama disimpan). Kirim confirm=true.", code="confirmation_required")
    res = await svc.backup.restore(body.name, body.include_metadata)
    svc.db.audit("backup_restore", user=user, target=body.name)
    return res
