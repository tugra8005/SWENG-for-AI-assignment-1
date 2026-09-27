from fastapi import APIRouter, Depends
from pydantic import BaseModel

from mesveret.context import Ctx
from mesveret.data.iller import ILLER
from mesveret.db.models import User
from mesveret.routers.deps import current_user, get_ctx, optional_user
from mesveret.services import ontology, profile

router = APIRouter(tags=["profil"])


class AddressIn(BaseModel):
    city: str
    district: str
    address_line: str = ""


@router.get("/cities")
def cities() -> list[str]:
    return list(ILLER)


@router.get("/users/{nickname}")
def public_profile(
    nickname: str, ctx: Ctx = Depends(get_ctx), viewer: User | None = Depends(optional_user)
) -> dict:
    return profile.public_profile(ctx, profile.find_user(ctx, nickname), viewer)


@router.get("/me/profile")
def my_profile(ctx: Ctx = Depends(get_ctx), user: User = Depends(current_user)) -> dict:
    body = profile.private_profile(ctx, user)
    ctx.commit()
    return body


@router.put("/me/address")
def change_address(
    body: AddressIn, ctx: Ctx = Depends(get_ctx), user: User = Depends(current_user)
) -> dict:
    profile.change_address(ctx, user, body.city, body.district, body.address_line)
    return {"message": "Adres güncellendi. Yeni şehrin kapsamında oy hakkınız "
            "bekleme süresi dolunca doğar."}


@router.post("/me/interests/{area_id}")
def join_interest(area_id: str, ctx: Ctx = Depends(get_ctx), user: User = Depends(current_user)) -> dict:
    m = ontology.join_interest(ctx, user, area_id)
    ctx.commit()
    return ontology.membership_view(ctx, m)


@router.delete("/me/interests/{area_id}")
def leave_interest(area_id: str, ctx: Ctx = Depends(get_ctx), user: User = Depends(current_user)) -> dict:
    ontology.leave_interest(ctx, user, area_id)
    ctx.commit()
    return {"message": "İlgi kapsamından ayrıldınız."}
