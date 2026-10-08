"""Konular ve tartışma alanı: oylamasız mesajlar, sürümler, sansür şeritleri."""

from __future__ import annotations

from sqlalchemy import func, select

from mesveret.context import Ctx
from mesveret.db.models import (
    ClosureText,
    Decision,
    Dissent,
    Message,
    MessageVersion,
    Proposal,
    Topic,
    User,
)
from mesveret.domain.cellar import cellar_thread_refs
from mesveret.domain.diff import word_diff
from mesveret.errors import Conflict, DomainError, Forbidden, NotFound
from mesveret.services import interactions, ledger, media, ontology
from mesveret.services.profile import nickname_map

MAX_MESSAGE = 10_000
ACTIVE_STATUSES = ("DRAFT", "SILENT", "RIVAL_PERIOD", "QUEUED", "VOTING")


class Gone(DomainError):
    status = 410


def check_square_text(text: str, *, max_len: int = MAX_MESSAGE) -> str:
    text = text.strip()
    if not text:
        raise DomainError("Metin boş olamaz.")
    if len(text) > max_len:
        raise DomainError(f"Metin en fazla {max_len} karakter olabilir.")
    if cellar_thread_refs(text):
        raise DomainError("Mahzen başlıklarına Meydan'dan referans verilemez.")
    return text


def get_topic(ctx: Ctx, topic_id: int) -> Topic:
    topic = ctx.db.get(Topic, topic_id)
    if topic is None:
        raise NotFound("Konu bulunamadı.")
    return topic


def get_message(ctx: Ctx, message_id: int) -> Message:
    msg = ctx.db.get(Message, message_id)
    if msg is None:
        raise NotFound("Mesaj bulunamadı.")
    return msg


def current_version(ctx: Ctx, msg: Message) -> MessageVersion:
    return ctx.db.execute(
        select(MessageVersion).where(
            MessageVersion.message_id == msg.id, MessageVersion.version_no == msg.current_version
        )
    ).scalar_one()


def ensure_writable(topic: Topic) -> None:
    if topic.deleted_by_proposal_id is not None:
        raise Conflict(f"Bu konu #{topic.deleted_by_proposal_id} numaralı oylamayla silindi.")
    if topic.status != "OPEN":
        raise Conflict("Konu karara bağlandı; tartışma alanı salt okunur.")


def is_participant(ctx: Ctx, topic: Topic, user_id: str) -> bool:
    if topic.author_id == user_id:
        return True
    return ctx.db.execute(
        select(Message.id).where(Message.topic_id == topic.id, Message.author_id == user_id).limit(1)
    ).first() is not None


def add_version(
    ctx: Ctx, msg: Message, text: str, editor_id: str, via_proposal_id: int | None = None
) -> MessageVersion:
    msg.current_version += 1
    v = MessageVersion(
        message_id=msg.id, version_no=msg.current_version, text=text, editor_id=editor_id,
        via_proposal_id=via_proposal_id, created_at=ctx.now,
    )
    ctx.db.add(v)
    ctx.db.flush()
    ledger.enqueue(ctx, "SURUM_EKLENDI", {
        "mesaj": msg.id, "konu": msg.topic_id, "surum": v.version_no, "metin": text,
        "oneri": via_proposal_id,
    }, ref=v)
    return v


def create_message(
    ctx: Ctx, topic: Topic, author_id: str, text: str, *, reply_to: int | None = None,
    is_opening: bool = False, ledger_type: str = "MESAJ", extra: dict | None = None,
) -> tuple[Message, MessageVersion]:
    msg = Message(
        topic_id=topic.id, author_id=author_id, reply_to_id=reply_to, is_opening=is_opening,
        created_at=ctx.now, current_version=1,
    )
    ctx.db.add(msg)
    ctx.db.flush()
    v = MessageVersion(
        message_id=msg.id, version_no=1, text=text, editor_id=author_id, created_at=ctx.now,
    )
    ctx.db.add(v)
    ctx.db.flush()
    author = ctx.db.get(User, author_id)
    ledger.enqueue(ctx, ledger_type, {
        "mesaj": msg.id, "konu": topic.id, "yazar": author.nickname if author else author_id,
        "metin": text, "yanit": reply_to, **(extra or {}),
    }, ref=v)
    return msg, v


def post_message(
    ctx: Ctx, user: User, topic_id: int, text: str, reply_to: int | None = None,
    *, media_ids: list[str] | None = None,
) -> Message:
    topic = get_topic(ctx, topic_id)
    ensure_writable(topic)
    text = check_square_text(text)
    pictures = media.check_attachable(ctx, user.id, media_ids)
    replied_author = None
    if reply_to is not None:
        target = ctx.db.get(Message, reply_to)
        if target is None or target.topic_id != topic.id:
            raise DomainError("Yanıtlanan mesaj bu konuda değil.")
        if target.deleted_by_proposal_id is not None:
            raise DomainError("Silinmiş bir mesaja yanıt verilemez.")
        replied_author = target.author_id
    firsts = dict(ctx.db.execute(
        select(Message.author_id, func.min(Message.created_at))
        .where(Message.topic_id == topic.id).group_by(Message.author_id)
    ).all())
    msg, _ = create_message(ctx, topic, user.id, text, reply_to=reply_to)
    media.attach(ctx, pictures, "mesaj", msg.id)
    if user.id not in firsts:
        interactions.on_first_participation(ctx, user.id, firsts)
    if replied_author:
        interactions.on_reply(ctx, user.id, replied_author)
    ctx.commit()
    return msg


def edit_own_message(ctx: Ctx, user: User, message_id: int, text: str) -> MessageVersion:
    msg = get_message(ctx, message_id)
    if msg.author_id != user.id:
        raise Forbidden("Başkasının mesajını yalnızca düzenleme önerisiyle değiştirebilirsiniz.")
    if msg.is_opening:
        raise Forbidden("Konu açılış metni oylanarak kabul edildi; yalnızca düzenleme "
                        "önerisiyle değişir.")
    if msg.deleted_by_proposal_id is not None:
        raise Gone(f"Bu mesaj #{msg.deleted_by_proposal_id} numaralı oylamayla silindi.")
    ensure_writable(get_topic(ctx, msg.topic_id))
    text = check_square_text(text)
    if text == current_version(ctx, msg).text:
        raise DomainError("Yeni sürüm öncekiyle aynı.")
    v = add_version(ctx, msg, text, user.id)
    ctx.commit()
    return v


def message_history(ctx: Ctx, message_id: int) -> dict:
    msg = get_message(ctx, message_id)
    if msg.deleted_by_proposal_id is not None:
        raise Gone(f"Bu mesaj #{msg.deleted_by_proposal_id} numaralı oylamayla silindi.")
    topic = get_topic(ctx, msg.topic_id)
    if topic.deleted_by_proposal_id is not None:
        raise Gone(f"Bu konu #{topic.deleted_by_proposal_id} numaralı oylamayla silindi.")
    versions = ctx.db.execute(
        select(MessageVersion).where(MessageVersion.message_id == msg.id)
        .order_by(MessageVersion.version_no)
    ).scalars().all()
    names = nickname_map(ctx, [v.editor_id for v in versions] + [msg.author_id])
    out, prev = [], None
    for v in versions:
        out.append({
            "version": v.version_no, "text": v.text, "editor": names.get(v.editor_id),
            "via_proposal_id": v.via_proposal_id, "created_at": v.created_at,
            "ledger_hash": v.ledger_hash,
            "diff": [list(c) for c in word_diff(prev, v.text)] if prev is not None else None,
        })
        prev = v.text
    return {"message_id": msg.id, "topic_id": msg.topic_id, "author": names.get(msg.author_id),
            "versions": out}


def _message_view(ctx: Ctx, msg: Message, names: dict[str, str],
                  pictures: dict[int, list[dict]] | None = None) -> dict:
    v = current_version(ctx, msg)
    if msg.deleted_by_proposal_id is not None:
        # İçerik gizlenir; mühür (defter hash'i) kalır: silme gizlemedir, kayıttan kaldırmaz.
        return {"id": msg.id, "deleted_by_proposal_id": msg.deleted_by_proposal_id,
                "deletion_basis": deletion_basis(ctx, msg.deleted_by_proposal_id),
                "ledger_hash": v.ledger_hash}
    return {
        "id": msg.id,
        "author": names.get(msg.author_id),
        "text": v.text,
        "created_at": msg.created_at,
        "edited_at": v.created_at if v.version_no > 1 else None,
        "version": v.version_no,
        "reply_to": msg.reply_to_id,
        "ledger_hash": v.ledger_hash,
        "media": (pictures or {}).get(msg.id, []),
    }


def _with_pending(view: dict, pending: dict | None) -> dict:
    """Silinmemiş mesaja aktif silme oylamasını ekler (silinmiş mesaj yalnızca şerittir)."""
    return view if "deleted_by_proposal_id" in view else {**view, "pending_deletion": pending}


def deletion_basis(ctx: Ctx, proposal_id: int) -> dict:
    """Sansür şeridi için: silme hangi içerik kuralına dayandı, ya da yazarın isteği miydi."""
    p = ctx.db.get(Proposal, proposal_id)
    payload = p.payload if p else {}
    return {"rules": list(payload.get("rules", [])), "own": bool(payload.get("own"))}


def topic_summary(ctx: Ctx, topic: Topic) -> dict:
    if topic.deleted_by_proposal_id is not None:
        return {"id": topic.id, "deleted_by_proposal_id": topic.deleted_by_proposal_id,
                "deletion_basis": deletion_basis(ctx, topic.deleted_by_proposal_id),
                "area_id": topic.area_id}
    count = ctx.db.execute(
        select(func.count()).select_from(Message).where(
            Message.topic_id == topic.id, Message.is_opening.is_(False)
        )
    ).scalar_one()
    from mesveret.services import petitions, proposals  # ikisi de bu modülü içe aktarır

    accepted = ctx.db.get(Proposal, topic.accepted_proposal_id) if topic.accepted_proposal_id else None
    return {
        "id": topic.id, "title": topic.title, "area_id": topic.area_id,
        # R2 daraltmasıyla kabul edilen konuda başlık talebi, etki başlığı kararın kapsamını anlatır.
        "effective_title": proposals.effective_title(accepted) if accepted else None,
        "area_name": ontology.area_name(ctx, topic.area_id), "parent_id": topic.parent_id,
        "status": topic.status, "owner_scope": ontology.scope_label(ctx, topic.owner_scope_id),
        "proposed_at": accepted.created_at if accepted else topic.created_at,
        "created_at": topic.created_at, "message_count": count,
        # KONU önerisiyle gelen kapak görseli: kabul edilince konunun da kapağıdır.
        "cover": media.cover(ctx, accepted.id) if accepted else None,
        "addressee": petitions.addressee_view(ctx, topic.addressee),
    }


def list_topics(ctx: Ctx, area_id: str | None = None) -> list[dict]:
    q = select(Topic).order_by(Topic.created_at.desc())
    if area_id:
        q = q.where(Topic.area_id.in_(ctx.graph.area_subtree(area_id)))
    return [topic_summary(ctx, t) for t in ctx.db.execute(q).scalars()]


def _event(ctx: Ctx, topic: Topic) -> dict | None:
    from mesveret.services import calendar  # calendar media'yı, media bu modülü içe aktarır

    return calendar.for_topic(ctx, topic)


def topic_view(ctx: Ctx, topic_id: int, viewer: User | None) -> dict:
    from mesveret.services import decision_hour, petitions, proposals  # bu modülü içe aktarırlar

    topic = get_topic(ctx, topic_id)
    if topic.deleted_by_proposal_id is not None:
        return topic_summary(ctx, topic)
    messages = ctx.db.execute(
        select(Message).where(Message.topic_id == topic.id).order_by(Message.created_at, Message.id)
    ).scalars().all()
    names = nickname_map(ctx, [m.author_id for m in messages] + [topic.author_id])
    pictures = media.attached(ctx, "mesaj", [m.id for m in messages])
    opening = next((m for m in messages if m.is_opening), None)
    decision = ctx.db.execute(
        select(Decision).where(Decision.topic_id == topic.id).order_by(Decision.id.desc())
    ).scalars().first()
    decision_view = None
    if decision is not None:
        dissents = ctx.db.execute(
            select(Dissent).where(Dissent.decision_id == decision.id).order_by(Dissent.id)
        ).scalars().all()
        texts = {ct.id: ct for ct in ctx.db.execute(
            select(ClosureText).where(ClosureText.proposal_id == decision.proposal_id)
        ).scalars()}
        dn = nickname_map(ctx, [d.author_id for d in dissents]
                          + [ct.author_id for ct in texts.values()])

        def text_view(ct: ClosureText | None) -> dict | None:
            return None if ct is None else {"id": ct.id, "text": ct.text,
                                            "author": dn.get(ct.author_id)}

        options = (decision_hour.dissent_options(ctx, decision, viewer) if viewer else [])
        decision_view = {
            "id": decision.id, "proposal_id": decision.proposal_id, "text": decision.text,
            "created_at": decision.created_at, "ledger_hash": decision.ledger_hash,
            "dissents": [
                {"id": d.id, "author": dn.get(d.author_id), "text": d.text,
                 "created_at": d.created_at, "ledger_hash": d.ledger_hash,
                 "based_on": text_view(texts.get(d.closure_text_id))}
                for d in dissents
            ],
            "viewer_can_dissent": viewer is not None
            and decision_hour.dissent_refusal(ctx, decision, viewer) is None,
            "viewer_dissent_options": [text_view(ct) for ct in options],
        }
    reopen_after = (topic.closed_at + ctx.reg.duration("yeniden_acma")
                    if topic.status == "CLOSED" and topic.closed_at else None)
    active = ctx.db.execute(
        select(Proposal).where(Proposal.status.in_(ACTIVE_STATUSES)).order_by(Proposal.id)
    ).scalars().all()
    accepted = ctx.db.get(Proposal, topic.accepted_proposal_id) if topic.accepted_proposal_id else None
    narrowings = [
        {"scope": ontology.scope_label(ctx, n["scope_id"]), "share": n["share"],
         "total": n.get("total"), "message": n["message"]}
        for n in (accepted.narrowings if accepted else None) or []
    ]
    related = [
        {"id": p.id, "type": p.type, "status": p.status, "title": p.title,
         "effective_title": proposals.effective_title(p),
         "maturity": proposals.maturity(ctx, p) if p.status in ("QUEUED", "RIVAL_PERIOD") else None}
        for p in active
        if p.payload.get("topic_id") == topic.id or p.payload.get("parent_topic_id") == topic.id
    ]
    # Aktif silme oylamaları: mesajın ya da konunun üstünde küçük bir işaret olarak gösterilir.
    pending: dict[int | None, dict] = {}
    for p in active:
        if p.type == "SILME" and p.status != "DRAFT" and p.payload.get("topic_id") == topic.id:
            pending.setdefault(p.payload.get("message_id"),
                               {"proposal_id": p.id, "decides_at": proposals.decides_at(ctx, p)})
    subtopics = ctx.db.execute(
        select(Topic).where(Topic.parent_id == topic.id).order_by(Topic.id)
    ).scalars().all()
    body = topic_summary(ctx, topic)
    body.update({
        "author": names.get(topic.author_id),
        "opening": _message_view(ctx, opening, names, pictures) if opening else None,
        "messages": [_with_pending(_message_view(ctx, m, names, pictures), pending.get(m.id))
                     for m in messages if not m.is_opening],
        "pending_deletion": pending.get(None),
        "decision": decision_view,
        "petitions": petitions.for_topic(ctx, topic.id),
        "event": _event(ctx, topic),
        "narrowings": narrowings,
        "subtopics": [topic_summary(ctx, t) for t in subtopics],
        "proposals": related,
        "parent": topic_summary(ctx, get_topic(ctx, topic.parent_id)) if topic.parent_id else None,
        "reopen_after": reopen_after,
        "can_reopen": reopen_after is not None and ctx.now >= reopen_after,
        "viewer": {
            "can_post": viewer is not None and topic.status == "OPEN",
            "is_participant": viewer is not None and is_participant(ctx, topic, viewer.id),
        },
    })
    return body
