from fastapi import APIRouter, Depends
from pydantic import BaseModel

from mesveret.context import Ctx
from mesveret.db.models import User
from mesveret.routers.deps import current_user, get_ctx
from mesveret.services import notifications

router = APIRouter(prefix="/notifications", tags=["bildirimler"])


class ReadIn(BaseModel):
    ids: list[int] | None = None


@router.get("")
def list_notifications(ctx: Ctx = Depends(get_ctx), user: User = Depends(current_user)) -> dict:
    return notifications.list_for(ctx, user)


@router.get("/unread")
def unread(ctx: Ctx = Depends(get_ctx), user: User = Depends(current_user)) -> dict:
    return {"unread": notifications.unread_count(ctx, user)}


@router.post("/read")
def mark_read(body: ReadIn, ctx: Ctx = Depends(get_ctx),
              user: User = Depends(current_user)) -> dict:
    return {"marked": notifications.mark_read(ctx, user, body.ids)}
