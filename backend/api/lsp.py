"""Language server (clangd/pyright) untuk editor lewat WebSocket."""
import asyncio
import json

import psutil
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from backend.core.exceptions import AppError
from backend.dependencies import Services, current_user, project_dir, services, ws_user

router = APIRouter(prefix="/lsp", tags=["lsp"])
ws_router = APIRouter(tags=["websocket"])

IDLE_SECONDS = 20 * 60
MAX_CLIENT_MESSAGE = 4 * 1024 * 1024


@router.get("/status", summary="Ketersediaan language server per bahasa (clangd, pyright)")
def status(_: dict = Depends(current_user), svc: Services = Depends(services)):
    return svc.lsp.status()


@ws_router.websocket("/ws/lsp")
async def ws_lsp(ws: WebSocket, project_id: str, language: str, token: str | None = None):
    """Satu pesan WS = satu pesan JSON-RPC LSP. URI file memakai akar virtual file:///workspace/."""
    await ws.accept()
    svc: Services = ws.app.state.services
    try:
        user = ws_user(ws, token)
        if "read" not in user["perms"] or "execute" not in user["perms"]:
            raise AppError("Butuh izin read & execute untuk language server", code="permission_denied", status_code=403)
        root = project_dir(svc, project_id, user)
        if psutil.virtual_memory().available < svc.settings.min_free_memory_mb * 1024 * 1024:
            raise AppError("RAM server hampir habis; language server tidak dijalankan", code="low_memory", status_code=503)
        session = await svc.lsp.start(language, root, project_id)
    except AppError as e:
        await ws.send_json({"jsonrpc": "2.0", "method": "cs/error", "params": {"code": e.code, "message": e.message}})
        await ws.close(code=4403 if e.status_code == 403 else 4400)
        return
    await ws.send_json({"jsonrpc": "2.0", "method": "cs/ready", "params": {"server": session.info.id, "language": language}})

    async def client_to_server():
        while True:
            try:
                text = await asyncio.wait_for(ws.receive_text(), timeout=IDLE_SECONDS)
            except asyncio.TimeoutError:
                return
            if len(text) > MAX_CLIENT_MESSAGE:
                continue
            try:
                msg = json.loads(text)
            except ValueError:
                continue
            if isinstance(msg, dict):
                await session.send(msg)

    async def server_to_client():
        while True:
            msg = await session.receive()
            if msg is None:
                await ws.send_json({"jsonrpc": "2.0", "method": "cs/exit", "params": {"message": "Language server berhenti"}})
                return
            await ws.send_text(json.dumps(msg, ensure_ascii=False))

    tasks = [asyncio.create_task(client_to_server()), asyncio.create_task(server_to_client())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await session.close()
        try:
            await ws.close()
        except RuntimeError:
            pass
