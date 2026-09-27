from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from mesveret.context import Ctx
from mesveret.db.models import Topic, User
from mesveret.domain.scopes import interest_scope_id
from mesveret.routers.deps import get_ctx, optional_user
from mesveret.services import ontology, regulation

router = APIRouter(tags=["ontoloji"])


@router.get("/areas")
def areas(ctx: Ctx = Depends(get_ctx), viewer: User | None = Depends(optional_user)) -> list[dict]:
    counts = dict(ctx.db.execute(
        select(Topic.area_id, func.count()).where(Topic.deleted_by_proposal_id.is_(None))
        .group_by(Topic.area_id)
    ).all())
    mine = {m.scope_id: m for m in ctx.graph.memberships(viewer.id)} if viewer else {}
    out = []
    for a in ctx.graph.all_areas():
        scope_id = interest_scope_id(a.id)
        out.append({
            "id": a.id, "name": a.name, "parent_id": a.parent_id, "keywords": list(a.keywords),
            "topic_count": counts.get(a.id, 0), "interest_scope_id": scope_id,
            "membership": ontology.membership_view(ctx, mine[scope_id]) if scope_id in mine else None,
        })
    return out


@router.get("/scopes")
def scopes(ctx: Ctx = Depends(get_ctx), viewer: User | None = Depends(optional_user)) -> list[dict]:
    ids = ["genel"] + [s.id for s in ctx.graph.city_scopes()]
    ids += [f"yas:{g}" for g in ("18-24", "25-34", "35-49", "50+")]
    ids += [interest_scope_id(a.id) for a in ctx.graph.all_areas()]
    out = []
    for sid in ids:
        s = ctx.graph.scope(sid)
        if s is None:
            continue
        entry = {"id": s.id, "name": s.name, "type": str(s.type),
                 "subtype": str(s.subtype) if s.subtype else None}
        if viewer is not None:
            right = ontology.vote_right(ctx, viewer.id, s.id)
            entry["has_vote_right"] = right.has_right
            entry["vote_right_reason"] = right.reason
        out.append(entry)
    return out


@router.get("/resources")
def resources(ctx: Ctx = Depends(get_ctx)) -> list[dict]:
    out = []
    for r in sorted(ctx.graph.all_resources(), key=lambda r: (str(r.kind), r.name)):
        out.append({
            "id": r.id, "name": r.name, "kind": str(r.kind),
            "owner_scope_id": r.owner_scope_id, "owner": ontology.scope_label(ctx, r.owner_scope_id),
            "divisible": r.divisible,
            "division_type": str(r.division_type) if r.division_type else None,
            "shares": [
                {"scope_id": sid, "name": ontology.scope_label(ctx, sid), "points": pts}
                for sid, pts in r.shares.items()
            ],
        })
    return out


@router.get("/regulation")
def regulation_articles(ctx: Ctx = Depends(get_ctx)) -> list[dict]:
    return regulation.listing(ctx)
