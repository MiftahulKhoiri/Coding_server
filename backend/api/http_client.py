from fastapi import APIRouter, Depends

from backend.dependencies import Services, current_user, require, services
from backend.schemas.models import HttpRequestIn, HttpSaved, OkResponse

router = APIRouter(prefix="/http", tags=["http"])


@router.post("/request", summary="Kirim HTTP request (dengan perlindungan SSRF)")
async def send(body: HttpRequestIn, user: dict = Depends(require("execute")), svc: Services = Depends(services)):
    res = await svc.http.send(body.method, body.url, body.headers, body.params, body.body, body.body_type, body.form,
                              body.timeout, body.follow_redirects)
    svc.db.audit("http_request", user=user, target=f"{body.method} {body.url}"[:300])
    return res


@router.get("/collections")
def collections(user: dict = Depends(current_user), svc: Services = Depends(services)):
    return svc.http.collections(user)


@router.post("/collections", status_code=201)
def save(body: HttpSaved, user: dict = Depends(require("write")), svc: Services = Depends(services)):
    return svc.http.save(user, body.model_dump())


@router.delete("/collections/{request_id}", response_model=OkResponse)
def delete(request_id: int, user: dict = Depends(require("write")), svc: Services = Depends(services)):
    svc.http.delete(user, request_id)
    return {"ok": True}
