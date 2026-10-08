from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from mesveret.context import Ctx
from mesveret.db.models import User
from mesveret.routers.deps import current_user, get_ctx, optional_user
from mesveret.services import calendar

router = APIRouter(tags=["takvim"])


class AttendIn(BaseModel):
    coming: bool


class ReportIn(BaseModel):
    text: str
    headcount: int | None = None
    media_ids: list[str] = Field(default_factory=list)


def _site(request: Request) -> str:
    """Takvim dosyasındaki bağlantılar için sitenin adresi (istemci Origin gönderir)."""
    return request.headers.get("origin") or str(request.base_url)


@router.get("/calendar")
def listing(ctx: Ctx = Depends(get_ctx)) -> dict:
    return calendar.listing(ctx)


@router.get("/calendar.ics")
def feed(request: Request, ctx: Ctx = Depends(get_ctx)) -> Response:
    return Response(calendar.ics_for(ctx, None, _site(request)), media_type="text/calendar",
                    headers={"Content-Disposition": 'attachment; filename="mesveret.ics"'})


@router.get("/events/{event_id}")
def event(event_id: int, ctx: Ctx = Depends(get_ctx),
          viewer: User | None = Depends(optional_user)) -> dict:
    return calendar.view(ctx, event_id, viewer)


@router.get("/events/{event_id}/ics")
def event_ics(event_id: int, request: Request, ctx: Ctx = Depends(get_ctx)) -> Response:
    return Response(calendar.ics_for(ctx, event_id, _site(request)), media_type="text/calendar",
                    headers={"Content-Disposition":
                             f'attachment; filename="etkinlik-{event_id}.ics"'})


@router.put("/events/{event_id}/attendance")
def attend(event_id: int, body: AttendIn, ctx: Ctx = Depends(get_ctx),
           user: User = Depends(current_user)) -> dict:
    return calendar.attend(ctx, user, event_id, body.coming)


@router.post("/events/{event_id}/reports", status_code=status.HTTP_201_CREATED)
def report(event_id: int, body: ReportIn, ctx: Ctx = Depends(get_ctx),
           user: User = Depends(current_user)) -> dict:
    r = calendar.add_report(ctx, user, event_id, body.text, body.headcount, body.media_ids)
    return {"id": r.id}
