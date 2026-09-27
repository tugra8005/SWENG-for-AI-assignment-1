from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Header, Request

from mesveret import clock
from mesveret.context import Ctx
from mesveret.db.models import User
from mesveret.errors import Unauthorized
from mesveret.services.auth import decode_token


def get_ctx(request: Request) -> Iterator[Ctx]:
    state = request.app.state
    db = state.sessionmaker()
    try:
        now = clock.now(db)
        db.commit()
        yield Ctx(db=db, graph=state.graph, now=now, settings=state.settings, ledger=state.ledger)
    finally:
        db.close()


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def optional_user(
    ctx: Ctx = Depends(get_ctx), authorization: str | None = Header(default=None)
) -> User | None:
    token = _bearer(authorization)
    if token is None:
        return None
    user = ctx.db.get(User, decode_token(ctx.settings, token))
    if user is None or not user.email_verified:
        raise Unauthorized("Oturum geçersiz; yeniden giriş yapın.")
    return user


def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise Unauthorized("Bu işlem için giriş yapmalısınız.")
    return user
