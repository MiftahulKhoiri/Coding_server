"""Kontainer layanan + dependency FastAPI (autentikasi, izin, akses proyek)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import Depends, Request, WebSocket
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.config import Settings
from backend.core.exceptions import Forbidden, Unauthorized
from backend.core.security import RateLimiter
from backend.database.db import Database
from backend.engines.registry import EngineRegistry
from backend.services.lsp_service import LspService
from backend.services.format_service import FormatService
from backend.services.agent_service import AgentService
from backend.services.ai_service import AIService
from backend.services.model_bench import ModelBench
from backend.services.auth_service import AuthService
from backend.services.backup_service import BackupService
from backend.services.build_service import BuildService
from backend.services.database_service import DatabaseService
from backend.services.execution_service import ExecutionService
from backend.services.file_service import FileService
from backend.services.git_service import GitService
from backend.services.http_service import HttpService
from backend.services.monitor_service import MonitorService
from backend.services.project_service import ProjectService
from backend.services.terminal_service import TerminalService


@dataclass
class Services:
    settings: Settings
    db: Database
    registry: EngineRegistry
    auth: AuthService
    projects: ProjectService
    files: FileService
    execution: ExecutionService
    terminal: TerminalService
    database: DatabaseService
    git: GitService
    http: HttpService
    monitor: MonitorService
    backup: BackupService
    build: BuildService
    ai: AIService
    lsp: "LspService"
    agent: AgentService
    bench: ModelBench
    llama_ctx: "LlamaContextService"
    fmt: "FormatService"
    login_limiter: RateLimiter
    api_limiter: RateLimiter


def build_services(settings: Settings, registry: EngineRegistry) -> Services:
    db = Database(settings.metadata_dir / "coding_server.db")
    files = FileService(settings, db)
    holder: dict = {}
    svc = Services(
        settings=settings, db=db, registry=registry, auth=AuthService(settings, db),
        projects=ProjectService(settings, db), files=files,
        execution=ExecutionService(settings, db, registry), terminal=TerminalService(settings),
        database=DatabaseService(settings), git=GitService(settings, db), http=HttpService(settings, db),
        monitor=MonitorService(settings), backup=BackupService(settings), build=BuildService(settings),
        ai=AIService(settings, db, files), lsp=LspService(settings),
        login_limiter=RateLimiter(settings.rate_limit_login_per_minute, 60.0),
        api_limiter=RateLimiter(settings.rate_limit_api_per_minute, 60.0),
        agent=AgentService(settings, db, lambda: holder["svc"]),
        bench=ModelBench(settings, db, lambda: holder["svc"]),
        llama_ctx=None,  # diisi di bawah (butuh AIService)
        fmt=FormatService(settings),
    )
    from backend.services.llama_context import LlamaContextService

    svc.llama_ctx = LlamaContextService(settings, svc.ai)
    holder["svc"] = svc
    return svc


def services(request: Request) -> Services:
    return request.app.state.services


bearer = HTTPBearer(auto_error=False)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


async def current_user(
    request: Request, creds: HTTPAuthorizationCredentials | None = Depends(bearer)
) -> dict:
    if creds is None or creds.scheme.lower() != "bearer":
        raise Unauthorized("Butuh token Bearer")
    svc = services(request)
    svc.api_limiter.hit("u:" + creds.credentials[-16:])
    return svc.auth.user_from_access_token(creds.credentials)


def ws_user(ws: WebSocket, token: str | None) -> dict:
    svc: Services = ws.app.state.services
    if not token:
        auth = ws.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:]
    if not token:
        raise Unauthorized("Butuh token")
    return svc.auth.user_from_access_token(token)


def require(*perms: str):
    async def dep(user: dict = Depends(current_user)) -> dict:
        missing = [p for p in perms if p not in user["perms"]]
        if missing:
            raise Forbidden(f"Butuh izin: {', '.join(missing)}", code="permission_denied")
        return user

    return dep


def project_dir(svc: Services, project_id: str, user: dict) -> Path:
    svc.projects.get(project_id, user)
    d = svc.projects.project_dir(project_id)
    d.mkdir(parents=True, exist_ok=True)
    return d
