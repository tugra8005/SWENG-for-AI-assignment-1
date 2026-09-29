from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from mesveret.context import Ctx
from mesveret.db.models import User
from mesveret.errors import DomainError
from mesveret.routers.deps import current_user, get_ctx
from mesveret.services import decision_hour, delegation

router = APIRouter(tags=["karar saati"])


class VoteIn(BaseModel):
    proposal_id: int
    approve: bool | None = None
    approvals: list[int] | None = None
    vote_scope_id: str | None = None  # orantısız etkilenen kapsamın ayrı oylaması


class DelegationIn(BaseModel):
    target: str
    area_id: str | None = None


class DissentIn(BaseModel):
    text: str
    closure_text_id: int | None = None  # dayandığı kaybeden metin (tek seçenek varsa gerekmez)


@router.get("/decision-hour")
def status_(ctx: Ctx = Depends(get_ctx)) -> dict:
    return decision_hour.status(ctx)


@router.get("/decision-hour/ballot")
def ballot(ctx: Ctx = Depends(get_ctx), user: User = Depends(current_user)) -> dict:
    return decision_hour.ballot(ctx, user)


@router.post("/decision-hour/votes", status_code=status.HTTP_201_CREATED)
def vote(body: VoteIn, ctx: Ctx = Depends(get_ctx), user: User = Depends(current_user)) -> dict:
    if (body.approve is None) == (body.approvals is None):
        raise DomainError("Oy olarak ya 'approve' (EVET/HAYIR) ya da 'approvals' (metinler) verin.")
    choice = body.approve if body.approve is not None else body.approvals
    b = decision_hour.cast_vote(ctx, user, body.proposal_id, choice, body.vote_scope_id)
    return {"commit": b.commit, "message": "Oyunuz mühürlendi; pencere kapanınca açılacak."}


@router.get("/decision-hour/sessions")
def sessions(ctx: Ctx = Depends(get_ctx)) -> list[dict]:
    return decision_hour.list_sessions(ctx)


@router.get("/decision-hour/sessions/{session_id}")
def session(session_id: int, ctx: Ctx = Depends(get_ctx)) -> dict:
    return decision_hour.session_view(ctx, session_id)


@router.post("/decisions/{decision_id}/dissents", status_code=status.HTTP_201_CREATED)
def dissent(decision_id: int, body: DissentIn, ctx: Ctx = Depends(get_ctx),
            user: User = Depends(current_user)) -> dict:
    d = decision_hour.add_dissent(ctx, user, decision_id, body.text, body.closure_text_id)
    return {"id": d.id}


@router.get("/delegations")
def my_delegations(ctx: Ctx = Depends(get_ctx), user: User = Depends(current_user)) -> dict:
    return delegation.my_delegations(ctx, user)


@router.post("/delegations", status_code=status.HTTP_201_CREATED)
def set_delegation(body: DelegationIn, ctx: Ctx = Depends(get_ctx),
                   user: User = Depends(current_user)) -> dict:
    delegation.set_delegation(ctx, user, body.target, body.area_id or None)
    ctx.commit()
    return {"message": "Havale kaydedildi."}


class RenewIn(BaseModel):
    area_id: str | None = None


@router.post("/delegations/renew")
def renew_delegation(body: RenewIn, ctx: Ctx = Depends(get_ctx),
                     user: User = Depends(current_user)) -> dict:
    expires_at = delegation.renew_delegation(ctx, user, body.area_id or None)
    ctx.commit()
    return {"message": "Havale yenilendi.", "expires_at": expires_at}


@router.delete("/delegations")
def revoke_delegation(area_id: str | None = None, ctx: Ctx = Depends(get_ctx),
                      user: User = Depends(current_user)) -> dict:
    delegation.revoke_delegation(ctx, user, area_id or None)
    ctx.commit()
    return {"message": "Havale geri alındı."}
