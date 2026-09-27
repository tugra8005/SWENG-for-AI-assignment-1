from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from mesveret.context import Ctx
from mesveret.db.models import User
from mesveret.routers.deps import current_user, get_ctx
from mesveret.services import cellar

router = APIRouter(prefix="/cellar", tags=["mahzen"])


class ThreadIn(BaseModel):
    title: str
    text: str
    acknowledge: bool = False


class PostIn(BaseModel):
    text: str
    acknowledge: bool = False


class RevealBallotIn(BaseModel):
    yes: bool


@router.get("/entry")
def entry(user: User = Depends(current_user)) -> dict:
    return cellar.entry_status(user)


@router.post("/entry/ack")
def acknowledge(ctx: Ctx = Depends(get_ctx), user: User = Depends(current_user)) -> dict:
    cellar.acknowledge_entry(ctx, user)
    return {"ok": True}


@router.get("/threads")
def threads(ctx: Ctx = Depends(get_ctx), user: User = Depends(current_user)) -> dict:
    return cellar.list_threads(ctx, user)


@router.post("/threads", status_code=status.HTTP_201_CREATED)
def create_thread(body: ThreadIn, ctx: Ctx = Depends(get_ctx),
                  user: User = Depends(current_user)) -> dict:
    t = cellar.create_thread(ctx, user, body.title, body.text, acknowledge=body.acknowledge)
    return {"id": t.id}


@router.get("/threads/{thread_id}")
def thread(thread_id: int, ctx: Ctx = Depends(get_ctx), user: User = Depends(current_user)) -> dict:
    return cellar.thread_view(ctx, thread_id, user)


@router.get("/revealed/{thread_id}")
def revealed(thread_id: int, ctx: Ctx = Depends(get_ctx)) -> dict:
    return cellar.revealed_thread(ctx, thread_id)


@router.post("/threads/{thread_id}/posts", status_code=status.HTTP_201_CREATED)
def reply(thread_id: int, body: PostIn, ctx: Ctx = Depends(get_ctx),
          user: User = Depends(current_user)) -> dict:
    post = cellar.reply(ctx, user, thread_id, body.text, acknowledge=body.acknowledge)
    return {"no": post.id}


@router.post("/posts/{post_id}/sign")
def sign(post_id: int, ctx: Ctx = Depends(get_ctx), user: User = Depends(current_user)) -> dict:
    cellar.sign_post(ctx, user, post_id)
    return {"ok": True}


@router.post("/threads/{thread_id}/reveal-vote", status_code=status.HTTP_201_CREATED)
def open_vote(thread_id: int, ctx: Ctx = Depends(get_ctx),
              user: User = Depends(current_user)) -> dict:
    vote = cellar.open_reveal_vote(ctx, user, thread_id)
    return {"electorate_size": len(vote.electorate), "flagged": len(vote.flagged)}


@router.put("/threads/{thread_id}/reveal-vote")
def cast(thread_id: int, body: RevealBallotIn, ctx: Ctx = Depends(get_ctx),
         user: User = Depends(current_user)) -> dict:
    return cellar.cast_reveal_vote(ctx, user, thread_id, body.yes)
