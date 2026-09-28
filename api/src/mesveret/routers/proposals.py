from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from mesveret.context import Ctx
from mesveret.db.models import User
from mesveret.routers.deps import current_user, get_ctx, optional_user
from mesveret.services import proposals
from mesveret.services.proposals import ProposalInput

router = APIRouter(prefix="/proposals", tags=["öneriler"])


class ProposalIn(BaseModel):
    type: str
    title: str = ""
    body: str = ""
    area_id: str | None = None
    scope_id: str | None = None
    resource_ids: list[str] = Field(default_factory=list)
    parent_topic_id: int | None = None
    target_message_id: int | None = None
    target_topic_id: int | None = None
    new_text: str | None = None
    article_key: str | None = None
    new_value: dict[str, Any] | None = None
    reopens_topic_id: int | None = None
    content_rules: list[str] = Field(default_factory=list)
    excerpt: str = ""
    article_action: str = "degistir"


class RivalIn(BaseModel):
    text: str


@router.get("")
def list_proposals(state: str | None = None, ctx: Ctx = Depends(get_ctx),
                   viewer: User | None = Depends(optional_user)) -> list[dict]:
    return proposals.list_proposals(ctx, state, viewer)


@router.post("", status_code=status.HTTP_201_CREATED)
def open_proposal(body: ProposalIn, ctx: Ctx = Depends(get_ctx),
                  user: User = Depends(current_user)) -> dict:
    p = proposals.open_proposal(ctx, user, ProposalInput(**body.model_dump()))
    return {"id": p.id, "status": p.status}


@router.get("/{proposal_id}")
def proposal(proposal_id: int, ctx: Ctx = Depends(get_ctx),
             viewer: User | None = Depends(optional_user)) -> dict:
    return proposals.proposal_view(ctx, proposals.get_proposal(ctx, proposal_id), viewer)


@router.post("/{proposal_id}/objections")
def object_to(proposal_id: int, ctx: Ctx = Depends(get_ctx),
              user: User = Depends(current_user)) -> dict:
    return proposals.object_to(ctx, user, proposal_id)


@router.post("/{proposal_id}/rivals", status_code=status.HTTP_201_CREATED)
def add_rival(proposal_id: int, body: RivalIn, ctx: Ctx = Depends(get_ctx),
              user: User = Depends(current_user)) -> dict:
    ct = proposals.add_rival(ctx, user, proposal_id, body.text)
    return {"id": ct.id}


@router.post("/{proposal_id}/submit")
def submit_draft(proposal_id: int, body: ProposalIn, ctx: Ctx = Depends(get_ctx),
                 user: User = Depends(current_user)) -> dict:
    p = proposals.submit_draft(ctx, user, proposal_id, ProposalInput(**body.model_dump()))
    return {"id": p.id, "status": p.status}
