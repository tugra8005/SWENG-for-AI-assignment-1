from fastapi import APIRouter, Depends, Query

from mesveret.context import Ctx
from mesveret.routers.deps import get_ctx
from mesveret.services import search as search_service

router = APIRouter(tags=["arama"])


@router.get("/search")
def search(q: str = Query(..., max_length=100), ctx: Ctx = Depends(get_ctx)) -> dict:
    return search_service.search(ctx, q)
