from fastapi import APIRouter, Depends

from backend.dependencies import Services, current_user, require, services
from backend.schemas.models import OkResponse, ProjectCreate, ProjectOut, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
def list_projects(user: dict = Depends(current_user), svc: Services = Depends(services)):
    return svc.projects.list(user)


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, user: dict = Depends(require("write")), svc: Services = Depends(services)):
    p = svc.projects.create(user, body.name, body.description, body.language, body.template)
    svc.db.audit("project_create", user=user, target=p["id"])
    return p


@router.get("/templates")
def templates(_: dict = Depends(current_user)):
    from backend.services.project_service import TEMPLATES

    return {"languages": sorted(TEMPLATES)}


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, user: dict = Depends(current_user), svc: Services = Depends(services)):
    return svc.projects._decorate(svc.projects.get(project_id, user))


@router.put("/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, body: ProjectUpdate, user: dict = Depends(require("write")), svc: Services = Depends(services)):
    return svc.projects.update(project_id, user, body.name, body.description, body.language)


@router.delete("/{project_id}", response_model=OkResponse)
def delete_project(project_id: str, user: dict = Depends(require("delete")), svc: Services = Depends(services)):
    svc.projects.delete(project_id, user)
    svc.db.audit("project_delete", user=user, target=project_id)
    return {"ok": True, "message": "Proyek dihapus"}
