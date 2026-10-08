"""Görseller: yükleme, içeriğe ekleme, görünürlük.

Yükleme iki adımlıdır: görsel önce yüklenir (sahibine bağlı, eksiz), sonra mesaj ya da öneriyle
birlikte eklenir. Eklenen görsel deftere ``GORSEL_EKLENDI`` olarak yazılır (özgün sürümün hash'i,
alt metin). Bağlandığı içerik oylamayla silinirse görsel de gizlenir: sitede görünmez, adresi 410
döner; defterdeki kaydı kalır.
"""

from __future__ import annotations

import secrets
from typing import Any

from sqlalchemy import func, select

from mesveret.context import Ctx
from mesveret.db.models import (
    CalendarEvent,
    EventReport,
    Media,
    Message,
    Petition,
    PetitionReply,
    Topic,
    User,
)
from mesveret.domain import images
from mesveret.errors import Conflict, DomainError, Forbidden, NotFound
from mesveret.services import ledger

MAX_PER_ITEM = 4  # bir mesaja eklenebilecek görsel
MAX_UNATTACHED = 12  # kişi başına yüklenmiş ama henüz eklenmemiş görsel
VARIANTS = {"baski": "image/png", "ozgun": "image/jpeg"}


class Gone(DomainError):
    status = 410


def new_id() -> str:
    # Harfle başlar: defter outbox'ı yalnız rakamdan oluşan kimliği tamsayı sanır.
    return "g" + secrets.token_hex(7)


def _store(ctx: Ctx, data: bytes, alt: str, *, owner_id: str | None, media_id: str | None = None,
           credit: str | None = None, source_url: str | None = None) -> Media:
    try:
        alt = images.check_alt(alt)
        processed = images.process(data)
    except images.ImageRejected as exc:
        raise DomainError(str(exc)) from exc
    m = Media(
        id=media_id or new_id(), owner_id=owner_id, sha256=processed.sha256, alt=alt,
        credit=credit, source_url=source_url, width=processed.width, height=processed.height,
        original=processed.original, print_png=processed.print, created_at=ctx.now,
    )
    ctx.db.add(m)
    ctx.db.flush()
    return m


def upload(ctx: Ctx, user: User, data: bytes, alt: str) -> Media:
    pending = ctx.db.execute(
        select(func.count()).select_from(Media).where(
            Media.owner_id == user.id, Media.attached_kind.is_(None))
    ).scalar_one()
    if pending >= MAX_UNATTACHED:
        raise Conflict(f"Henüz kullanmadığınız {pending} görsel var; önce onları bir mesaja ekleyin.")
    m = _store(ctx, data, alt, owner_id=user.id)
    ctx.commit()
    return m


def store_archive(ctx: Ctx, data: bytes, alt: str, *, media_id: str, credit: str,
                  source_url: str) -> Media:
    """Tohum: kamu malı arşiv görseli (sahibi yok; künyesi ve kaynağı görselle birlikte durur)."""
    return _store(ctx, data, alt, owner_id=None, media_id=media_id, credit=credit,
                  source_url=source_url)


def check_attachable(ctx: Ctx, user_id: str | None, media_ids: list[str] | None,
                     *, limit: int = MAX_PER_ITEM) -> list[Media]:
    """Eklenecek görselleri denetler (içerik oluşturulmadan önce çağrılır)."""
    ids = list(dict.fromkeys(media_ids or []))
    if len(ids) > limit:
        raise DomainError(f"En fazla {limit} görsel eklenebilir.")
    rows = []
    for mid in ids:
        m = ctx.db.get(Media, mid)
        if m is None:
            raise DomainError("Görsel bulunamadı; yeniden yükleyin.")
        if m.owner_id != user_id:
            raise Forbidden("Yalnızca kendi yüklediğiniz görselleri ekleyebilirsiniz.")
        if m.attached_kind is not None:
            raise Conflict("Bu görsel başka bir içeriğe eklenmiş.")
        rows.append(m)
    return rows


def attach(ctx: Ctx, rows: list[Media], kind: str, ref_id: int) -> None:
    """Denetlenmiş görselleri içeriğe bağlar ve deftere yazar."""
    if kind not in KINDS:
        raise ValueError(kind)
    owners = {m.owner_id for m in rows if m.owner_id}
    names = {u.id: u.nickname for u in ctx.db.execute(
        select(User).where(User.id.in_(owners))).scalars()} if owners else {}
    for pos, m in enumerate(rows):
        m.attached_kind, m.attached_id, m.position = kind, ref_id, pos
        ledger.enqueue(ctx, "GORSEL_EKLENDI", {
            "gorsel": m.id, "sha256": m.sha256, "alt": m.alt, "ek": f"{kind}:{ref_id}",
            "yukleyen": names.get(m.owner_id) if m.owner_id else None, "kaynak": m.credit,
        }, ref=m)


def view(m: Media) -> dict[str, Any]:
    return {"id": m.id, "alt": m.alt, "width": m.width, "height": m.height,
            "credit": m.credit, "source_url": m.source_url, "ledger_hash": m.ledger_hash}


def attached(ctx: Ctx, kind: str, ref_ids: list[int]) -> dict[int, list[dict]]:
    """İçerik kimliği → eklenmiş görseller (sırasıyla). Gizleme kararı çağırana aittir."""
    if not ref_ids:
        return {}
    out: dict[int, list[dict]] = {}
    for m in ctx.db.execute(
        select(Media).where(Media.attached_kind == kind, Media.attached_id.in_(ref_ids))
        .order_by(Media.attached_id, Media.position)
    ).scalars():
        out.setdefault(m.attached_id, []).append(view(m))
    return out


def cover(ctx: Ctx, proposal_id: int) -> dict | None:
    """KONU önerisinin kapak görseli (konu silindiyse yok)."""
    m = ctx.db.execute(
        select(Media).where(Media.attached_kind == "oneri", Media.attached_id == proposal_id)
        .order_by(Media.position).limit(1)
    ).scalar_one_or_none()
    return view(m) if m is not None and gone_reason(ctx, m) is None else None


def _topic_of_message(ctx: Ctx, ref_id: int) -> Topic | None:
    msg = ctx.db.get(Message, ref_id)
    return ctx.db.get(Topic, msg.topic_id) if msg is not None else None


def _topic_of_proposal(ctx: Ctx, ref_id: int) -> Topic | None:
    return ctx.db.execute(
        select(Topic).where(Topic.accepted_proposal_id == ref_id)
    ).scalar_one_or_none()


def _topic_of_reply(ctx: Ctx, ref_id: int) -> Topic | None:
    reply = ctx.db.get(PetitionReply, ref_id)
    pet = ctx.db.get(Petition, reply.petition_id) if reply is not None else None
    return ctx.db.get(Topic, pet.topic_id) if pet is not None else None


def _topic_of_report(ctx: Ctx, ref_id: int) -> Topic | None:
    report = ctx.db.get(EventReport, ref_id)
    event = ctx.db.get(CalendarEvent, report.event_id) if report is not None else None
    return ctx.db.get(Topic, event.topic_id) if event is not None else None


# Eklenti türü → görselin bağlı olduğu konuyu bulan fonksiyon. Yeni bir eklenti türü yalnızca
# buraya bir satır ekler; ``gone_reason`` değişmez.
_TOPIC_OF = {"mesaj": _topic_of_message, "oneri": _topic_of_proposal,
             "yanit": _topic_of_reply, "rapor": _topic_of_report}
KINDS = tuple(_TOPIC_OF)


def gone_reason(ctx: Ctx, m: Media) -> str | None:
    """Görselin bağlı olduğu içerik oylamayla silindiyse gerekçe, değilse ``None``."""
    if m.attached_kind == "mesaj":
        msg = ctx.db.get(Message, m.attached_id)
        if msg is not None and msg.deleted_by_proposal_id is not None:
            return (f"Bu görselin bulunduğu mesaj #{msg.deleted_by_proposal_id} numaralı "
                    "oylamayla silindi.")
    find = _TOPIC_OF.get(m.attached_kind or "")
    topic = find(ctx, m.attached_id) if find is not None else None
    if topic is not None and topic.deleted_by_proposal_id is not None:
        return (f"Bu görselin bulunduğu konu #{topic.deleted_by_proposal_id} numaralı "
                "oylamayla silindi.")
    return None


def get_media(ctx: Ctx, media_id: str) -> Media:
    m = ctx.db.get(Media, media_id)
    if m is None:
        raise NotFound("Görsel bulunamadı.")
    if (reason := gone_reason(ctx, m)) is not None:
        raise Gone(reason)
    return m


def content(ctx: Ctx, media_id: str, variant: str) -> tuple[bytes, str]:
    if variant not in VARIANTS:
        raise NotFound("Görselin yalnızca 'baski' ve 'ozgun' sürümleri vardır.")
    m = get_media(ctx, media_id)
    return (m.print_png if variant == "baski" else m.original), VARIANTS[variant]
