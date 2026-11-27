import asyncio

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from backend.core.exceptions import AppError, Forbidden
from backend.core.permissions import intersect_for_ai
from backend.dependencies import Services, current_user, project_dir, require, services, ws_user
from backend.schemas.models import (AgentModelsIn, AIApply, AIChat, AIConnectionIn, AIConversationIn, AIDecision,
                                    AIProposal, AISettingsIn, ModelBenchIn, ModelProfileImport, ModelProfileIn,
                                    OkResponse)
from backend.services.model_profiles import PURPOSES

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


@router.post("/unload-all", summary="Lepas semua model lokal dari RAM (kecuali yang sedang dipakai agent/Uji Model)")
async def unload_all(user: dict = Depends(require("admin")), svc: Services = Depends(services)):
    out = await svc.ai.unload_all()
    svc.db.audit("ai_unload_all", user=user, detail=out)
    return out


@router.put("/settings")
async def update_settings(body: AISettingsIn, user: dict = Depends(require("admin")), svc: Services = Depends(services)):
    svc.ai.save_settings(body.model_dump(exclude_none=True))
    return await svc.ai.status(user)


# ---------- peran model agent ----------
@router.get("/agent-models", summary="Peran model AI Agent (perencana/pelaksana/peninjau/online) + eskalasi")
def agent_models(_: dict = Depends(current_user), svc: Services = Depends(services)):
    return svc.ai.public_agent_models()


@router.put("/agent-models", summary="Atur peran model agent; null = kosongkan (pakai model aktif)")
def update_agent_models(body: AgentModelsIn, user: dict = Depends(require("admin")), svc: Services = Depends(services)):
    out = svc.ai.save_agent_models(body.model_dump(exclude_unset=True))
    svc.db.audit("ai_agent_models", user=user, detail={k: v for k, v in out.items() if k != "default"})
    return out


# ---------- uji model ----------
@router.get("/bench", summary="Riwayat Uji Model + papan peringkat + rekomendasi peran")
def bench_list(_: dict = Depends(require("read")), svc: Services = Depends(services)):
    return {"runs": svc.bench.list(), "leaderboard": svc.bench.leaderboard(),
            "recommendation": svc.bench.recommendation(), "cases": svc.bench.cases()}


@router.post("/bench", status_code=201, summary="Mulai Uji Model (berjalan di latar belakang, bergiliran)")
async def bench_start(body: ModelBenchIn, user: dict = Depends(require("admin")), svc: Services = Depends(services)):
    return {"runs": svc.bench.create(user, [t.model_dump() for t in body.targets], body.mode)}


@router.get("/bench/{run_id}", summary="Detail Uji Model: hasil per kasus")
def bench_get(run_id: str, _: dict = Depends(require("read")), svc: Services = Depends(services)):
    return svc.bench.get(run_id)


@router.post("/bench/{run_id}/save-profile", summary="Simpan draf profil hasil kalibrasi walau belum memenuhi syarat")
def bench_save_profile(run_id: str, _: dict = Depends(require("admin")), svc: Services = Depends(services)):
    return svc.bench.save_draft(run_id)


# ---------- profil model ----------
@router.get("/profiles", summary="Profil semua model (file JSON per model) + daftar kegunaan")
async def profiles(_: dict = Depends(require("read")), svc: Services = Depends(services)):
    models: list[str] = []
    for c in svc.ai.connections():
        if c["location"] == "local":
            try:
                models += [m["id"] for m in await svc.ai.list_models(c["id"])]
            except AppError:
                pass
    return {"profiles": svc.ai.profiles.list(models),
            "purposes": [{"key": k, "label": v} for k, v in PURPOSES.items()],
            "dir": str(svc.settings.model_profiles_dir), "git": svc.settings.model_profiles_git}


@router.get("/profiles/item", summary="Profil satu model (bawaan bila belum pernah disimpan)")
def profile_get(model: str, _: dict = Depends(require("read")), svc: Services = Depends(services)):
    return svc.ai.profiles.get(model)


@router.put("/profiles/item", summary="Ubah profil manual (disimpan ke file + GitHub)")
def profile_update(model: str, body: ModelProfileIn, user: dict = Depends(require("admin")),
                   svc: Services = Depends(services)):
    out = svc.ai.profiles.update(model, body.model_dump(exclude_unset=True))
    svc.db.audit("model_profile_update", user=user, target=model)
    return out


@router.delete("/profiles/item", summary="Kembalikan profil ke bawaan (hapus file)")
def profile_reset(model: str, user: dict = Depends(require("admin")), svc: Services = Depends(services)):
    out = svc.ai.profiles.delete(model)
    svc.db.audit("model_profile_reset", user=user, target=model)
    return out


@router.post("/profiles/item/sync", summary="Sinkronkan file profil ke GitHub sekarang")
async def profile_sync(model: str, _: dict = Depends(require("admin")), svc: Services = Depends(services)):
    if not svc.ai.profiles.stored(model):
        raise AppError("Profil masih bawaan (belum ada file untuk disinkronkan)", code="no_profile_file")
    await svc.ai.profiles.sync(model, f"profil model {model}: sinkron manual")
    return svc.ai.profiles.get(model)


@router.post("/profiles/import", summary="Impor file profil model (JSON hasil ekspor)")
def profile_import(body: ModelProfileImport, user: dict = Depends(require("admin")), svc: Services = Depends(services)):
    out = svc.ai.profiles.import_profile(body.profile)
    svc.db.audit("model_profile_import", user=user, target=out["model"])
    return out


@router.post("/bench/{run_id}/cancel")
async def bench_cancel(run_id: str, _: dict = Depends(require("admin")), svc: Services = Depends(services)):
    return await svc.bench.cancel(run_id)


@router.delete("/bench/{run_id}", response_model=OkResponse)
def bench_delete(run_id: str, _: dict = Depends(require("admin")), svc: Services = Depends(services)):
    svc.bench.delete(run_id)
    return OkResponse()


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
    """Chat streaming. Klien: {type:'send', conversation_id?, content, project_id?, files?, editor_text?, editor_name?,
    auto_apply?} atau {type:'stop'}. Server: {type: conversation|start|reasoning|delta|edits|done|error|stopped}.
    'edits' = daftar proposal perubahan file dari jawaban AI (diterapkan langsung bila auto_apply)."""
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
            root, pid = None, None
            if msg.get("project_id"):
                pid = str(msg["project_id"])
                root = project_dir(svc, pid, user)
            auto_apply = bool(msg.get("auto_apply")) and "write" in user["perms"]
            async for ev in svc.ai.chat_stream(
                user, msg.get("conversation_id"), str(msg.get("content", "")), project_dir=root,
                files=msg.get("files") or None, editor_text=msg.get("editor_text"), editor_name=msg.get("editor_name"),
                project_id=pid, auto_apply=auto_apply,
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
    root = project_dir(svc, body.project_id, user)
    if not intersect_for_ai(user["perms"]):
        raise Forbidden("AI tidak punya hak apa pun untuk pengguna ini")
    return svc.ai.public_proposal(svc.ai.propose(user, body.project_id, body.path, body.action, body.content,
                                                 body.reason, root=root))


@router.get("/proposals")
def proposals(project_id: str, status: str | None = None, conversation_id: int | None = None,
              task_id: str | None = None, user: dict = Depends(require("read")), svc: Services = Depends(services)):
    project_dir(svc, project_id, user)
    return {"proposals": svc.ai.proposals(project_id, status, conversation_id, task_id)}


@router.post("/proposals/{proposal_id}/decide", summary="Setujui/tolak proposal AI (dicatat & bisa di-undo)")
async def decide(proposal_id: int, body: AIDecision, user: dict = Depends(require("write")), svc: Services = Depends(services)):
    root = project_dir(svc, body.project_id, user)
    res = svc.ai.decide(user, body.project_id, root, proposal_id, body.approve, body.confirm_high_risk)
    svc.db.audit("ai_proposal_decide", user=user, target=str(proposal_id), detail=res["status"])
    svc.agent.on_proposal_decided(res["proposal"].get("task_id"))
    return res


@router.post("/proposals/{proposal_id}/revert", summary="Batalkan editan AI yang sudah diterapkan (kembalikan isi lama)")
def revert(proposal_id: int, body: AIDecision, user: dict = Depends(require("write")), svc: Services = Depends(services)):
    root = project_dir(svc, body.project_id, user)
    res = svc.ai.revert(user, body.project_id, root, proposal_id)
    svc.db.audit("ai_proposal_revert", user=user, target=str(proposal_id))
    return res
