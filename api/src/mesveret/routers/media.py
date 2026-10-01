from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status

from mesveret.context import Ctx
from mesveret.db.models import User
from mesveret.domain import images
from mesveret.routers.deps import current_user, get_ctx
from mesveret.services import media

router = APIRouter(prefix="/media", tags=["görseller"])


@router.post("", status_code=status.HTTP_201_CREATED)
def upload(file: UploadFile = File(...), alt: str = Form(""), ctx: Ctx = Depends(get_ctx),
           user: User = Depends(current_user)) -> dict:
    data = file.file.read(images.MAX_BYTES + 1)
    return media.view(media.upload(ctx, user, data, alt))


@router.get("/{media_id}")
def meta(media_id: str, ctx: Ctx = Depends(get_ctx)) -> dict:
    return media.view(media.get_media(ctx, media_id))


@router.get("/{media_id}/{variant}")
def content(media_id: str, variant: str, ctx: Ctx = Depends(get_ctx)) -> Response:
    data, mime = media.content(ctx, media_id, variant)
    # Kısa önbellek: içerik silinirse görsel de bir saat içinde her yerden düşer.
    return Response(content=data, media_type=mime,
                    headers={"Cache-Control": "public, max-age=3600"})
