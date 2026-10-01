from fastapi import APIRouter, Depends

from mesveret.context import Ctx
from mesveret.errors import DomainError, NotFound
from mesveret.routers.deps import get_ctx
from mesveret.services import ledger, regulation

router = APIRouter(prefix="/ledger", tags=["defter"])


@router.get("/verify")
def verify(ctx: Ctx = Depends(get_ctx)) -> dict:
    """Üç düğümün zincir bütünlüğünü ve birbirleriyle tutarlılığını denetler; çalışan kodun
    uyguladığı yönetmeliği defterdeki son yönetmelik kaydıyla karşılaştırır."""
    ledger.flush(ctx)
    result = ledger.verify_nodes(ctx.ledger)
    result["yonetmelik"] = regulation.verify_state(ctx)
    return result


@router.get("/recent")
def recent(limit: int = 5, ctx: Ctx = Depends(get_ctx)) -> dict:
    """Defterin ucu (son kayıt numarası ve mührü) ve son kayıtlar; künye ve "Defterden" kutusu için."""
    result = ledger.recent(ctx.ledger, max(1, min(limit, 20)))
    if result is None:
        raise DomainError("Deftere şu anda ulaşılamıyor.")
    return result


@router.get("/records/{hash_prefix}")
def record(hash_prefix: str, ctx: Ctx = Depends(get_ctx)) -> dict:
    prefix = hash_prefix.strip().lower()
    if len(prefix) < 6:
        raise DomainError("Hash'in en az 6 karakterini girin.")
    rec = ledger.record_by_hash(ctx.ledger, prefix)
    if rec is None:
        raise NotFound("Bu hash ile başlayan bir defter kaydı yok.")
    return rec
