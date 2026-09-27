"""Yalnızca Docker'sız yerel geliştirme sunucusunda açılan araçlar (CLI komutlarının karşılığı)."""

from datetime import timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from mesveret.context import Ctx
from mesveret.routers.deps import get_ctx
from mesveret.services import devtools

router = APIRouter(prefix="/_dev", tags=["geliştirme"])


class AdvanceIn(BaseModel):
    days: float = 0
    hours: float = 0
    minutes: float = 0


class DecisionHourIn(BaseModel):
    close: bool = False
    scripted: bool = True


@router.post("/advance-time")
def advance(body: AdvanceIn, ctx: Ctx = Depends(get_ctx)) -> dict:
    delta = timedelta(days=body.days, hours=body.hours, minutes=body.minutes)
    return devtools.advance(ctx, ctx.now + delta)


@router.post("/run-karar-saati")
def run_decision_hour(body: DecisionHourIn, ctx: Ctx = Depends(get_ctx)) -> dict:
    if body.close:
        return devtools.close_decision_hour(ctx)
    return devtools.open_decision_hour(ctx, scripted=body.scripted)
