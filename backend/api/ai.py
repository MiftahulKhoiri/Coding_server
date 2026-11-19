from fastapi import APIRouter, Depends

from backend.core.exceptions import Forbidden
from backend.core.permissions import intersect_for_ai
from backend.dependencies import Services, current_user, project_dir, require, services
from backend.schemas.models import AIChat, AIDecision, AIProposal

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/status")
async def status(user: dict = Depends(current_user), svc: Services = Depends(services)):
    return await svc.ai.status(user)


@router.post("/chat")
async def chat(body: AIChat, user: dict = Depends(require("read")), svc: Services = Depends(services)):
    root = project_dir(svc, body.project_id, user) if body.project_id else None
    return await svc.ai.chat(user, body.messages, root, body.files, temperature=body.temperature, max_tokens=body.max_tokens)


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
