"""Gazete: kararlardan türetilen haberler (Meydan'ın ön sayfası).

Haber yazılmaz, hesaplanır: kabul edilen konular, Kararlar, dilekçeler ve yanıtları, yanıtsız
kalan dilekçeler, takvime eklenen ve gerçekleşen etkinlikler, yönetmelik değişiklikleri ve
silinen içerik. Manşet ve spot kalıptan üretilir; her haber kaydın kendisine bağlanır.
Silinen konunun haberleri yayımlanmaz.

Her haber türü bir üreticidir (``SOURCES``): yeni bir haber türü, yeni bir üretici fonksiyondur.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any

from sqlalchemy import select

from mesveret.context import Ctx
from mesveret.db.models import (
    CalendarEvent,
    Decision,
    EventReport,
    Petition,
    PetitionReply,
    Proposal,
    Topic,
)
from mesveret.domain.regulation import article_title
from mesveret.domain.rules import format_date
from mesveret.services import calendar, media, ontology, petitions
from mesveret.services.profile import nickname_map

LIMIT = 30


def _clip(text: str, n: int) -> str:
    text = " ".join(text.split())
    if len(text) <= n:
        return text
    cut = text[: n - 1].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + "…"


def _sentence(text: str, n: int = 110) -> str:
    """Metnin ilk cümlesi (kısaltılarak)."""
    first = " ".join(text.split()).split(". ")[0].rstrip(".")
    return _clip(first, n)


def _item(kind: str, ref: int, at: datetime, kicker: str, headline: str, dek: str,
          link: str, *, image: dict | None = None, area: str | None = None,
          lines: list[str] | None = None) -> dict[str, Any]:
    return {"id": f"{kind}:{ref}", "kind": kind, "at": at, "kicker": kicker,
            "headline": headline, "dek": dek, "link": link, "image": image, "area": area,
            "lines": lines or []}


def _live_topics(ctx: Ctx) -> dict[int, Topic]:
    return {t.id: t for t in ctx.db.execute(
        select(Topic).where(Topic.deleted_by_proposal_id.is_(None))).scalars()}


def _addressee_line(ctx: Ctx, topic: Topic) -> str:
    a = petitions.lookup(ctx, topic.addressee)
    return f"Muhatap: {a.name}" if a else ""


def topics_accepted(ctx: Ctx, live: dict[int, Topic]) -> Iterator[dict]:
    with_event = set(ctx.db.execute(select(CalendarEvent.topic_id)).scalars())
    for t in live.values():
        # Etkinlikli konunun haberi "Takvime eklendi"dir; aynı konu iki kez yazılmaz.
        if t.accepted_proposal_id is None or t.id in with_event:
            continue
        p = ctx.db.get(Proposal, t.accepted_proposal_id)
        how = "Karar Saati'nde kabul edildi" if p and p.session_id else "itirazsız kabul edildi"
        scope = ontology.scope_label(ctx, t.owner_scope_id)
        yield _item("KONU", t.id, t.created_at, "Yeni konu", t.title,
                    f"{scope} {how}. {_addressee_line(ctx, t)}".strip(), f"/konu/{t.id}",
                    image=media.cover(ctx, t.accepted_proposal_id),
                    area=ontology.area_name(ctx, t.area_id))


def decisions(ctx: Ctx, live: dict[int, Topic]) -> Iterator[dict]:
    for d in ctx.db.execute(select(Decision)).scalars():
        t = live.get(d.topic_id)
        if t is None:
            continue
        sent = ctx.db.execute(select(Petition).where(
            Petition.topic_id == t.id, Petition.kind == "KARAR")).scalar_one_or_none()
        dek = f"{t.title} konusu karara bağlandı."
        if sent is not None:
            dek += f" Karar {len(sent.recipients)} kuruma iletildi ({sent.number})."
        yield _item("KARAR", d.id, d.created_at, "Karar", _sentence(d.text), dek,
                    f"/konu/{t.id}", image=media.cover(ctx, t.accepted_proposal_id)
                    if t.accepted_proposal_id else None, area=ontology.area_name(ctx, t.area_id),
                    lines=[_clip(d.text, 280)])


def petitions_sent(ctx: Ctx, live: dict[int, Topic]) -> Iterator[dict]:
    for pet in ctx.db.execute(select(Petition).where(Petition.kind == "TALEP")).scalars():
        t = live.get(pet.topic_id)
        if t is None:
            continue
        to = ", ".join(r["name"] for r in pet.recipients)
        yield _item("DILEKCE", pet.id, pet.sent_at, "Dilekçe", f"Dilekçe iletildi: {pet.subject}",
                    f"Alıcı: {to}. Yasal yanıt süresi {format_date(petitions.due_at(pet))[:10]}.",
                    f"/dilekce/{pet.id}", area=ontology.area_name(ctx, t.area_id),
                    lines=[pet.number])


def replies(ctx: Ctx, live: dict[int, Topic]) -> Iterator[dict]:
    for r, pet in ctx.db.execute(select(PetitionReply, Petition).join(
            Petition, Petition.id == PetitionReply.petition_id)).all():
        t = live.get(pet.topic_id)
        if t is None:
            continue
        name = next((x["name"] for x in pet.recipients if x["id"] == r.recipient_id),
                    r.recipient_id)
        scans = media.attached(ctx, "yanit", [r.id]).get(r.id, [])
        yield _item("YANIT", r.id, r.entered_at, "Yanıt", f"{name} yanıt verdi: {pet.subject}",
                    _clip(r.text, 200), f"/dilekce/{pet.id}", image=scans[0] if scans else None,
                    area=ontology.area_name(ctx, t.area_id))


def overdue(ctx: Ctx, live: dict[int, Topic]) -> Iterator[dict]:
    answered = {(pid, rid) for pid, rid in ctx.db.execute(
        select(PetitionReply.petition_id, PetitionReply.recipient_id)).all()}
    for pet in ctx.db.execute(select(Petition)).scalars():
        due = petitions.due_at(pet)
        if pet.topic_id not in live or due > ctx.now:
            continue
        silent = [x["name"] for x in pet.recipients if (pet.id, x["id"]) not in answered]
        if not silent:
            continue
        who = silent[0] if len(silent) == 1 else f"{len(silent)} kurum"
        yield _item("SURE_DOLDU", pet.id, due, "Süre doldu", f"Yanıt gelmedi: {pet.subject}",
                    f"{who} 30 günlük yasal süre içinde yanıt vermedi ({pet.number}).",
                    f"/dilekce/{pet.id}", lines=silent)


def events_planned(ctx: Ctx, live: dict[int, Topic]) -> Iterator[dict]:
    for ev in ctx.db.execute(select(CalendarEvent)).scalars():
        t = live.get(ev.topic_id)
        if t is None:
            continue
        yield _item("ETKINLIK", ev.id, ev.created_at, "Takvim", f"Takvime eklendi: {ev.title}",
                    f"{format_date(ev.starts_at)} · {ev.venue_text}", f"/etkinlik/{ev.id}",
                    image=media.cover(ctx, ev.proposal_id), area=ontology.area_name(ctx, t.area_id))


def events_held(ctx: Ctx, live: dict[int, Topic]) -> Iterator[dict]:
    for ev in ctx.db.execute(select(CalendarEvent)).scalars():
        t = live.get(ev.topic_id)
        if t is None or calendar.status(ctx, ev) != "GERCEKLESTI":
            continue
        reports = ctx.db.execute(select(EventReport).where(EventReport.event_id == ev.id)
                                 .order_by(EventReport.created_at)).scalars().all()
        if not reports:
            continue
        photos = media.attached(ctx, "rapor", [r.id for r in reports])
        image = next((m[0] for r in reports if (m := photos.get(r.id))), None)
        count = max((r.headcount or 0 for r in reports), default=0)
        names = nickname_map(ctx, [r.author_id for r in reports])
        who = ", ".join(names.get(r.author_id, "?") for r in reports)
        dek = (f"{count} kişi katıldı; " if count else "") + (
            f"raporu {who} yazdı." if len(reports) == 1 else f"raporları {who} yazdı.")
        yield _item("GERCEKLESTI", ev.id, reports[0].created_at, "Etkinlik raporu",
                    f"Gerçekleşti: {ev.title}", dek, f"/etkinlik/{ev.id}",
                    image=image or media.cover(ctx, ev.proposal_id),
                    area=ontology.area_name(ctx, t.area_id), lines=[_clip(reports[0].text, 280)])


def _value_text(value: Any) -> str:
    if not isinstance(value, dict):
        return "—"
    if "baslik" in value:
        return value["baslik"]
    parts = []
    for k, v in value.items():
        unit = {"saat": "saat", "gun": "gün"}.get(k)
        parts.append(f"{v} {unit}" if unit else (str(v) if k in ("deger", "oran") else f"{k} {v}"))
    return ", ".join(parts)


def regulation_changes(ctx: Ctx, live: dict[int, Topic]) -> Iterator[dict]:
    rows = ctx.db.execute(select(Proposal).where(
        Proposal.type == "YONETMELIK", Proposal.status == "ACCEPTED")).scalars()
    for p in rows:
        key, action = p.payload.get("article_key"), p.payload.get("action", "degistir")
        title = article_title(key, p.payload.get("new_value") or p.payload.get("old_value"))
        verb = {"ekle": "eklendi", "kaldir": "kaldırıldı"}.get(action, "değişti")
        dek = (f"{_value_text(p.payload.get('old_value'))} → "
               f"{_value_text(p.payload.get('new_value'))}" if action == "degistir"
               else _clip(p.title, 160))
        yield _item("YONETMELIK", p.id, p.decided_at or p.created_at, "Yönetmelik",
                    f"Yönetmelik {verb}: {title}", dek, f"/oneri/{p.id}")


def deletions(ctx: Ctx, live: dict[int, Topic]) -> Iterator[dict]:
    rows = ctx.db.execute(select(Proposal).where(
        Proposal.type == "SILME", Proposal.status == "ACCEPTED")).scalars()
    for p in rows:
        what = "bir mesaj" if p.payload.get("message_id") else "bir konu"
        rules = ", ".join(p.payload.get("rules") or []) or "yazarın isteği"
        yield _item("SILME", p.id, p.decided_at or p.created_at, "Silme",
                    f"Oylamayla {what} silindi",
                    f"№{p.id} oylaması · dayanak: {rules}. Defterdeki kaydı silinmez.",
                    f"/oneri/{p.id}")


SOURCES: tuple[Callable[[Ctx, dict[int, Topic]], Iterator[dict]], ...] = (
    topics_accepted, decisions, petitions_sent, replies, overdue, events_planned, events_held,
    regulation_changes, deletions,
)


def front_page(ctx: Ctx, limit: int = LIMIT) -> dict[str, Any]:
    live = _live_topics(ctx)
    items = [it for source in SOURCES for it in source(ctx, live) if it["at"] <= ctx.now]
    items.sort(key=lambda it: (it["at"], it["id"]), reverse=True)
    items = items[:limit]
    # Manşet: son yedi günün görselli en yeni haberi; yoksa en yeni haber.
    lead = next((it for it in items if it["image"] and (ctx.now - it["at"]).days < 7),
                items[0] if items else None)
    rest = [it for it in items if it is not lead]
    return {"lead": lead, "items": rest, "upcoming": calendar.upcoming(ctx)}
