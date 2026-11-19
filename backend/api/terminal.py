import asyncio
import base64

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from backend.core.exceptions import AppError
from backend.dependencies import Services, project_dir, require, services, ws_user
from backend.schemas.models import OkResponse, TerminalCreate, TerminalOut

router = APIRouter(prefix="/terminal", tags=["terminal"])
ws_router = APIRouter(tags=["websocket"])


@router.post("/sessions", response_model=TerminalOut, status_code=201)
async def create_session(body: TerminalCreate, user: dict = Depends(require("terminal")), svc: Services = Depends(services)):
    root = project_dir(svc, body.project_id, user)
    cwd = svc.files.resolve(root, body.cwd, must_exist=True)
    if not cwd.is_dir():
        raise AppError("cwd harus folder", code="not_a_folder")
    sess = svc.terminal.create(user, body.project_id, root, cwd, body.cols, body.rows)
    svc.db.audit("terminal_open", user=user, target=body.project_id, detail={"session_id": sess.session_id})
    return sess.public()


@router.get("/sessions", response_model=list[TerminalOut])
def list_sessions(user: dict = Depends(require("terminal")), svc: Services = Depends(services)):
    return svc.terminal.list(user)


@router.delete("/sessions/{session_id}", response_model=OkResponse)
def close_session(session_id: str, user: dict = Depends(require("terminal")), svc: Services = Depends(services)):
    svc.terminal.get(session_id, user)
    svc.terminal.close(session_id)
    svc.db.audit("terminal_close", user=user, target=session_id)
    return {"ok": True, "message": "Sesi ditutup"}


@ws_router.websocket("/ws/terminal/{session_id}")
async def ws_terminal(ws: WebSocket, session_id: str, token: str | None = None):
    """Pesan klien: {type:'input', data} | {type:'resize', cols, rows} | {type:'signal', signal:'SIGINT'} | {type:'ping'}.
    Pesan server: {type:'output', data} | {type:'exit', exit_code} | {type:'error', message}."""
    await ws.accept()
    svc: Services = ws.app.state.services
    try:
        user = ws_user(ws, token)
        if "terminal" not in user["perms"]:
            raise AppError("Butuh izin terminal", code="permission_denied", status_code=403)
        sess = svc.terminal.get(session_id, user)
    except AppError as e:
        await ws.send_json({"type": "error", "code": e.code, "message": e.message})
        await ws.close(code=4403)
        return
    q: asyncio.Queue = asyncio.Queue(maxsize=5000)
    if sess.scrollback:
        await ws.send_json({"type": "output", "data": bytes(sess.scrollback[-20000:]).decode("utf-8", errors="replace")})
    if sess.status != "running":
        await ws.send_json({"type": "exit", "exit_code": sess.exit_code})
        await ws.close()
        return
    sess.subscribers.add(q)

    async def writer():
        while True:
            ev = await q.get()
            await ws.send_json(ev)
            if ev["type"] == "exit":
                await ws.close()
                return

    wtask = asyncio.create_task(writer())
    try:
        while True:
            msg = await ws.receive_json()
            t = msg.get("type")
            if t == "input":
                svc.terminal.write(sess, str(msg.get("data", "")))
            elif t == "input_b64":
                svc.terminal.write(sess, base64.b64decode(msg.get("data", "")).decode("utf-8", errors="replace"))
            elif t == "resize":
                svc.terminal.resize(sess, int(msg.get("cols", 80)), int(msg.get("rows", 24)))
            elif t == "signal":
                svc.terminal.signal(sess, str(msg.get("signal", "")))
            elif t == "ping":
                await ws.send_json({"type": "pong"})
    except (WebSocketDisconnect, RuntimeError, ValueError):
        pass
    finally:
        wtask.cancel()
        sess.subscribers.discard(q)
