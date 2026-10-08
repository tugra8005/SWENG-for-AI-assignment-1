from fastapi import APIRouter, Depends, Query

from mesveret.context import Ctx
from mesveret.routers.deps import get_ctx
from mesveret.services import news

router = APIRouter(tags=["gazete"])


@router.get("/news")
def front_page(limit: int = Query(30, ge=1, le=60), ctx: Ctx = Depends(get_ctx)) -> dict:
    return news.front_page(ctx, limit)
