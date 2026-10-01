from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from mesveret.context import Ctx
from mesveret.db.models import User
from mesveret.routers.deps import current_user, get_ctx, optional_user
from mesveret.services import topics

router = APIRouter(tags=["konular"])


class MessageIn(BaseModel):
    text: str
    reply_to: int | None = None
    media_ids: list[str] = Field(default_factory=list)


class EditIn(BaseModel):
    text: str


@router.get("/topics")
def list_topics(area_id: str | None = None, ctx: Ctx = Depends(get_ctx)) -> list[dict]:
    return topics.list_topics(ctx, area_id)


@router.get("/topics/{topic_id}")
def topic(topic_id: int, ctx: Ctx = Depends(get_ctx),
          viewer: User | None = Depends(optional_user)) -> dict:
    return topics.topic_view(ctx, topic_id, viewer)


@router.post("/topics/{topic_id}/messages", status_code=status.HTTP_201_CREATED)
def post_message(topic_id: int, body: MessageIn, ctx: Ctx = Depends(get_ctx),
                 user: User = Depends(current_user)) -> dict:
    msg = topics.post_message(ctx, user, topic_id, body.text, body.reply_to,
                              media_ids=body.media_ids)
    return {"id": msg.id}


@router.put("/messages/{message_id}")
def edit_message(message_id: int, body: EditIn, ctx: Ctx = Depends(get_ctx),
                 user: User = Depends(current_user)) -> dict:
    v = topics.edit_own_message(ctx, user, message_id, body.text)
    return {"id": message_id, "version": v.version_no}


@router.get("/messages/{message_id}/history")
def history(message_id: int, ctx: Ctx = Depends(get_ctx)) -> dict:
    return topics.message_history(ctx, message_id)
