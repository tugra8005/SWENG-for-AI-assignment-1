"""Öneri motoru: açılış denetimi, şeritler, itiraz, rakip metinler ve kabul etkileri.

Hızlı şerit (sessiz onay): KONU, ALT_KONU, DUZENLEME.
Yavaş şerit (Karar Saati): SILME, YONETMELIK, KAPANIS ve itiraz eşiğine ulaşan hızlı şerit
önerileri.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC
from typing import Any

from sqlalchemy import func, select

from mesveret.context import Ctx
from mesveret.db.models import (
    ClosureText,
    Decision,
    Message,
    Objection,
    Proposal,
    SessionItem,
    Topic,
    User,
)
from mesveret.domain.diff import word_diff
from mesveret.domain.maturation import LABELS as MATURITY_LABELS
from mesveret.domain.maturation import (
    first_session_at,
    matures_at,
    maturity_class,
    maturity_duration,
)
from mesveret.domain.ontology import ResourceInfo, ResourceKind
from mesveret.domain.oracle import label_check, oracle_comment
from mesveret.domain.regulation import DEFAULT_ARTICLES, RegulationError, validate_value
from mesveret.domain.rules import (
    ProposalDraft,
    RuleContext,
    RuleReport,
    check_proposal,
    format_date,
)
from mesveret.domain.scopes import GENERAL_SCOPE_ID
from mesveret.domain.text import normalize
from mesveret.domain.types import ProposalStatus, ProposalType, initial_lane
from mesveret.errors import Conflict, DomainError, Forbidden, NotFound
from mesveret.services import ledger, ontology, regulation, topics
from mesveret.services.profile import nickname_map

MAX_TITLE = 200
MAX_BODY = 20_000
OPEN_STATUSES = ("SILENT", "RIVAL_PERIOD", "QUEUED", "VOTING")


@dataclass
class ProposalInput:
    type: str
    title: str = ""
    body: str = ""
    area_id: str | None = None
    scope_id: str | None = None
    resource_ids: list[str] = field(default_factory=list)
    parent_topic_id: int | None = None
    target_message_id: int | None = None
    target_topic_id: int | None = None
    new_text: str | None = None
    article_key: str | None = None
    new_value: dict[str, Any] | None = None
    reopens_topic_id: int | None = None


@dataclass
class Prepared:
    """Türe özgü hazırlığın sonucu: Proposal alanları."""

    type: ProposalType
    title: str
    body: str
    area_id: str | None
    scope_id: str
    resource_ids: list[str]
    target_key: str
    payload: dict[str, Any]
    parent_resource_id: str | None = None


# --- yardımcılar --------------------------------------------------------------------------------


def get_proposal(ctx: Ctx, proposal_id: int) -> Proposal:
    p = ctx.db.get(Proposal, proposal_id)
    if p is None:
        raise NotFound("Öneri bulunamadı.")
    return p


def _title(text: str, *, required: bool = True) -> str:
    text = text.strip()
    if required and len(text) < 3:
        raise DomainError("Başlık en az 3 karakter olmalı.")
    if len(text) > MAX_TITLE:
        raise DomainError(f"Başlık en fazla {MAX_TITLE} karakter olabilir.")
    return text


def _body(text: str, *, required: bool = True, label: str = "Metin") -> str:
    text = text.strip()
    if required and not text:
        raise DomainError(f"{label} boş olamaz.")
    if len(text) > MAX_BODY:
        raise DomainError(f"{label} en fazla {MAX_BODY} karakter olabilir.")
    return topics.check_square_text(text, max_len=MAX_BODY) if text else text


def _live_topic(ctx: Ctx, topic_id: int | None, *, must_be_open: bool = True) -> Topic:
    if topic_id is None:
        raise DomainError("Hedef konu belirtilmeli.")
    topic = topics.get_topic(ctx, topic_id)
    if topic.deleted_by_proposal_id is not None:
        raise Conflict(f"Bu konu #{topic.deleted_by_proposal_id} numaralı oylamayla silindi.")
    if must_be_open and topic.status != "OPEN":
        raise Conflict("Konu karara bağlandı; önce yeniden açılması gerekir.")
    return topic


def _resource_labels(ctx: Ctx, ids: list[str]) -> list[str]:
    out = []
    for rid in ids:
        if rid not in out:
            out.append(rid)
    return out


# --- türe özgü hazırlık ---------------------------------------------------------------------------


def _prepare(ctx: Ctx, user: User, inp: ProposalInput) -> Prepared:
    try:
        t = ProposalType(inp.type)
    except ValueError as exc:
        raise DomainError("Bilinmeyen öneri türü.") from exc

    if t is ProposalType.KONU and inp.reopens_topic_id is not None:
        topic = topics.get_topic(ctx, inp.reopens_topic_id)
        if topic.status != "CLOSED" or topic.closed_at is None:
            raise Conflict("Yalnızca karara bağlanmış bir konu yeniden açılabilir.")
        reopen_at = topic.closed_at + ctx.reg.duration("yeniden_acma")
        if ctx.now < reopen_at:
            raise DomainError(
                f"Bu konu {format_date(reopen_at)} tarihinden önce yeniden açılamaz "
                "(yeniden_acma süresi)."
            )
        return Prepared(
            t, _title(inp.title or f"Yeniden açma: {topic.title}"),
            _body(inp.body, label="Gerekçe"), topic.area_id,
            inp.scope_id or topic.owner_scope_id, [topic.resource_id],
            f"YENIDEN_ACMA:{topic.id}", {"topic_id": topic.id, "reopen": True},
        )

    if t in (ProposalType.KONU, ProposalType.ALT_KONU):
        title = _title(inp.title)
        if not inp.scope_id:
            raise DomainError("Seçmen kapsamı seçilmeli.")
        payload: dict[str, Any] = {}
        parent_rid = None
        if t is ProposalType.ALT_KONU:
            parent = _live_topic(ctx, inp.parent_topic_id)
            payload["parent_topic_id"] = parent.id
            parent_rid = parent.resource_id
            key = f"ALT_KONU:{parent.id}:{normalize(title)}"
        else:
            key = f"KONU:{inp.area_id}:{normalize(title)}"
        return Prepared(
            t, title, _body(inp.body, label="Açılış metni"), inp.area_id, inp.scope_id,
            _resource_labels(ctx, inp.resource_ids), key, payload, parent_rid,
        )

    if t is ProposalType.DUZENLEME:
        msg = topics.get_message(ctx, inp.target_message_id) if inp.target_message_id else None
        if msg is None:
            raise DomainError("Düzenlenecek mesaj belirtilmeli.")
        if msg.deleted_by_proposal_id is not None:
            raise Conflict(f"Bu mesaj #{msg.deleted_by_proposal_id} numaralı oylamayla silindi.")
        if msg.author_id == user.id and not msg.is_opening:
            raise DomainError("Kendi mesajınızı doğrudan düzenleyebilirsiniz; öneri gerekmez.")
        topic = _live_topic(ctx, msg.topic_id)
        new_text = _body(inp.new_text or "", label="Yeni metin")
        current = topics.current_version(ctx, msg)
        if new_text == current.text:
            raise DomainError("Önerilen metin mevcut metinle aynı.")
        return Prepared(
            t, _title(inp.title or f"Düzenleme: {topic.title}"), _body(inp.body, required=False),
            topic.area_id, inp.scope_id or topic.owner_scope_id, [topic.resource_id],
            f"ICERIK:mesaj:{msg.id}",
            {"topic_id": topic.id, "message_id": msg.id, "base_version": current.version_no,
             "new_text": new_text, "opening": msg.is_opening},
        )

    if t is ProposalType.SILME:
        if (inp.target_message_id is None) == (inp.target_topic_id is None):
            raise DomainError("Silinecek mesajı ya da konuyu (yalnızca birini) belirtin.")
        if inp.target_message_id is not None:
            msg = topics.get_message(ctx, inp.target_message_id)
            if msg.deleted_by_proposal_id is not None:
                raise Conflict("Bu mesaj zaten silindi.")
            topic = _live_topic(ctx, msg.topic_id, must_be_open=False)
            target = {"message_id": msg.id}
            key = f"ICERIK:mesaj:{msg.id}"
            default_title = f"Silme: {topic.title} konusundaki #{msg.id} numaralı mesaj"
        else:
            topic = _live_topic(ctx, inp.target_topic_id, must_be_open=False)
            target = {}
            key = f"ICERIK:konu:{topic.id}"
            default_title = f"Silme: {topic.title}"
        return Prepared(
            t, _title(inp.title or default_title), _body(inp.body, required=False),
            topic.area_id, inp.scope_id or topic.owner_scope_id, [topic.resource_id], key,
            {"topic_id": topic.id, **target},
        )

    if t is ProposalType.YONETMELIK:
        key = inp.article_key or ""
        if key not in DEFAULT_ARTICLES:
            raise DomainError("Böyle bir yönetmelik maddesi yok.")
        try:
            new_value = validate_value(key, inp.new_value or {})
        except RegulationError as exc:
            raise DomainError(str(exc)) from exc
        old_value = ctx.graph.articles().get(key)
        if new_value == old_value:
            raise DomainError("Önerilen değer mevcut değerle aynı.")
        return Prepared(
            t, _title(inp.title or f"Yönetmelik: {key}"), _body(inp.body, required=False), None,
            inp.scope_id or GENERAL_SCOPE_ID, [regulation.article_resource_id(key)],
            f"MADDE:{key}", {"article_key": key, "old_value": old_value, "new_value": new_value},
        )

    # KAPANIS
    topic = _live_topic(ctx, inp.target_topic_id)
    if not topics.is_participant(ctx, topic, user.id):
        raise Forbidden("Kapanış önerisini yalnızca konunun katılımcıları açabilir.")
    active = ctx.db.execute(
        select(Proposal.id).where(
            Proposal.type == "KAPANIS", Proposal.status.in_(OPEN_STATUSES),
            Proposal.target_key == f"KAPANIS:{topic.id}",
        )
    ).first()
    if active:
        raise Conflict(
            f"Bu konuda açık bir kapanış önerisi var (#{active[0]}); rakip metin olarak ekleyin."
        )
    return Prepared(
        t, _title(inp.title or f"Kapanış: {topic.title}"), _body(inp.body, label="Karar metni"),
        topic.area_id, inp.scope_id or topic.owner_scope_id, [topic.resource_id],
        f"KAPANIS:{topic.id}", {"topic_id": topic.id},
    )


# --- denetim ------------------------------------------------------------------------------------


def last_rejection(ctx: Ctx, target_key: str, exclude_id: int | None = None):
    q = select(func.max(Proposal.decided_at)).where(
        Proposal.target_key == target_key, Proposal.status == "REJECTED"
    )
    if exclude_id is not None:
        q = q.where(Proposal.id != exclude_id)
    return ctx.db.execute(q).scalar()


def draft_of(p: Proposal | Prepared, proposer_id: str) -> ProposalDraft:
    parent = p.parent_resource_id if isinstance(p, Prepared) else (
        f"konu:{p.payload['parent_topic_id']}" if p.payload.get("parent_topic_id") else None
    )
    return ProposalDraft(
        type=ProposalType(p.type), proposer_id=proposer_id, scope_id=p.scope_id,
        area_id=p.area_id, resource_ids=tuple(p.resource_ids), parent_topic_id=parent,
        target_key=p.target_key, title=p.title, body=p.body,
    )


def run_rules(
    ctx: Ctx, draft: ProposalDraft, exclude_id: int | None = None
) -> RuleReport:
    rc = RuleContext(
        onto=ctx.graph, reg=ctx.reg, now=ctx.now,
        proposer_right=ontology.vote_right(ctx, draft.proposer_id, draft.scope_id),
        last_rejection=last_rejection(ctx, draft.target_key or "", exclude_id),
    )
    return check_proposal(draft, rc)


def _raise_violations(report: RuleReport) -> None:
    raise DomainError(
        "Öneri denetimden geçemedi.",
        violations=[{"rule": v.rule, "message": v.message} for v in report.violations],
    )


def oracle_text(p: Proposal) -> str:
    return f"{p.title}\n{p.body}\n{p.payload.get('new_text', '')}"


# --- açılış -------------------------------------------------------------------------------------


def _start_lane(ctx: Ctx, p: Proposal) -> None:
    t = ProposalType(p.type)
    p.lane = str(initial_lane(t))
    if t is ProposalType.KAPANIS:
        p.status = ProposalStatus.RIVAL_PERIOD
        p.deadline_at = ctx.now + ctx.reg.duration("kapanis_rakip_suresi")
    elif p.lane == "FAST":
        p.status = ProposalStatus.SILENT
        p.deadline_at = ctx.now + ctx.reg.duration("sessiz_onay_suresi")
    else:
        p.status = ProposalStatus.QUEUED
        p.queued_at = ctx.now


def _finish_opening(ctx: Ctx, p: Proposal, report: RuleReport) -> None:
    p.narrowings = [
        {"resource_id": n.resource_id, "scope_id": n.scope_id, "share": n.share,
         "total": n.total, "message": n.message, "effect_title": n.effect_title}
        for n in report.narrowings
    ]
    findings = label_check(oracle_text(p), p.area_id, p.scope_id, p.resource_ids, ctx.graph)
    p.oracle_comment = oracle_comment(report, findings, ctx.graph)
    p.oracle_findings = [{"kind": f.kind, "suggestion": f.suggestion, "message": f.message}
                         for f in findings]
    _start_lane(ctx, p)
    ctx.db.flush()
    if p.type == "KAPANIS":
        ctx.db.add(ClosureText(proposal_id=p.id, author_id=p.proposer_id, text=p.body,
                               created_at=ctx.now))
    ctx.graph.record_proposal(p.id, p.type, p.scope_id, list(p.resource_ids), p.status)
    proposer = ctx.db.get(User, p.proposer_id)
    ledger.enqueue(ctx, "ONERI_ACILDI", {
        "oneri": p.id, "tur": p.type, "baslik": p.title, "metin": p.body,
        "oneren": proposer.nickname if proposer else p.proposer_id,
        "secmen": p.scope_id, "alan": p.area_id, "etkiler": list(p.resource_ids),
        "daraltma": [n["message"] for n in p.narrowings], "ayrinti": p.payload,
    }, ref=p)


def open_proposal(ctx: Ctx, user: User, inp: ProposalInput) -> Proposal:
    prep = _prepare(ctx, user, inp)
    report = run_rules(ctx, draft_of(prep, user.id))
    if not report.ok:
        _raise_violations(report)
    p = Proposal(
        type=str(prep.type), status="SILENT", lane="FAST", proposer_id=user.id,
        scope_id=prep.scope_id, area_id=prep.area_id, resource_ids=prep.resource_ids,
        title=prep.title, body=prep.body, payload=prep.payload, target_key=prep.target_key,
        created_at=ctx.now,
    )
    ctx.db.add(p)
    _finish_opening(ctx, p, report)
    ctx.commit()
    return p


def create_draft(ctx: Ctx, owner_id: str, title: str, body: str, payload: dict) -> Proposal:
    """Mahzen ifşasından TASLAK bir KONU önerisi (etiketleri sahibi seçip gönderir)."""
    p = Proposal(
        type="KONU", status="DRAFT", lane="FAST", proposer_id=owner_id, scope_id=GENERAL_SCOPE_ID,
        area_id=None, resource_ids=[], title=title[:MAX_TITLE], body=body[:MAX_BODY],
        payload=payload, target_key="TASLAK", created_at=ctx.now,
    )
    ctx.db.add(p)
    ctx.db.flush()
    return p


def submit_draft(ctx: Ctx, user: User, proposal_id: int, inp: ProposalInput) -> Proposal:
    p = get_proposal(ctx, proposal_id)
    if p.status != "DRAFT":
        raise Conflict("Bu öneri taslak değil.")
    if p.proposer_id != user.id:
        raise Forbidden("Taslağı yalnızca sahibi gönderebilir.")
    prep = _prepare(ctx, user, ProposalInput(
        type="KONU", title=inp.title or p.title, body=inp.body or p.body, area_id=inp.area_id,
        scope_id=inp.scope_id, resource_ids=inp.resource_ids,
    ))
    report = run_rules(ctx, draft_of(prep, user.id), exclude_id=p.id)
    if not report.ok:
        _raise_violations(report)
    p.title, p.body, p.area_id, p.scope_id = prep.title, prep.body, prep.area_id, prep.scope_id
    p.resource_ids, p.target_key = prep.resource_ids, prep.target_key
    p.payload = {**p.payload, **prep.payload}
    p.created_at = ctx.now
    _finish_opening(ctx, p, report)
    ctx.commit()
    return p


# --- itiraz ve rakip metin ---------------------------------------------------------------------------


def objection_threshold(ctx: Ctx, p: Proposal) -> int:
    return ctx.reg.objection_threshold(ontology.active_member_count(ctx, p.scope_id))


def objection_count(ctx: Ctx, p: Proposal) -> int:
    return ctx.db.execute(
        select(func.count()).select_from(Objection).where(Objection.proposal_id == p.id)
    ).scalar_one()


def object_to(ctx: Ctx, user: User, proposal_id: int) -> dict:
    p = get_proposal(ctx, proposal_id)
    if p.status != "SILENT":
        raise Conflict("Bu öneri itiraza açık değil.")
    right = ontology.vote_right(ctx, user.id, p.scope_id)
    if not right.has_right:
        raise Forbidden(f"İtiraz için seçmen kapsamında oy hakkı gerekir. {right.reason}")
    exists = ctx.db.execute(
        select(Objection.id).where(Objection.proposal_id == p.id, Objection.user_id == user.id)
    ).first()
    if exists:
        raise Conflict("Bu öneriye zaten itiraz ettiniz.")
    ctx.db.add(Objection(proposal_id=p.id, user_id=user.id, created_at=ctx.now))
    ctx.db.flush()
    count, threshold = objection_count(ctx, p), objection_threshold(ctx, p)
    moved = count >= threshold
    if moved:
        p.status, p.lane, p.queued_at = "QUEUED", "SLOW", ctx.now
        ctx.graph.set_proposal_status(p.id, p.status)
        ledger.enqueue(ctx, "ONERI_YAVAS_SERIDE", {
            "oneri": p.id, "itiraz": count, "esik": threshold,
        })
    ctx.commit()
    return {"count": count, "threshold": threshold, "moved": moved}


def closure_texts(ctx: Ctx, p: Proposal) -> list[ClosureText]:
    return list(ctx.db.execute(
        select(ClosureText).where(ClosureText.proposal_id == p.id).order_by(ClosureText.id)
    ).scalars())


def add_rival(ctx: Ctx, user: User, proposal_id: int, text: str) -> ClosureText:
    p = get_proposal(ctx, proposal_id)
    if p.type != "KAPANIS":
        raise DomainError("Rakip metin yalnızca kapanış önerisine eklenir.")
    if p.status != "RIVAL_PERIOD" or (p.deadline_at and ctx.now >= p.deadline_at):
        raise Conflict("Rakip metin süresi doldu.")
    topic = topics.get_topic(ctx, p.payload["topic_id"])
    if not topics.is_participant(ctx, topic, user.id):
        raise Forbidden("Rakip metni yalnızca konunun katılımcıları ekleyebilir.")
    if any(ct.author_id == user.id for ct in closure_texts(ctx, p)):
        raise Conflict("Bu kapanışa zaten bir metin eklediniz.")
    ct = ClosureText(proposal_id=p.id, author_id=user.id,
                     text=_body(text, label="Karar metni"), created_at=ctx.now)
    ctx.db.add(ct)
    ctx.db.flush()
    ledger.enqueue(ctx, "KAPANIS_METNI", {
        "oneri": p.id, "metin_no": ct.id, "yazar": user.nickname, "metin": ct.text,
    }, ref=ct)
    ctx.commit()
    return ct


# --- zamanlanmış geçişler ------------------------------------------------------------------------


def end_silent_period(ctx: Ctx, p: Proposal) -> None:
    """Sessiz onay süresi doldu ve itiraz eşiği aşılmadı: kabul."""
    if p.status == "SILENT":
        accept(ctx, p)


def end_rival_period(ctx: Ctx, p: Proposal) -> None:
    if p.status == "RIVAL_PERIOD":
        p.status, p.queued_at = "QUEUED", ctx.now
        ctx.graph.set_proposal_status(p.id, p.status)


# --- sonuç ve etkiler ---------------------------------------------------------------------------


def _new_topic(ctx: Ctx, p: Proposal, parent_id: int | None) -> Topic:
    topic = Topic(
        title=p.title, area_id=p.area_id, parent_id=parent_id, owner_scope_id=p.scope_id,
        author_id=p.proposer_id, status="OPEN", created_at=ctx.now, accepted_proposal_id=p.id,
    )
    ctx.db.add(topic)
    ctx.db.flush()
    ctx.graph.upsert_resource(
        ResourceInfo(topic.resource_id, ResourceKind.KONU, topic.title, topic.owner_scope_id),
        topic_area_id=topic.area_id,
        parent_topic_id=f"konu:{parent_id}" if parent_id else None,
    )
    topics.create_message(
        ctx, topic, p.proposer_id, p.body, is_opening=True, ledger_type="KONU_KABUL",
        extra={"oneri": p.id, "baslik": topic.title, "alan": topic.area_id,
               "sahip_kapsam": topic.owner_scope_id,
               "daraltma": [n["message"] for n in p.narrowings]},
    )
    return topic


def _apply(ctx: Ctx, p: Proposal, winner_text_id: int | None) -> None:
    t = ProposalType(p.type)
    if t is ProposalType.KONU and p.payload.get("reopen"):
        topic = topics.get_topic(ctx, p.payload["topic_id"])
        topic.status, topic.reopened_at = "OPEN", ctx.now
        ledger.enqueue(ctx, "KONU_YENIDEN_ACILDI", {"konu": topic.id, "oneri": p.id})
    elif t in (ProposalType.KONU, ProposalType.ALT_KONU):
        _new_topic(ctx, p, p.payload.get("parent_topic_id"))
    elif t is ProposalType.DUZENLEME:
        msg = topics.get_message(ctx, p.payload["message_id"])
        topics.add_version(ctx, msg, p.payload["new_text"], p.proposer_id, via_proposal_id=p.id)
    elif t is ProposalType.SILME:
        if "message_id" in p.payload:
            target = topics.get_message(ctx, p.payload["message_id"])
        else:
            target = topics.get_topic(ctx, p.payload["topic_id"])
        target.deleted_by_proposal_id = p.id
        ledger.enqueue(ctx, "ICERIK_SILINDI", {
            "oneri": p.id, "konu": p.payload["topic_id"], "mesaj": p.payload.get("message_id"),
            "not": "İçerik sitede gizlendi; defterdeki kayıtları silinmez.",
        })
    elif t is ProposalType.YONETMELIK:
        regulation.apply_change(ctx, p.payload["article_key"], p.payload["new_value"], p.id)
        ledger.enqueue(ctx, "YONETMELIK_DEGISTI", {
            "oneri": p.id, "madde": p.payload["article_key"],
            "eski": p.payload["old_value"], "yeni": p.payload["new_value"],
        })
    elif t is ProposalType.KAPANIS:
        texts = {ct.id: ct for ct in closure_texts(ctx, p)}
        if winner_text_id not in texts:
            raise DomainError("Kazanan karar metni bulunamadı.")
        topic = topics.get_topic(ctx, p.payload["topic_id"])
        d = Decision(topic_id=topic.id, proposal_id=p.id, closure_text_id=winner_text_id,
                     text=texts[winner_text_id].text, created_at=ctx.now)
        ctx.db.add(d)
        ctx.db.flush()
        topic.status, topic.closed_at = "CLOSED", ctx.now
        ctx.graph.record_decision(d.id, topic.resource_id)
        ledger.enqueue(ctx, "KARAR", {
            "karar": d.id, "konu": topic.id, "oneri": p.id, "metin": d.text,
        }, ref=d)


def accept(ctx: Ctx, p: Proposal, *, winner_text_id: int | None = None, note: str | None = None) -> None:
    _apply(ctx, p, winner_text_id)
    p.status, p.decided_at, p.outcome_note = "ACCEPTED", ctx.now, note
    ctx.graph.set_proposal_status(p.id, p.status)
    ledger.enqueue(ctx, "ONERI_SONUCU", {"oneri": p.id, "sonuc": "KABUL", "not": note})
    ctx.db.flush()


def reject(ctx: Ctx, p: Proposal, note: str) -> None:
    p.status, p.decided_at, p.outcome_note = "REJECTED", ctx.now, note
    ctx.graph.set_proposal_status(p.id, p.status)
    ledger.enqueue(ctx, "ONERI_SONUCU", {"oneri": p.id, "sonuc": "RET", "not": note})
    ctx.db.flush()


# --- olgunlaşma ---------------------------------------------------------------------------------


def maturity(ctx: Ctx, p: Proposal) -> dict[str, Any]:
    """Önerinin Karar Saati'nde oylanabilmesi için olgunlaşma durumu (bkz. domain.maturation)."""
    klass = maturity_class(ProposalType(p.type), ctx.graph.scope(p.scope_id), ctx.graph)
    at = matures_at(ProposalType(p.type), created_at=p.created_at, queued_at=p.queued_at,
                    klass=klass, reg=ctx.reg).astimezone(UTC)
    return {
        "klass": klass.value,
        "label": MATURITY_LABELS[klass],
        "hours": int(maturity_duration(klass, ctx.reg).total_seconds() // 3600),
        "matures_at": at,
        "mature": at <= ctx.now,
        "first_session_at": first_session_at(at, ctx.now, ctx.reg.decision_hour()).astimezone(UTC),
    }


def is_mature(ctx: Ctx, p: Proposal) -> bool:
    return maturity(ctx, p)["mature"]


# --- görünümler ---------------------------------------------------------------------------------


def _resource_view(ctx: Ctx, rid: str, narrowings: list[dict]) -> dict:
    r = ctx.graph.resource(rid)
    view: dict[str, Any] = {"id": rid, "name": r.name if r else rid,
                            "kind": str(r.kind) if r else None, "narrowed": None}
    n = next((n for n in narrowings if n["resource_id"] == rid), None)
    if n is not None:
        view["narrowed"] = {"scope": ontology.scope_label(ctx, n["scope_id"]),
                            "share": n["share"], "total": n.get("total")}
    return view


def effective_title(p: Proposal) -> str | None:
    """R2 daraltması varsa talebin yerine etkiyi anlatan başlık (kaynak adı + kapsamın payı)."""
    titles = [n["effect_title"] for n in p.narrowings or [] if n.get("effect_title")]
    return " ve ".join(titles) if titles else None


def summary(ctx: Ctx, p: Proposal, names: dict[str, str]) -> dict:
    return {
        "id": p.id, "type": p.type, "status": p.status, "lane": p.lane, "title": p.title,
        "effective_title": effective_title(p),
        "maturity": maturity(ctx, p) if p.status in ("QUEUED", "RIVAL_PERIOD") else None,
        "proposer": names.get(p.proposer_id), "scope": ontology.scope_label(ctx, p.scope_id),
        "scope_id": p.scope_id, "area_id": p.area_id, "area_name": ontology.area_name(ctx, p.area_id)
        if p.area_id else None, "created_at": p.created_at, "deadline_at": p.deadline_at,
        "decided_at": p.decided_at,
    }


def list_proposals(ctx: Ctx, state: str | None, viewer: User | None) -> list[dict]:
    q = select(Proposal).order_by(Proposal.id.desc())
    if state == "open":
        q = q.where(Proposal.status.in_(OPEN_STATUSES))
    elif state == "decided":
        q = q.where(Proposal.status.in_(("ACCEPTED", "REJECTED")))
    elif state == "draft":
        if viewer is None:
            return []
        q = q.where(Proposal.status == "DRAFT", Proposal.proposer_id == viewer.id)
    rows = [p for p in ctx.db.execute(q).scalars()
            if p.status != "DRAFT" or (viewer and p.proposer_id == viewer.id)]
    names = nickname_map(ctx, [p.proposer_id for p in rows])
    return [summary(ctx, p, names) for p in rows]


def proposal_view(ctx: Ctx, p: Proposal, viewer: User | None) -> dict:
    names = nickname_map(ctx, [p.proposer_id])
    body = summary(ctx, p, names)
    body.update({
        "body": p.body, "payload": p.payload, "narrowings": p.narrowings,
        "resources": [_resource_view(ctx, rid, p.narrowings or []) for rid in p.resource_ids],
        "oracle_comment": p.oracle_comment, "oracle_findings": p.oracle_findings,
        "queued_at": p.queued_at, "session_id": p.session_id, "outcome_note": p.outcome_note,
        "ledger_hash": p.ledger_hash,
    })
    if p.status == "SILENT":
        body["objections"] = {"count": objection_count(ctx, p), "threshold": objection_threshold(ctx, p)}
    if p.type == "DUZENLEME":
        msg = ctx.db.get(Message, p.payload["message_id"])
        base = topics.current_version(ctx, msg).text if msg else ""
        body["current_text"] = base
        body["diff"] = [list(c) for c in word_diff(base, p.payload["new_text"])]
    if p.type == "SILME" and p.status not in ("ACCEPTED",):
        body["target_preview"] = _target_preview(ctx, p)
    if p.type == "KAPANIS":
        texts = closure_texts(ctx, p)
        tn = nickname_map(ctx, [ct.author_id for ct in texts])
        body["texts"] = [{"id": ct.id, "author": tn.get(ct.author_id), "text": ct.text,
                          "created_at": ct.created_at, "ledger_hash": ct.ledger_hash}
                         for ct in texts]
        d = ctx.db.execute(select(Decision).where(Decision.proposal_id == p.id)).scalar_one_or_none()
        body["decision_id"] = d.id if d else None
    if p.session_id is not None:
        item = ctx.db.execute(select(SessionItem).where(
            SessionItem.session_id == p.session_id, SessionItem.proposal_id == p.id
        )).scalar_one_or_none()
        body["result"] = item.result if item else None
    viewer_info: dict[str, Any] = {}
    if viewer is not None:
        viewer_info["is_proposer"] = viewer.id == p.proposer_id
        viewer_info["has_objected"] = ctx.db.execute(select(Objection.id).where(
            Objection.proposal_id == p.id, Objection.user_id == viewer.id
        )).first() is not None
        right = ontology.vote_right(ctx, viewer.id, p.scope_id)
        viewer_info["has_vote_right"] = right.has_right
        viewer_info["vote_right_reason"] = right.reason
        if p.type == "KAPANIS" and p.status == "RIVAL_PERIOD":
            topic = ctx.db.get(Topic, p.payload["topic_id"])
            viewer_info["can_add_rival"] = bool(topic) and topics.is_participant(
                ctx, topic, viewer.id
            ) and viewer.id not in {ct.author_id for ct in closure_texts(ctx, p)}
    body["viewer"] = viewer_info
    return body


def _target_preview(ctx: Ctx, p: Proposal) -> dict | None:
    if "message_id" in p.payload:
        msg = ctx.db.get(Message, p.payload["message_id"])
        if msg is None or msg.deleted_by_proposal_id is not None:
            return None
        return {"kind": "mesaj", "id": msg.id, "text": topics.current_version(ctx, msg).text}
    topic = ctx.db.get(Topic, p.payload["topic_id"])
    if topic is None or topic.deleted_by_proposal_id is not None:
        return None
    return {"kind": "konu", "id": topic.id, "title": topic.title}
