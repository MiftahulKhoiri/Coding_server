import asyncio

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from backend.core.exceptions import AppError, Forbidden
from backend.core.permissions import intersect_for_ai
from backend.dependencies import Services, current_user, project_dir, require, services, ws_user
from backend.schemas.models import (AIApply, AIChat, AIConnectionIn, AIConversationIn, AIDecision, AIProposal,
                                    AISettingsIn, OkResponse)

router = APIRouter(prefix="/ai", tags=["ai"])
ws_router = APIRouter(tags=["websocket"])


# ---------- status & pengaturan model ----------
@router.get("/status", summary="Status model AI aktif (idle/loading/ready/error) + pengaturan")
async def status(user: dict = Depends(current_user), svc: Services = Depends(services)):
    return await svc.ai.status(user)


@router.get("/presets", summary="Templat koneksi lokal & online")
def presets(_: dict = Depends(current_user), svc: Services = Depends(services)):
    return {"presets": svc.ai.presets()}


@router.get("/connections")
def connections(_: dict = Depends(current_user), svc: Services = Depends(services)):
    return {"connections": svc.ai.connections()}


@router.post("/connections", status_code=201)
def add_connection(body: AIConnectionIn, user: dict = Depends(require("admin")), svc: Services = Depends(services)):
    c = svc.ai.save_connection(body.model_dump())
    svc.db.audit("ai_connection_add", user=user, target=c["id"], detail=c["base_url"])
    return c


@router.put("/connections/{cid}")
def update_connection(cid: str, body: AIConnectionIn, user: dict = Depends(require("admin")), svc: Services = Depends(services)):
    c = svc.ai.save_connection(body.model_dump(), cid)
    svc.db.audit("ai_connection_update", user=user, target=cid)
    return c


@router.delete("/connections/{cid}", response_model=OkResponse)
def delete_connection(cid: str, user: dict = Depends(require("admin")), svc: Services = Depends(services)):
    svc.ai.delete_connection(cid)
    svc.db.audit("ai_connection_delete", user=user, target=cid)
    return {"ok": True}


@router.get("/connections/{cid}/models", summary="Daftar model dari penyedia (status muat untuk llama-server)")
async def models(cid: str, _: dict = Depends(require("execute")), svc: Services = Depends(services)):
    return {"models": await svc.ai.list_models(cid)}


@router.post("/apply", summary="Terapkan model: bongkar model lama, muat model baru (lokal) / aktifkan (online)")
async def apply(body: AIApply, user: dict = Depends(require("admin")), svc: Services = Depends(services)):
    st = await svc.ai.apply(body.connection_id, body.model, wait=body.wait)
    svc.db.audit("ai_apply", user=user, target=f"{body.connection_id}:{body.model}")
    return await svc.ai.status(user) if body.wait else st


@router.post("/unload", summary="Bongkar model dari memori")
async def unload(user: dict = Depends(require("admin")), svc: Services = Depends(services)):
    await svc.ai.unload()
    return await svc.ai.status(user)


@router.put("/settings")
async def update_settings(body: AISettingsIn, user: dict = Depends(require("admin")), svc: Services = Depends(services)):
    svc.ai.save_settings(body.model_dump(exclude_none=True))
    return await svc.ai.status(user)


# ---------- percakapan ----------
@router.get("/conversations")
def conversations(user: dict = Depends(require("read")), svc: Services = Depends(services)):
    return {"conversations": svc.ai.conversations(user)}


@router.post("/conversations", status_code=201)
def new_conversation(body: AIConversationIn, user: dict = Depends(require("read")), svc: Services = Depends(services)):
    return svc.ai.create_conversation(user, body.title)


@router.get("/conversations/{conv_id}")
def get_conversation(conv_id: int, user: dict = Depends(require("read")), svc: Services = Depends(services)):
    return svc.ai.conversation(user, conv_id)


@router.patch("/conversations/{conv_id}")
def rename_conversation(conv_id: int, body: AIConversationIn, user: dict = Depends(require("read")),
                        svc: Services = Depends(services)):
    return svc.ai.rename_conversation(user, conv_id, body.title)


@router.delete("/conversations/{conv_id}", response_model=OkResponse)
def delete_conversation(conv_id: int, user: dict = Depends(require("read")), svc: Services = Depends(services)):
    svc.ai.delete_conversation(user, conv_id)
    return {"ok": True}


@router.post("/chat", summary="Chat tanpa streaming (tanpa riwayat)")
async def chat(body: AIChat, user: dict = Depends(require("execute")), svc: Services = Depends(services)):
    root = project_dir(svc, body.project_id, user) if body.project_id else None
    return await svc.ai.chat(user, body.messages, root, body.files, temperature=body.temperature, max_tokens=body.max_tokens)


@ws_router.websocket("/ws/ai/chat")
async def ws_chat(ws: WebSocket, token: str | None = None):
    """Chat streaming. Klien: {type:'send', conversation_id?, content, project_id?, files?, editor_text?, editor_name?}
    atau {type:'stop'}. Server: {type: conversation|start|reasoning|delta|done|error|stopped}."""
    await ws.accept()
    svc: Services = ws.app.state.services
    try:
        user = ws_user(ws, token)
        if "execute" not in user["perms"]:
            raise AppError("Butuh izin execute untuk chat AI", code="permission_denied", status_code=403)
    except AppError as e:
        await ws.send_json({"type": "error", "code": e.code, "message": e.message})
        await ws.close(code=4403)
        return

    task: asyncio.Task | None = None

    async def run(msg: dict) -> None:
        try:
            root = None
            if msg.get("project_id"):
                root = project_dir(svc, str(msg["project_id"]), user)
            async for ev in svc.ai.chat_stream(
                user, msg.get("conversation_id"), str(msg.get("content", "")), project_dir=root,
                files=msg.get("files") or None, editor_text=msg.get("editor_text"), editor_name=msg.get("editor_name"),
            ):
                await ws.send_json(ev)
        except asyncio.CancelledError:
            await ws.send_json({"type": "stopped"})
            raise
        except AppError as e:
            await ws.send_json({"type": "error", "code": e.code, "message": e.message})
        except Exception as e:  # jangan biarkan WS tertutup tanpa pesan
            await ws.send_json({"type": "error", "code": "internal", "message": str(e)})

    try:
        while True:
            msg = await ws.receive_json()
            t = msg.get("type")
            if t == "send":
                if task and not task.done():
                    await ws.send_json({"type": "error", "code": "busy", "message": "Jawaban sebelumnya belum selesai"})
                    continue
                task = asyncio.create_task(run(msg))
            elif t == "stop" and task and not task.done():
                task.cancel()
            elif t == "ping":
                await ws.send_json({"type": "pong"})
    except (WebSocketDisconnect, RuntimeError, ValueError):
        pass
    finally:
        if task and not task.done():
            task.cancel()


# ---------- proposal perubahan file oleh AI ----------
@router.post("/proposals", status_code=201, summary="AI mengusulkan perubahan file (belum diterapkan)")
def propose(body: AIProposal, user: dict = Depends(require("read")), svc: Services = Depends(services)):
    project_dir(svc, body.project_id, user)
    if not intersect_for_ai(user["perms"]):
        raise Forbidden("AI tidak punya hak apa pun untuk pengguna ini")
    return svc.ai.propose(user, body.project_id, body.path, body.action, body.content, body.reason)


@router.get("/proposals")
def proposals(project_id: str, status: str | None = None, user: dict = Depends(require("read")), svc: Services = Depends(services)):
    project_dir(svc, project_id, user)
    return {"proposals": svc.ai.proposals(project_id, status)}


@router.post("/proposals/{proposal_id}/decide", summary="Setujui/tolak proposal AI (dicatat & bisa di-undo)")
def decide(proposal_id: int, body: AIDecision, user: dict = Depends(require("write")), svc: Services = Depends(services)):
    root = project_dir(svc, body.project_id, user)
    res = svc.ai.decide(user, body.project_id, root, proposal_id, body.approve)
    svc.db.audit("ai_proposal_decide", user=user, target=str(proposal_id), detail=res["status"])
    return res
