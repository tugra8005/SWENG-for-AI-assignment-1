"""Muhataplar ve dilekçeler.

Kurum muhataplı bir konu kabul edilince kuruma talep dilekçesi gider (``TALEP``); konu karara
bağlanınca Karar, karar bildirimi olarak aynı kuruma iletilir (``KARAR``). Kurumun yanıtını
konunun bir katılımcısı işler: yazının metni, tarihi, sayısı ve isteğe bağlı taranmış görüntüsü.
3071 sayılı Dilekçe Hakkının Kullanılmasına Dair Kanun'a göre yanıt süresi 30 gündür; süre
geçince dilekçe "süresinde yanıt verilmedi" olarak görünür (hesaplanır, zamanlayıcı işi yok).

İletim sitede kayıttır: gerçek bir kuruma e-posta ya da e-Devlet başvurusu gönderilmez. Defter
dilekçenin metnini ve alıcılarını, yanıtı ve onu işleyeni mühürler.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from mesveret.context import Ctx
from mesveret.db.models import (
    Message,
    Objection,
    Petition,
    PetitionReply,
    Proposal,
    SessionItem,
    Topic,
    User,
)
from mesveret.domain import addressees
from mesveret.domain.addressees import Addressee, AddresseeKind
from mesveret.errors import Conflict, DomainError, Forbidden, NotFound
from mesveret.services import events, ledger, media, ontology
from mesveret.services.profile import nickname_map

REPLY_DAYS = 30  # 3071 sayılı Kanun, md. 7
TZ = ZoneInfo("Europe/Istanbul")
MAX_REPLY = 10_000


# --- muhataplar -------------------------------------------------------------------------------------


def lookup(ctx: Ctx, addressee_id: str | None) -> Addressee | None:
    return addressees.lookup(addressee_id, ctx.cities)


def addressee_view(ctx: Ctx, addressee_id: str | None) -> dict | None:
    a = lookup(ctx, addressee_id)
    if a is None:
        return None
    return {"id": a.id, "kind": str(a.kind), "name": a.name, "short": a.short, "level": a.level}


def catalog(ctx: Ctx, scope_id: str | None) -> list[dict]:
    """Öneri formu için: muhataplar ve seçilen kapsamın her birine yazıp yazamayacağı (R9)."""
    scope = ctx.graph.scope(scope_id) if scope_id else None
    out = []
    for a in addressees.catalog(ctx.cities):
        refusal = addressees.jurisdiction_refusal(scope, a) if scope else None
        out.append({"id": a.id, "kind": str(a.kind), "name": a.name, "short": a.short,
                    "level": a.level, "allowed": refusal is None, "refusal": refusal})
    return out


# --- gönderim ---------------------------------------------------------------------------------------


def _basis(ctx: Ctx, p: Proposal) -> dict[str, Any]:
    if p.session_id is not None:
        return {"kind": "KARAR_SAATI", "session_id": p.session_id}
    from mesveret.services import proposals  # proposals bu modülü içe aktarır

    count = ctx.db.execute(select(func.count()).select_from(Objection).where(
        Objection.proposal_id == p.id)).scalar_one()
    return {"kind": "SESSIZ_ONAY", "objections": count,
            "threshold": proposals.objection_threshold(ctx, p)}


def send(ctx: Ctx, topic: Topic, p: Proposal, kind: str, text: str) -> Petition | None:
    """Konunun muhatabı bir kurumsa dilekçeyi iletir; takvim ve iç düzen için ``None``."""
    a = lookup(ctx, topic.addressee)
    if a is None or a.kind is not AddresseeKind.KURUM:
        return None
    to = addressees.recipients(a, ctx.cities)
    subject = topic.title if kind == "TALEP" else f"{topic.title}: karar bildirimi"
    pet = Petition(
        kind=kind, topic_id=topic.id, proposal_id=p.id, addressee=a.id,
        recipients=[{"id": r.id, "name": r.name} for r in to], subject=subject[:200], text=text,
        basis=_basis(ctx, p), sent_at=ctx.now,
    )
    ctx.db.add(pet)
    ctx.db.flush()
    ledger.enqueue(ctx, "DILEKCE_ILETILDI", {
        "evrak": pet.number, "tur": kind, "konu": topic.id, "oneri": p.id,
        "alicilar": [r.name for r in to], "baslik": pet.subject, "metin": text,
        "dayanak": pet.basis,
    }, ref=pet)
    events.publish(ctx, events.PetitionSent(pet, p.proposer_id))
    return pet


@events.subscribe(events.TopicAccepted)
def _on_topic_accepted(ctx: Ctx, e: events.TopicAccepted) -> None:
    """Kurum muhataplı konu: kabul edilen talep kuruma dilekçe olarak gider."""
    send(ctx, e.topic, e.proposal, "TALEP", e.proposal.body)


@events.subscribe(events.DecisionMade)
def _on_decision_made(ctx: Ctx, e: events.DecisionMade) -> None:
    """Kurum muhataplı konunun Kararı aynı kuruma karar bildirimi olarak iletilir."""
    send(ctx, e.topic, e.proposal, "KARAR", e.decision.text)


# --- yanıt ------------------------------------------------------------------------------------------


def get_petition(ctx: Ctx, petition_id: int) -> Petition:
    pet = ctx.db.get(Petition, petition_id)
    if pet is None:
        raise NotFound("Dilekçe bulunamadı.")
    return pet


def _today(ctx: Ctx) -> date:
    return ctx.now.astimezone(TZ).date()


def reply_refusal(ctx: Ctx, pet: Petition, user: User | None) -> str | None:
    if user is None:
        return "Yanıtı işlemek için giriş yapın."
    from mesveret.services import topics  # topics media'yı, media bu modülü değil

    topic = ctx.db.get(Topic, pet.topic_id)
    if topic is None or topic.deleted_by_proposal_id is not None:
        return "Konu silindi."
    if not topics.is_participant(ctx, topic, user.id):
        return "Kurumun yanıtını yalnızca konunun katılımcıları işleyebilir."
    return None


def add_reply(ctx: Ctx, user: User, petition_id: int, *, recipient_id: str, text: str,
              replied_on: date, reference: str | None = None,
              media_id: str | None = None) -> PetitionReply:
    pet = get_petition(ctx, petition_id)
    if (refusal := reply_refusal(ctx, pet, user)) is not None:
        raise Forbidden(refusal)
    names = {r["id"]: r["name"] for r in pet.recipients}
    if recipient_id not in names:
        raise DomainError("Bu kurum dilekçenin alıcıları arasında değil.")
    exists = ctx.db.execute(select(PetitionReply.id).where(
        PetitionReply.petition_id == pet.id, PetitionReply.recipient_id == recipient_id)).first()
    if exists:
        raise Conflict(f"{names[recipient_id]} yanıtı zaten işlendi.")
    text = (text or "").strip()
    if not text:
        raise DomainError("Yanıtın metni boş olamaz.")
    if len(text) > MAX_REPLY:
        raise DomainError(f"Yanıt en fazla {MAX_REPLY} karakter olabilir.")
    sent_on = pet.sent_at.astimezone(TZ).date()
    if replied_on < sent_on:
        raise DomainError("Yanıtın tarihi dilekçenin iletildiği günden önce olamaz.")
    if replied_on > _today(ctx):
        raise DomainError("Yanıtın tarihi bugünden sonra olamaz.")
    scan = media.check_attachable(ctx, user.id, [media_id] if media_id else [], limit=1)
    reply = PetitionReply(
        petition_id=pet.id, recipient_id=recipient_id, text=text,
        reference=(reference or "").strip()[:80] or None, replied_on=replied_on,
        entered_by=user.id, entered_at=ctx.now,
    )
    ctx.db.add(reply)
    ctx.db.flush()
    ledger.enqueue(ctx, "DILEKCE_YANITI", {
        "evrak": pet.number, "kurum": names[recipient_id], "metin": text,
        "tarih": replied_on.isoformat(), "sayi": reply.reference, "isleyen": user.nickname,
    }, ref=reply)
    media.attach(ctx, scan, "yanit", reply.id)
    events.publish(ctx, events.PetitionReplied(pet, reply, names[recipient_id], user.id))
    ctx.commit()
    return reply


# --- görünümler -------------------------------------------------------------------------------------


def due_at(pet: Petition) -> datetime:
    return pet.sent_at + timedelta(days=REPLY_DAYS)


def signature(ctx: Ctx, pet: Petition) -> str:
    """İmza satırı: kararın nasıl alındığı (Karar Saati sonucu ya da sessiz onay)."""
    b = pet.basis or {}
    if b.get("kind") == "KARAR_SAATI":
        item = ctx.db.execute(select(SessionItem).where(
            SessionItem.session_id == b["session_id"], SessionItem.proposal_id == pet.proposal_id,
            SessionItem.concurrent.is_(False))).scalar_one_or_none()
        r = (item.result if item else None) or {}
        head = f"Karar Saati #{b['session_id']}"
        if r.get("kind") == "binary":
            return (f"{head}: {r['yes']} ağırlıklı EVET, {r['no']} HAYIR · "
                    f"{r['eligible']} seçmen")
        if r.get("kind") == "approval":
            score = next((s["score"] for s in r.get("scores", [])
                          if s["text_id"] == r.get("winner")), 0)
            return f"{head}: kazanan metin {score} ağırlıklı onay aldı · {r['eligible']} seçmen"
        return head
    return (f"Sessiz onay: itiraz süresi {b.get('objections', 0)} itirazla doldu "
            f"(eşik {b.get('threshold', '—')}); itirazsız kabul.")


def _replies(ctx: Ctx, pet_ids: list[int]) -> dict[int, list[PetitionReply]]:
    out: dict[int, list[PetitionReply]] = {}
    if not pet_ids:
        return out
    for r in ctx.db.execute(select(PetitionReply).where(
            PetitionReply.petition_id.in_(pet_ids)).order_by(PetitionReply.id)).scalars():
        out.setdefault(r.petition_id, []).append(r)
    return out


def _recipient_rows(ctx: Ctx, pet: Petition, replies: list[PetitionReply],
                    full: bool) -> list[dict]:
    by_id = {r.recipient_id: r for r in replies}
    scans = media.attached(ctx, "yanit", [r.id for r in replies]) if full else {}
    names = nickname_map(ctx, [r.entered_by for r in replies]) if full else {}
    late = ctx.now >= due_at(pet)
    rows = []
    for rec in pet.recipients:
        r = by_id.get(rec["id"])
        row: dict[str, Any] = {
            "id": rec["id"], "name": rec["name"],
            "status": "YANITLANDI" if r else ("SURE_DOLDU" if late else "BEKLIYOR"),
        }
        if r is not None:
            row["reply"] = {"id": r.id, "replied_on": r.replied_on, "reference": r.reference,
                            "entered_at": r.entered_at, "ledger_hash": r.ledger_hash,
                            **({"text": r.text, "entered_by": names.get(r.entered_by),
                                "media": scans.get(r.id, [])} if full else {})}
        rows.append(row)
    return rows


def summary(ctx: Ctx, pet: Petition, replies: list[PetitionReply]) -> dict:
    rows = _recipient_rows(ctx, pet, replies, full=False)
    return {
        "id": pet.id, "number": pet.number, "kind": pet.kind, "topic_id": pet.topic_id,
        "proposal_id": pet.proposal_id, "subject": pet.subject, "sent_at": pet.sent_at,
        "due_at": due_at(pet), "addressee": addressee_view(ctx, pet.addressee),
        "recipients": rows, "replied": sum(r["status"] == "YANITLANDI" for r in rows),
        "overdue": sum(r["status"] == "SURE_DOLDU" for r in rows),
    }


def for_topic(ctx: Ctx, topic_id: int) -> list[dict]:
    pets = ctx.db.execute(select(Petition).where(Petition.topic_id == topic_id)
                          .order_by(Petition.id)).scalars().all()
    replies = _replies(ctx, [p.id for p in pets])
    return [summary(ctx, p, replies.get(p.id, [])) for p in pets]


def listing(ctx: Ctx, limit: int = 50) -> list[dict]:
    pets = ctx.db.execute(select(Petition).order_by(Petition.sent_at.desc(), Petition.id.desc())
                          .limit(limit)).scalars().all()
    replies = _replies(ctx, [p.id for p in pets])
    return [summary(ctx, p, replies.get(p.id, [])) for p in pets]


def view(ctx: Ctx, petition_id: int, viewer: User | None) -> dict:
    pet = get_petition(ctx, petition_id)
    topic = ctx.db.get(Topic, pet.topic_id)
    if topic is None:
        raise NotFound("Dilekçenin konusu bulunamadı.")
    if topic.deleted_by_proposal_id is not None:
        raise media.Gone(f"Bu dilekçenin konusu #{topic.deleted_by_proposal_id} numaralı "
                         "oylamayla silindi; dilekçenin kaydı defterde durur.")
    p = ctx.db.get(Proposal, pet.proposal_id)
    replies = _replies(ctx, [pet.id]).get(pet.id, [])
    body = summary(ctx, pet, replies)
    proposer = ctx.db.get(User, p.proposer_id) if p else None
    signers = ctx.db.execute(select(func.count(func.distinct(Message.author_id))).where(
        Message.topic_id == topic.id)).scalar_one()
    body.update({
        "text": pet.text, "signature": signature(ctx, pet), "ledger_hash": pet.ledger_hash,
        "recipients": _recipient_rows(ctx, pet, replies, full=True),
        "topic": {"id": topic.id, "title": topic.title, "area_name":
                  ontology.area_name(ctx, topic.area_id), "participants": signers},
        "scope": ontology.scope_label(ctx, p.scope_id) if p else None,
        "proposer": proposer.nickname if proposer else None,
        "reply_days": REPLY_DAYS,
        "viewer": {"can_reply": reply_refusal(ctx, pet, viewer) is None,
                   "reply_refusal": reply_refusal(ctx, pet, viewer)},
    })
    return body
