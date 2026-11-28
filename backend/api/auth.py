from fastapi import APIRouter, Depends, File, Request, Response, UploadFile

from backend.dependencies import Services, client_ip, current_user, require, services
from backend.schemas.models import (LinkStart, LoginRequest, LogoutRequest, OAuthConfigIn, OkResponse, PasswordChange,
                                    ProfileUpdate,
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


@router.put("/me/avatar", response_model=UserOut, summary="Unggah foto profil (multipart 'file': JPEG/PNG/WebP, maks 2 MB)")
async def upload_avatar(file: UploadFile = File(...), user: dict = Depends(current_user), svc: Services = Depends(services)):
    data = await file.read(svc.auth.AVATAR_MAX + 1)
    u = svc.auth.set_avatar(user, data)
    svc.db.audit("avatar_update", user=user, detail={"bytes": len(data)})
    return u


@router.delete("/me/avatar", response_model=UserOut, summary="Hapus foto profil")
def delete_avatar(user: dict = Depends(current_user), svc: Services = Depends(services)):
    return svc.auth.delete_avatar(user)


@router.get("/users/{user_id}/avatar", summary="Foto profil pengguna (butuh login)",
            responses={200: {"content": {"image/jpeg": {}, "image/png": {}, "image/webp": {}}}})
def get_avatar(user_id: int, _: dict = Depends(current_user), svc: Services = Depends(services)):
    data, ctype = svc.auth.avatar(user_id)
    return Response(content=data, media_type=ctype, headers={"Cache-Control": "private, max-age=86400",
                                                             "X-Content-Type-Options": "nosniff"})


# ---------- akun tertaut (GitHub / Google, OAuth device flow) ----------
@router.get("/oauth/providers", summary="Penyedia yang sudah diatur admin (github/google)")
def oauth_providers(_: dict = Depends(current_user), svc: Services = Depends(services)):
    return svc.oauth.providers()


@router.get("/oauth/config", summary="Client ID OAuth (khusus admin utama)")
def oauth_config(_: dict = Depends(require("system")), svc: Services = Depends(services)):
    return svc.oauth.public_config()


@router.put("/oauth/config", summary="Simpan Client ID/secret OAuth (khusus admin utama)")
def oauth_config_save(body: OAuthConfigIn, user: dict = Depends(require("system")), svc: Services = Depends(services)):
    out = svc.oauth.save_config(body.github_client_id, body.google_client_id, body.google_client_secret)
    svc.db.audit("oauth_config", user=user)
    return out


@router.get("/identities", summary="Akun GitHub/Google yang ditautkan + email terverifikasi")
def identities(user: dict = Depends(current_user), svc: Services = Depends(services)):
    return {"identities": svc.oauth.identities(user), "verified_emails": svc.oauth.verified_emails(user["id"])}


@router.post("/identities/{provider}/link", summary="Mulai menautkan akun (device flow): tampilkan user_code ke pengguna")
async def identity_link(provider: str, body: LinkStart, user: dict = Depends(current_user), svc: Services = Depends(services)):
    return await svc.oauth.start(user, provider, body.allow_push)


@router.get("/identities/flows/{flow_id}", summary="Status penautan (pending|linked|denied|expired|error)")
def identity_flow(flow_id: str, user: dict = Depends(current_user), svc: Services = Depends(services)):
    return svc.oauth.flow(user, flow_id)


@router.delete("/identities/{provider}", response_model=OkResponse, summary="Lepas tautan akun")
def identity_unlink(provider: str, user: dict = Depends(current_user), svc: Services = Depends(services)):
    svc.oauth.unlink(user, provider)
    return {"ok": True}


@router.post("/password", response_model=OkResponse)
def change_password(body: PasswordChange, user: dict = Depends(current_user), svc: Services = Depends(services)):
    svc.auth.change_password(user, body.old_password, body.new_password)
    svc.db.audit("password_change", user=user)
    return {"ok": True, "message": "Password diganti"}


@router.get("/users", response_model=list[UserOut])
def list_users(_: dict = Depends(require("users")), svc: Services = Depends(services)):
    return svc.auth.list_users()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, user: dict = Depends(require("users")), svc: Services = Depends(services)):
    u = svc.auth.create_user(body.username, body.password, body.role, actor=user,
                             display_name=body.display_name, email=body.email)
    svc.db.audit("user_create", user=user, target=body.username, detail={"role": body.role})
    return u


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, user: dict = Depends(require("users")), svc: Services = Depends(services)):
    u = svc.auth.update_user(user_id, body.role, body.is_active, body.password, actor=user,
                             display_name=body.display_name, email=body.email)
    changed = [k for k, v in body.model_dump().items() if v is not None]
    svc.db.audit("user_update", user=user, target=u["username"], detail={"fields": changed})
    return u


@router.delete("/users/{user_id}", response_model=UserDeleted,
               summary="Hapus akun (bukan admin utama); proyeknya dipindahkan ke admin utama")
def delete_user(user_id: int, user: dict = Depends(require("users")), svc: Services = Depends(services)):
    res = svc.auth.delete_user(user, user_id)
    svc.db.audit("user_delete", user=user, target=res["username"], detail=res)
    moved = res["projects_moved"]
    return {"ok": True, "username": res["username"], "projects_moved": moved,
            "message": f"Akun {res['username']} dihapus" + (f"; {moved} proyek dipindahkan ke admin utama" if moved else "")}
