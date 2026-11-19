from fastapi import APIRouter, Depends, Request

from backend.dependencies import Services, client_ip, current_user, require, services
from backend.schemas.models import (LoginRequest, LogoutRequest, OkResponse, PasswordChange, RefreshRequest,
                                    TokenResponse, UserCreate, UserOut, UserUpdate)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse, summary="Login, mendapat access & refresh token")
def login(body: LoginRequest, request: Request, svc: Services = Depends(services)):
    ip = client_ip(request)
    svc.login_limiter.hit("login:" + ip)
    try:
        res = svc.auth.login(body.username, body.password)
    except Exception:
        svc.db.audit("login_failed", target=body.username, ip=ip)
        raise
    svc.db.audit("login", user=res["user"], ip=ip)
    return res


@router.post("/refresh", response_model=TokenResponse, summary="Tukar refresh token dengan token baru")
def refresh(body: RefreshRequest, request: Request, svc: Services = Depends(services)):
    svc.login_limiter.hit("refresh:" + client_ip(request))
    return svc.auth.refresh(body.refresh_token)


@router.post("/logout", response_model=OkResponse, summary="Cabut access token (dan refresh token bila dikirim)")
def logout(body: LogoutRequest | None = None, user: dict = Depends(current_user), svc: Services = Depends(services)):
    svc.auth.revoke(user["jti"], user["exp"])
    if body and body.refresh_token:
        try:
            from backend.core.security import decode_token

            p = decode_token(svc.settings.secret_key, body.refresh_token, kind="refresh")
            if int(p["sub"]) == user["id"]:
                svc.auth.revoke(p["jti"], p["exp"])
        except Exception:
            pass
    svc.db.audit("logout", user=user)
    return {"ok": True, "message": "Logout berhasil"}


@router.get("/me", response_model=UserOut)
def me(user: dict = Depends(current_user)):
    return user


@router.post("/password", response_model=OkResponse)
def change_password(body: PasswordChange, user: dict = Depends(current_user), svc: Services = Depends(services)):
    svc.auth.change_password(user, body.old_password, body.new_password)
    svc.db.audit("password_change", user=user)
    return {"ok": True, "message": "Password diganti"}


@router.get("/users", response_model=list[UserOut])
def list_users(_: dict = Depends(require("admin")), svc: Services = Depends(services)):
    return svc.auth.list_users()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, user: dict = Depends(require("admin")), svc: Services = Depends(services)):
    u = svc.auth.create_user(body.username, body.password, body.role)
    svc.db.audit("user_create", user=user, target=body.username)
    return u


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, user: dict = Depends(require("admin")), svc: Services = Depends(services)):
    u = svc.auth.update_user(user_id, body.role, body.is_active, body.password)
    svc.db.audit("user_update", user=user, target=str(user_id))
    return u
