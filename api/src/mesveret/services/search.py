"""Arama: konular, öneriler, tartışma mesajları, dilekçeler ve etkinlikler.

Eşleme Türkçe küçük harf kurallarıyla yapılır ("İSTANBUL" = "istanbul", "ılık" ≠ "ilik"):
PostgreSQL'in ``lower`` işlevi yerel ayara bağlıdır ve I/İ'yi Türkçe çevirmez. Bu yüzden adaylar
okunup Python'da ``domain.text.turkish_lower`` ile süzülür; her türde en yeni ``SCAN`` kayıt
taranır. Silinmiş içerik, Mahzen ve taslaklar aranmaz.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from mesveret.context import Ctx
from mesveret.db.models import (
    CalendarEvent,
    Message,
    MessageVersion,
    Petition,
    Proposal,
    Topic,
)
from mesveret.domain.text import turkish_lower
from mesveret.errors import DomainError

SCAN = 2000
PER_KIND = 8


def _snippet(text: str, needle: str, width: int = 70) -> str:
    flat = " ".join(text.split())
    i = turkish_lower(flat).find(needle)
    if i < 0:
        return flat[: width * 2] + ("…" if len(flat) > width * 2 else "")
    start, end = max(0, i - width), min(len(flat), i + len(needle) + width)
    return ("…" if start else "") + flat[start:end] + ("…" if end < len(flat) else "")


def _hit(text: str, needle: str) -> bool:
    return needle in turkish_lower(text)


def search(ctx: Ctx, q: str) -> dict[str, Any]:
    needle = turkish_lower(" ".join(q.split()))
    if len(needle) < 2:
        raise DomainError("Aramak için en az iki harf yazın.")
    out: dict[str, list[dict]] = {"konular": [], "oneriler": [], "mesajlar": [],
                                  "dilekceler": [], "etkinlikler": []}
    live = {t.id: t for t in ctx.db.execute(select(Topic).where(
        Topic.deleted_by_proposal_id.is_(None)).order_by(Topic.id.desc()).limit(SCAN)).scalars()}
    for t in live.values():
        if _hit(t.title, needle) and len(out["konular"]) < PER_KIND:
            out["konular"].append({"id": t.id, "title": t.title, "link": f"/konu/{t.id}",
                                   "snippet": "karara bağlandı" if t.status == "CLOSED" else "açık"})
    for p in ctx.db.execute(select(Proposal).where(Proposal.status != "DRAFT")
                            .order_by(Proposal.id.desc()).limit(SCAN)).scalars():
        if len(out["oneriler"]) >= PER_KIND:
            break
        if _hit(p.title, needle) or _hit(p.body, needle):
            out["oneriler"].append({"id": p.id, "title": f"№{p.id} {p.title}",
                                    "link": f"/oneri/{p.id}", "snippet": _snippet(p.body, needle)})
    rows = ctx.db.execute(
        select(Message, MessageVersion).join(MessageVersion, (MessageVersion.message_id == Message.id)
                                             & (MessageVersion.version_no == Message.current_version))
        .where(Message.deleted_by_proposal_id.is_(None)).order_by(Message.id.desc()).limit(SCAN)
    ).all()
    for msg, ver in rows:
        if len(out["mesajlar"]) >= PER_KIND:
            break
        t = live.get(msg.topic_id)
        if t is not None and _hit(ver.text, needle):
            out["mesajlar"].append({"id": msg.id, "title": t.title,
                                    "link": f"/konu/{t.id}", "snippet": _snippet(ver.text, needle)})
    for pet in ctx.db.execute(select(Petition).order_by(Petition.id.desc()).limit(SCAN)).scalars():
        if pet.topic_id in live and (_hit(pet.subject, needle) or _hit(pet.text, needle)) \
                and len(out["dilekceler"]) < PER_KIND:
            out["dilekceler"].append({"id": pet.id, "title": f"{pet.number} · {pet.subject}",
                                      "link": f"/dilekce/{pet.id}",
                                      "snippet": _snippet(pet.text, needle)})
    for ev in ctx.db.execute(select(CalendarEvent).order_by(CalendarEvent.starts_at.desc())
                             .limit(SCAN)).scalars():
        if ev.topic_id in live and (_hit(ev.title, needle) or _hit(ev.venue_text, needle)) \
                and len(out["etkinlikler"]) < PER_KIND:
            out["etkinlikler"].append({"id": ev.id, "title": ev.title,
                                       "link": f"/etkinlik/{ev.id}", "snippet": ev.venue_text})
    return {"q": q, "total": sum(len(v) for v in out.values()), "groups": out}
