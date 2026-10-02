from datetime import date

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from mesveret.context import Ctx
from mesveret.db.models import User
from mesveret.routers.deps import current_user, get_ctx, optional_user
from mesveret.services import petitions

router = APIRouter(tags=["dilekçeler"])


class ReplyIn(BaseModel):
    recipient_id: str
    text: str
    replied_on: date
    reference: str | None = None
    media_id: str | None = None


@router.get("/addressees")
def addressees(scope_id: str | None = None, ctx: Ctx = Depends(get_ctx)) -> list[dict]:
    return petitions.catalog(ctx, scope_id)


@router.get("/petitions")
def list_petitions(ctx: Ctx = Depends(get_ctx)) -> list[dict]:
    return petitions.listing(ctx)


@router.get("/petitions/{petition_id}")
def petition(petition_id: int, ctx: Ctx = Depends(get_ctx),
             viewer: User | None = Depends(optional_user)) -> dict:
    return petitions.view(ctx, petition_id, viewer)


@router.post("/petitions/{petition_id}/replies", status_code=status.HTTP_201_CREATED)
def reply(petition_id: int, body: ReplyIn, ctx: Ctx = Depends(get_ctx),
          user: User = Depends(current_user)) -> dict:
    r = petitions.add_reply(ctx, user, petition_id, recipient_id=body.recipient_id,
                            text=body.text, replied_on=body.replied_on,
                            reference=body.reference, media_id=body.media_id)
    return {"id": r.id}
