from fastapi import APIRouter, Depends

from mesveret.context import Ctx
from mesveret.errors import DomainError, NotFound
from mesveret.routers.deps import get_ctx
from mesveret.services import ledger

router = APIRouter(prefix="/ledger", tags=["defter"])


@router.get("/verify")
def verify(ctx: Ctx = Depends(get_ctx)) -> dict:
    """Üç düğümün zincir bütünlüğünü ve birbirleriyle tutarlılığını denetler."""
    ledger.flush(ctx)
    return ledger.verify_nodes(ctx.ledger)


@router.get("/records/{hash_prefix}")
def record(hash_prefix: str, ctx: Ctx = Depends(get_ctx)) -> dict:
    prefix = hash_prefix.strip().lower()
    if len(prefix) < 6:
        raise DomainError("Hash'in en az 6 karakterini girin.")
    rec = ledger.record_by_hash(ctx.ledger, prefix)
    if rec is None:
        raise NotFound("Bu hash ile başlayan bir defter kaydı yok.")
    return rec
