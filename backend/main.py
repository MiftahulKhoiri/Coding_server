"""CODING_SERVER — FastAPI entrypoint.

Jalankan: python -m uvicorn backend.main:app --host 0.0.0.0 --port 8800
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import (agent, ai, auth, lsp, backup, database, execution, files, git, http_client, monitor, preview, projects,
                         system, terminal)
from backend.config import VERSION, Settings, get_settings
from backend.core.exceptions import install_handlers
from backend.core.logging import get_logger, setup_logging
from backend.dependencies import build_services
from backend.engines.registry import get_registry
from backend.middleware.request_log import RequestLogMiddleware
from backend.schemas.models import ErrorResponse

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.logs_dir)
    log = get_logger()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        svc = app.state.services
        svc.terminal.start_reaper()
        svc.agent.recover()
        svc.bench.recover()
        tasks = [asyncio.create_task(svc.backup.scheduler()), asyncio.create_task(svc.ai.idle_loop())]
        await svc.ai.restore_on_start()
        log.info("CODING_SERVER %s siap di %s:%s (sandbox=%s)", VERSION, settings.host, settings.port,
                 "bwrap" if settings.sandbox_enabled else "none")
        yield
        for t in tasks:
            t.cancel()
        await svc.bench.shutdown()
        await svc.agent.shutdown()
        await svc.execution.shutdown()
        svc.terminal.shutdown()

    app = FastAPI(
        title="CODING_SERVER API",
        version=VERSION,
        description="Multi-language development server untuk Raspberry Pi 5 dengan klien Android.",
        lifespan=lifespan,
        responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 403: {"model": ErrorResponse},
                   404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    app.state.services = build_services(settings, get_registry())
    app.state.services.auth.bootstrap_admin()
    install_handlers(app)
    app.add_middleware(RequestLogMiddleware)
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
                           allow_methods=["*"], allow_headers=["*"])
    for r in (auth, system, monitor, projects, files, execution, terminal, database, git, http_client, backup, ai, lsp,
              agent):
        app.include_router(r.router, prefix=API_PREFIX)
    app.include_router(execution.ws_router)
    app.include_router(terminal.ws_router)
    app.include_router(ai.ws_router)
    app.include_router(lsp.ws_router)
    app.include_router(preview.router)

    @app.get("/", include_in_schema=False)
    def root():
        return {"name": "CODING_SERVER", "version": VERSION, "docs": "/docs", "api": API_PREFIX}

    return app


app = create_app()
