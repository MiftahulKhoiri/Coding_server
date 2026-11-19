"""Pratinjau HTML/CSS/JS statis untuk WebView/browser.

URL berbentuk /preview/{token}/{project_id}/{path}. Token pratinjau berumur pendek, hanya
berlaku untuk satu proyek, sehingga file pendukung (css/js/gambar) ikut termuat tanpa header.
"""
import mimetypes

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse

from backend.core.exceptions import Forbidden, NotFound
from backend.core.security import create_token, decode_token
from backend.dependencies import Services, project_dir, require, services

router = APIRouter(tags=["preview"])


@router.post("/api/v1/preview/token", summary="Buat URL pratinjau (berlaku 1 jam)")
def preview_token(project_id: str, path: str = "index.html", user: dict = Depends(require("read")),
                  svc: Services = Depends(services)):
    project_dir(svc, project_id, user)
    tok, _, exp = create_token(svc.settings.secret_key, user_id=user["id"], username=user["username"], kind="preview",
                               ttl_seconds=3600, extra={"pid": project_id})
    rel = svc.files.normalize(path)
    return {"url": f"/preview/{tok}/{project_id}/{rel}", "expires_at": exp}


@router.get("/preview/{token}/{project_id}/{path:path}", include_in_schema=False)
def preview(token: str, project_id: str, path: str, request: Request):
    svc: Services = request.app.state.services
    payload = decode_token(svc.settings.secret_key, token, kind="preview")
    if payload.get("pid") != project_id:
        raise Forbidden("Token pratinjau bukan untuk proyek ini")
    root = svc.projects.project_dir(project_id)
    p = svc.files.resolve(root, path or "index.html", must_exist=True)
    if p.is_dir():
        p = p / "index.html"
        if not p.is_file():
            raise NotFound("index.html tidak ada")
    mt = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    return FileResponse(p, media_type=mt, headers={
        "Content-Security-Policy": "default-src 'self' 'unsafe-inline' data: blob:; connect-src *; img-src * data: blob:",
        "Cache-Control": "no-store",
    })
