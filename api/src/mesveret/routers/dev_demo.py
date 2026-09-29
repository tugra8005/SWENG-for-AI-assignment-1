"""Yalnızca geliştirme ortamında (ENV=dev) eklenen uç noktalar: sınıf gösterimi için hesap
değiştirici ve demo adımı. Üretim yapılandırmasında bu yönlendirici hiç eklenmez (``main``)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from mesveret.context import Ctx
from mesveret.routers.deps import get_ctx
from mesveret.services import auth, demo
from mesveret.services.profile import find_user

router = APIRouter(prefix="/_dev", tags=["geliştirme"])


class LoginAsIn(BaseModel):
    nickname: str


@router.post("/login-as")
def login_as(body: LoginAsIn, ctx: Ctx = Depends(get_ctx)) -> dict:
    """Parolasız giriş: yalnızca geliştirme ortamında, demo sırasında hesap değiştirmek için."""
    user = find_user(ctx, body.nickname)
    return {"token": auth.create_token(ctx.settings, user.id), "nickname": user.nickname}


@router.get("/demo")
def demo_step(ctx: Ctx = Depends(get_ctx)) -> dict:
    """Şu anki demo adımı ve ekranları; demo başlamadıysa ``step: null``."""
    return demo.view(ctx) or {"step": None}
