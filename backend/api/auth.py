from fastapi import APIRouter, Depends, Request

from backend.dependencies import Services, client_ip, current_user, require, services
from backend.schemas.models import (LoginRequest, LogoutRequest, OkResponse, PasswordChange, ProfileUpdate,
                                    RefreshRequest, TokenResponse, UserCreate, UserDeleted, UserOut, UserUpdate)

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


@router.get("/me", response_model=UserOut, summary="Profil pengguna yang sedang login")
def me(user: dict = Depends(current_user)):
    return user


@router.patch("/me", response_model=UserOut, summary="Ubah profil sendiri (nama tampilan, email, bio)")
def update_me(body: ProfileUpdate, user: dict = Depends(current_user), svc: Services = Depends(services)):
    u = svc.auth.update_profile(user, body.display_name, body.email, body.bio)
    svc.db.audit("profile_update", user=user)
    return u


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
    u = svc.auth.create_user(body.username, body.password, body.role, actor=user,
                             display_name=body.display_name, email=body.email)
    svc.db.audit("user_create", user=user, target=body.username, detail={"role": body.role})
    return u


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, user: dict = Depends(require("admin")), svc: Services = Depends(services)):
    u = svc.auth.update_user(user_id, body.role, body.is_active, body.password, actor=user,
                             display_name=body.display_name, email=body.email)
    changed = [k for k, v in body.model_dump().items() if v is not None]
    svc.db.audit("user_update", user=user, target=u["username"], detail={"fields": changed})
    return u


@router.delete("/users/{user_id}", response_model=UserDeleted,
               summary="Hapus akun (bukan admin utama); proyeknya dipindahkan ke admin utama")
def delete_user(user_id: int, user: dict = Depends(require("admin")), svc: Services = Depends(services)):
    res = svc.auth.delete_user(user, user_id)
    svc.db.audit("user_delete", user=user, target=res["username"], detail=res)
    moved = res["projects_moved"]
    return {"ok": True, "username": res["username"], "projects_moved": moved,
            "message": f"Akun {res['username']} dihapus" + (f"; {moved} proyek dipindahkan ke admin utama" if moved else "")}
