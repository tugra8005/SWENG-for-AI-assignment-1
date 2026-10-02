"""Öneri motoru: açılış denetimi, şeritler, itiraz, rakip metinler ve kabul etkileri.

Hızlı şerit (sessiz onay): KONU, ALT_KONU, DUZENLEME.
Yavaş şerit (Karar Saati): SILME, YONETMELIK, KAPANIS ve itiraz eşiğine ulaşan hızlı şerit
önerileri.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from mesveret.context import Ctx
from mesveret.db.models import (
    ClosureText,
    Decision,
    Media,
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
from mesveret.domain.oracle import ContentCheck, content_check, label_check, oracle_comment
from mesveret.domain.regulation import (
    CONTENT_RULE_KIND,
    RegulationError,
    article_kind,
    article_title,
    validate_value,
)
from mesveret.domain.rules import (
    ProposalDraft,
    RuleContext,
    RuleReport,
    check_proposal,
    format_date,
)
from mesveret.domain.scopes import GENERAL_SCOPE_ID
from mesveret.domain.shares import ShareImpact, impact_lines, pct, share_impact
from mesveret.domain.text import normalize
from mesveret.domain.types import ProposalStatus, ProposalType, initial_lane
from mesveret.errors import Conflict, DomainError, Forbidden, NotFound
from mesveret.services import (
    ledger,
    media,
    notifications,
    ontology,
    petitions,
    regulation,
    topics,
)
from mesveret.services.profile import nickname_map

MAX_TITLE = 200
INTERNAL = "mesveret"  # yönetmelik, silme, düzenleme: Meşveret'in iç düzeni
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
    # SILME: dayanılan içerik kuralları (IK-1…) ve kuralı ihlal eden kısım (metinden alıntı).
    content_rules: list[str] = field(default_factory=list)
    excerpt: str = ""
    # YONETMELIK: "degistir" (değer), "ekle" (yeni içerik kuralı), "kaldir" (içerik kuralı)
    article_action: str = "degistir"
    # Bölünebilir kaynak: {kaynak: {kapsam: yeni_pay}} (R2'nin ters yönü)
    share_effect: dict[str, dict[str, Any]] | None = None
    # KONU/ALT_KONU: önceden yüklenmiş kapak görseli (kabul edilince konunun kapağı olur)
    cover_media_id: str | None = None
    # KONU/ALT_KONU: önerinin iletileceği yer (R9); ALT_KONU verilmezse üst konununkini alır.
    addressee: str | None = None


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
            f"YENIDEN_ACMA:{topic.id}",
            {"topic_id": topic.id, "reopen": True, "addressee": topic.addressee},
        )

    if t in (ProposalType.KONU, ProposalType.ALT_KONU):
        title = _title(inp.title)
        if not inp.scope_id:
            raise DomainError("Seçmen kapsamı seçilmeli.")
        payload: dict[str, Any] = {}
        if inp.share_effect is not None:
            if not isinstance(inp.share_effect, dict) or not all(
                isinstance(v, dict) for v in inp.share_effect.values()
            ):
                raise DomainError("Pay etkisi {kaynak: {kapsam: yeni_pay}} biçiminde olmalı.")
            payload["share_effect"] = {rid: dict(eff) for rid, eff in inp.share_effect.items()}
            # Hedefler bu paylara göre bildirildi; kapanışta paylar değişmişse öneri uygulanamaz.
            payload["share_base"] = {
                rid: dict(r.shares) for rid in payload["share_effect"]
                if (r := ctx.graph.resource(rid)) is not None and r.divisible
            }
        parent_rid = None
        addressee = inp.addressee
        if t is ProposalType.ALT_KONU:
            parent = _live_topic(ctx, inp.parent_topic_id)
            payload["parent_topic_id"] = parent.id
            parent_rid = parent.resource_id
            key = f"ALT_KONU:{parent.id}:{normalize(title)}"
            addressee = addressee or parent.addressee
        else:
            key = f"KONU:{inp.area_id}:{normalize(title)}"
        payload["addressee"] = addressee
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
             "new_text": new_text, "opening": msg.is_opening, "addressee": INTERNAL},
        )

    if t is ProposalType.SILME:
        if (inp.target_message_id is None) == (inp.target_topic_id is None):
            raise DomainError("Silinecek mesajı ya da konuyu (yalnızca birini) belirtin.")
        own = False
        if inp.target_message_id is not None:
            msg = topics.get_message(ctx, inp.target_message_id)
            if msg.deleted_by_proposal_id is not None:
                raise Conflict("Bu mesaj zaten silindi.")
            topic = _live_topic(ctx, msg.topic_id, must_be_open=False)
            target = {"message_id": msg.id}
            key = f"ICERIK:mesaj:{msg.id}"
            default_title = f"Silme: {topic.title} konusundaki #{msg.id} numaralı mesaj"
            # Yazarın rızası: kendi mesajı için gerekçe gerekmez, basit çoğunluk yeter. Konu
            # silme hiçbir zaman "kendi" sayılmaz; başkalarının mesajlarını da götürür.
            own = msg.author_id == user.id
        else:
            topic = _live_topic(ctx, inp.target_topic_id, must_be_open=False)
            target = {}
            key = f"ICERIK:konu:{topic.id}"
            default_title = f"Silme: {topic.title}"
        rules = list(dict.fromkeys(code.strip() for code in inp.content_rules if code.strip()))
        return Prepared(
            t, _title(inp.title or default_title), _body(inp.body, required=False),
            topic.area_id, inp.scope_id or topic.owner_scope_id, [topic.resource_id], key,
            {"topic_id": topic.id, **target, "rules": rules, "excerpt": inp.excerpt.strip(),
             "own": own, "addressee": INTERNAL},
        )

    if t is ProposalType.YONETMELIK:
        prep = _prepare_regulation(ctx, inp)
        prep.payload["addressee"] = INTERNAL
        return prep

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
        f"KAPANIS:{topic.id}", {"topic_id": topic.id, "addressee": topic.addressee},
    )


def _prepare_regulation(ctx: Ctx, inp: ProposalInput) -> Prepared:
    action = inp.article_action or "degistir"
    if action not in regulation.ACTIONS:
        raise DomainError("Yönetmelik işlemi 'degistir', 'ekle' ya da 'kaldir' olmalı.")
    body, scope = _body(inp.body, required=False), inp.scope_id or GENERAL_SCOPE_ID
    current = ctx.graph.articles()

    if action == "ekle":
        key = regulation.next_content_rule_code(ctx)
        try:
            new_value = validate_value(key, inp.new_value or {})
        except RegulationError as exc:
            raise DomainError(str(exc)) from exc
        title = f"Yönetmelik: {key} eklensin ({new_value['baslik']})"
        # Hedef anahtarı kuralın başlığı: reddedilen ekleme yeni bir kodla hemen geri gelemez (R6).
        return Prepared(
            ProposalType.YONETMELIK, _title(inp.title or title), body, None, scope,
            [regulation.CONTENT_RULES_RESOURCE_ID], f"MADDE:ekle:{normalize(new_value['baslik'])}",
            {"article_key": key, "action": "ekle", "old_value": None, "new_value": new_value},
        )

    key = inp.article_key or ""
    kind = article_kind(key)
    if kind is None or key not in current:
        raise DomainError("Böyle bir yönetmelik maddesi yok ya da yürürlükte değil.")
    old_value = current[key]
    if ctx.reg.is_unchangeable(key):
        # Değer doğrulanmaz: öneri R8'de "Bu madde değiştirilemez" gerekçesiyle reddedilir.
        return Prepared(
            ProposalType.YONETMELIK,
            _title(inp.title or f"Yönetmelik: {article_title(key, old_value)}"), body, None, scope,
            [regulation.article_resource_id(key)], f"MADDE:{key}",
            {"article_key": key, "action": action, "old_value": old_value,
             "new_value": inp.new_value},
        )
    if action == "kaldir":
        if kind != CONTENT_RULE_KIND:
            raise DomainError("Yalnızca içerik kuralları kaldırılabilir; parametrelerin değeri değişir.")
        title = f"Yönetmelik: {key} kaldırılsın ({old_value['baslik']})"
        return Prepared(
            ProposalType.YONETMELIK, _title(inp.title or title), body, None, scope,
            [regulation.article_resource_id(key)], f"MADDE:{key}",
            {"article_key": key, "action": "kaldir", "old_value": old_value, "new_value": None},
        )

    try:
        new_value = validate_value(key, inp.new_value or {})
    except RegulationError as exc:
        raise DomainError(str(exc)) from exc
    if new_value == old_value:
        raise DomainError("Önerilen değer mevcut değerle aynı.")
    return Prepared(
        ProposalType.YONETMELIK,
        _title(inp.title or f"Yönetmelik: {article_title(key, old_value)}"), body, None, scope,
        [regulation.article_resource_id(key)], f"MADDE:{key}",
        {"article_key": key, "action": "degistir", "old_value": old_value, "new_value": new_value},
    )


# --- denetim ------------------------------------------------------------------------------------


def last_rejection(ctx: Ctx, target_key: str, exclude_id: int | None = None):
    q = select(func.max(Proposal.decided_at)).where(
        Proposal.target_key == target_key, Proposal.status == "REJECTED"
    )
    if exclude_id is not None:
        q = q.where(Proposal.id != exclude_id)
    return ctx.db.execute(q).scalar()


def deletion_target_text(ctx: Ctx, payload: dict) -> str:
    """Silinmesi önerilen içeriğin güncel metni (mesaj ya da konu başlığı + açılış metni)."""
    if payload.get("message_id") is not None:
        msg = ctx.db.get(Message, payload["message_id"])
        return topics.current_version(ctx, msg).text if msg else ""
    topic = ctx.db.get(Topic, payload.get("topic_id"))
    if topic is None:
        return ""
    opening = ctx.db.execute(select(Message).where(
        Message.topic_id == topic.id, Message.is_opening.is_(True)
    )).scalar_one_or_none()
    return f"{topic.title}\n{topics.current_version(ctx, opening).text if opening else ''}"


def draft_of(ctx: Ctx, p: Proposal | Prepared, proposer_id: str) -> ProposalDraft:
    parent = p.parent_resource_id if isinstance(p, Prepared) else (
        f"konu:{p.payload['parent_topic_id']}" if p.payload.get("parent_topic_id") else None
    )
    deletion = str(p.type) == "SILME"
    return ProposalDraft(
        type=ProposalType(p.type), proposer_id=proposer_id, scope_id=p.scope_id,
        area_id=p.area_id, resource_ids=tuple(p.resource_ids), parent_topic_id=parent,
        target_key=p.target_key, title=p.title, body=p.body,
        content_rules=tuple(p.payload.get("rules", ())) if deletion else (),
        excerpt=p.payload.get("excerpt", "") if deletion else "",
        target_text=deletion_target_text(ctx, p.payload) if deletion else "",
        own_content=bool(p.payload.get("own")) if deletion else False,
        share_effect=p.payload.get("share_effect"),
        article_key=p.payload.get("article_key") if str(p.type) == "YONETMELIK" else None,
        article_action=p.payload.get("action") if str(p.type) == "YONETMELIK" else None,
        new_value=p.payload.get("new_value") if str(p.type) == "YONETMELIK" else None,
        addressee=p.payload.get("addressee"),
    )


def share_impacts(ctx: Ctx, p: Proposal | Prepared) -> list[ShareImpact]:
    """Bütünün (kaynak sahibinin) oyladığı pay değişiklikleri. R2 ile daraltılmış öneriler muaf."""
    out = []
    for rid, effect in (p.payload.get("share_effect") or {}).items():
        r = ctx.graph.resource(rid)
        if r is None or not r.divisible or p.scope_id != r.owner_scope_id:
            continue
        out.append(share_impact(rid, r.shares, effect, ctx.reg.number("orantisizlik_esigi")))
    return out


def concurrent_scopes(ctx: Ctx, p: Proposal) -> list[str]:
    """Orantısız etkilenen ve bu yüzden ayrıca oylayacak alt kapsamlar."""
    return list(dict.fromkeys(sid for imp in share_impacts(ctx, p) for sid in imp.disproportionate))


def deletion_check(ctx: Ctx, p: Proposal) -> ContentCheck | None:
    """Hâtif'in H4 denetimi: silme önerisinin dayandığı kuralların alıntıdaki karşılığı."""
    if p.type != "SILME":
        return None
    return content_check(p.payload.get("rules", ()), p.payload.get("excerpt", ""),
                         ctx.reg.content_rules(), own=bool(p.payload.get("own")))


def threshold_key(p: Proposal) -> str:
    """Karar Saati'nde uygulanacak eşik maddesi."""
    if p.type == "YONETMELIK":
        return "yonetmelik_esigi"
    if p.type == "SILME" and not p.payload.get("own"):
        return "silme_esigi"
    return "basit_cogunluk"


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
    if p.lane == "FAST" and concurrent_scopes(ctx, p):
        # Orantısız etkilenen kapsamın vetosu sessiz onayla atlanamaz: doğrudan yavaş şerit.
        p.lane = "SLOW"
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
    p.oracle_comment = oracle_comment(
        report, findings, ctx.graph, deletion_check(ctx, p),
        extra=impact_lines(share_impacts(ctx, p), lambda sid: ontology.scope_label(ctx, sid)),
    )
    p.oracle_findings = [{"kind": f.kind, "suggestion": f.suggestion, "message": f.message}
                         for f in findings]
    _start_lane(ctx, p)
    ctx.db.flush()
    ctx.graph.record_proposal(p.id, p.type, p.scope_id, list(p.resource_ids), p.status)
    proposer = ctx.db.get(User, p.proposer_id)
    ledger.enqueue(ctx, "ONERI_ACILDI", {
        "oneri": p.id, "tur": p.type, "baslik": p.title, "metin": p.body,
        "oneren": proposer.nickname if proposer else p.proposer_id,
        "secmen": p.scope_id, "alan": p.area_id, "etkiler": list(p.resource_ids),
        "daraltma": [n["message"] for n in p.narrowings], "ayrinti": p.payload,
    }, ref=p)
    if p.type == "KAPANIS":
        # Açılış metni de rakip metinler gibi kendi kaydıyla mühürlenir (metin_no oylamada anılır).
        ct = ClosureText(proposal_id=p.id, author_id=p.proposer_id, text=p.body, created_at=ctx.now)
        ctx.db.add(ct)
        ctx.db.flush()
        ledger.enqueue(ctx, "KAPANIS_METNI", {
            "oneri": p.id, "metin_no": ct.id,
            "yazar": proposer.nickname if proposer else p.proposer_id, "metin": ct.text,
        }, ref=ct)


def _cover(ctx: Ctx, user: User, inp: ProposalInput, t: ProposalType) -> list[Media]:
    if not inp.cover_media_id:
        return []
    if t not in (ProposalType.KONU, ProposalType.ALT_KONU) or inp.reopens_topic_id is not None:
        raise DomainError("Kapak görseli yalnızca yeni konu önerisine eklenir.")
    return media.check_attachable(ctx, user.id, [inp.cover_media_id], limit=1)


def open_proposal(ctx: Ctx, user: User, inp: ProposalInput) -> Proposal:
    prep = _prepare(ctx, user, inp)
    cover = _cover(ctx, user, inp, prep.type)
    report = run_rules(ctx, draft_of(ctx, prep, user.id))
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
    media.attach(ctx, cover, "oneri", p.id)
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
        scope_id=inp.scope_id, resource_ids=inp.resource_ids, addressee=inp.addressee,
    ))
    cover = _cover(ctx, user, inp, ProposalType.KONU)
    report = run_rules(ctx, draft_of(ctx, prep, user.id), exclude_id=p.id)
    if not report.ok:
        _raise_violations(report)
    p.title, p.body, p.area_id, p.scope_id = prep.title, prep.body, prep.area_id, prep.scope_id
    p.resource_ids, p.target_key = prep.resource_ids, prep.target_key
    p.payload = {**p.payload, **prep.payload}
    p.created_at = ctx.now
    _finish_opening(ctx, p, report)
    media.attach(ctx, cover, "oneri", p.id)
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
        notifications.moved_to_slow_lane(ctx, p, count, threshold)
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
    """Sessiz onay süresi doldu ve itiraz eşiği aşılmadı: kabul (pay çakışması yoksa)."""
    if p.status == "SILENT":
        accept_or_conflict(ctx, p)
        notifications.silent_period_ended(ctx, p)


def end_rival_period(ctx: Ctx, p: Proposal) -> None:
    if p.status == "RIVAL_PERIOD":
        p.status, p.queued_at = "QUEUED", ctx.now
        ctx.graph.set_proposal_status(p.id, p.status)


# --- sonuç ve etkiler ---------------------------------------------------------------------------


def _apply_share_effect(ctx: Ctx, p: Proposal) -> None:
    """Kabul edilen önerinin bildirdiği yeni paylar kaynağa işlenir."""
    for rid, effect in (p.payload.get("share_effect") or {}).items():
        r = ctx.graph.resource(rid)
        if r is None or not effect:
            continue
        new = {sid: int(effect.get(sid, old)) for sid, old in r.shares.items()}
        if new == dict(r.shares):
            continue
        ctx.graph.upsert_resource(replace(r, shares=new))
        ledger.enqueue(ctx, "PAY_DEGISTI", {
            "oneri": p.id, "kaynak": rid, "eski": dict(r.shares), "yeni": new,
        })


def _new_topic(ctx: Ctx, p: Proposal, parent_id: int | None) -> Topic:
    topic = Topic(
        title=p.title, area_id=p.area_id, parent_id=parent_id, owner_scope_id=p.scope_id,
        author_id=p.proposer_id, status="OPEN", created_at=ctx.now, accepted_proposal_id=p.id,
        addressee=p.payload.get("addressee"),
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
        topic = _new_topic(ctx, p, p.payload.get("parent_topic_id"))
        _apply_share_effect(ctx, p)
        # Kurum muhataplı konu: kabul edilen talep kuruma dilekçe olarak gider.
        petitions.send(ctx, topic, p, "TALEP", p.body)
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
            "kurallar": p.payload.get("rules", []), "kendi": bool(p.payload.get("own")),
            "not": "İçerik sitede gizlendi; defterdeki kayıtları silinmez.",
        })
    elif t is ProposalType.YONETMELIK:
        action = p.payload.get("action", "degistir")
        regulation.apply_change(ctx, p.payload["article_key"], p.payload["new_value"], p.id,
                                action=action)
        ledger.enqueue(ctx, "YONETMELIK_DEGISTI", {
            "oneri": p.id, "madde": p.payload["article_key"], "islem": action,
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
        # Kurum muhataplı konunun Kararı aynı kuruma karar bildirimi olarak iletilir.
        petitions.send(ctx, topic, p, "KARAR", d.text)


def share_conflicts(ctx: Ctx, p: Proposal) -> list[dict]:
    """Önerinin pay hedefleri, dayandıkları paylar (``share_base``) değiştiyse geçersizdir.

    Kaynak başına çakışma döner; ``by``, aynı kaynağa dokunup bu öneri açıldıktan sonra kabul
    edilmiş en son öneridir (aynı oturumda öneriler numara sırasıyla uygulandığı için, numarası
    daha küçük olan)."""
    out = []
    for rid, base in (p.payload.get("share_base") or {}).items():
        r = ctx.graph.resource(rid)
        if r is None or dict(r.shares) == {sid: int(v) for sid, v in base.items()}:
            continue
        later = ctx.db.execute(
            select(Proposal).where(
                Proposal.id != p.id, Proposal.status == "ACCEPTED",
                Proposal.decided_at >= p.created_at,
            ).order_by(Proposal.decided_at.desc(), Proposal.id.desc())
        ).scalars()
        by = next((q.id for q in later if rid in (q.payload.get("share_effect") or {})), None)
        out.append({"resource_id": rid, "name": r.name, "by": by})
    return out


def conflict_note(conflicts: list[dict]) -> str:
    parts = [(f"№{c['by']} {c['name']} paylarını daha önce değiştirdi" if c["by"]
              else f"{c['name']} payları öneri açıldıktan sonra değişti") for c in conflicts]
    return ("Kabul oyu aldı ama çakışma nedeniyle uygulanamadı: " + "; ".join(parts) + ". "
            "Öneri reddedilmiş sayılmaz; güncel paylarla aynı içerikle yeniden açılabilir.")


def mark_conflict(ctx: Ctx, p: Proposal, conflicts: list[dict]) -> None:
    note = conflict_note(conflicts)
    p.status, p.decided_at, p.outcome_note = "CONFLICT", ctx.now, note
    ctx.graph.set_proposal_status(p.id, p.status)
    ledger.enqueue(ctx, "ONERI_SONUCU", {
        "oneri": p.id, "sonuc": "UYGULANAMADI", "not": note,
        "cakisma": [{"kaynak": c["resource_id"], "oneri": c["by"]} for c in conflicts],
    })
    ctx.db.flush()


def accept_or_conflict(ctx: Ctx, p: Proposal, *, note: str | None = None) -> list[dict]:
    """Kabul eder; pay hedefleri geçersizse uygulamaz, çakışma olarak işaretler. Çakışmaları döner."""
    conflicts = share_conflicts(ctx, p)
    if conflicts:
        mark_conflict(ctx, p, conflicts)
    else:
        accept(ctx, p, note=note)
    return conflicts


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


def decides_at(ctx: Ctx, p: Proposal) -> datetime | None:
    """Açık önerinin karara bağlanacağı an: sessiz onay bitişi, açık oturumun kapanışı ya da
    olgunlaştıktan sonraki ilk Karar Saati."""
    from mesveret.services import decision_hour  # decision_hour bu modülü içe aktarır

    if p.status == "SILENT":
        return p.deadline_at
    if p.status == "VOTING":
        session = decision_hour.open_session_row(ctx)
        return session.closes_at if session else None
    if p.status in ("QUEUED", "RIVAL_PERIOD"):
        return maturity(ctx, p)["first_session_at"]
    return None


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
        "addressee": petitions.addressee_view(ctx, p.payload.get("addressee")),
    }


def list_proposals(ctx: Ctx, state: str | None, viewer: User | None) -> list[dict]:
    q = select(Proposal).order_by(Proposal.id.desc())
    if state == "open":
        q = q.where(Proposal.status.in_(OPEN_STATUSES))
    elif state == "decided":
        q = q.where(Proposal.status.in_(("ACCEPTED", "REJECTED", "CONFLICT")))
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
    impacts = share_impacts(ctx, p)
    if p.status in (*OPEN_STATUSES, "CONFLICT") and (changed := share_conflicts(ctx, p)):
        # Pay tablosu öneri açıldıktan sonra değişti: Hâtif'in sayısal yorumu güncel paylara göre
        # yeniden üretilir; açılıştaki yorum "öneri anında" etiketiyle kalır.
        body["oracle_current"] = {
            "lines": impact_lines(impacts, lambda sid: ontology.scope_label(ctx, sid)),
            "cause": [c["by"] for c in changed if c["by"]],
        }
    body["share_effect"] = [
        {"resource_id": imp.resource_id, "name": ctx.graph.resource(imp.resource_id).name,
         "average_pct": pct(imp.average), "threshold_pp": float(imp.threshold_pp),
         "rows": [{"scope_id": r.scope_id, "name": ontology.scope_label(ctx, r.scope_id),
                   "old": r.old, "new": r.new, "change_pct": pct(r.relative),
                   "disproportionate": r.scope_id in imp.disproportionate} for r in imp.rows]}
        for imp in impacts
    ]
    body["concurrent_scopes"] = [
        {"id": sid, "name": ontology.scope_label(ctx, sid)}
        for sid in dict.fromkeys(s for imp in impacts for s in imp.disproportionate)
    ]
    if p.type == "DUZENLEME":
        msg = ctx.db.get(Message, p.payload["message_id"])
        base = topics.current_version(ctx, msg).text if msg else ""
        body["current_text"] = base
        body["diff"] = [list(c) for c in word_diff(base, p.payload["new_text"])]
    if p.type == "SILME" and p.status not in ("ACCEPTED",):
        body["target_preview"] = _target_preview(ctx, p)
    if p.type == "SILME":
        rules = ctx.reg.content_rules()
        body["content_rules"] = [{"code": c, "title": rules[c].title if c in rules else c}
                                 for c in p.payload.get("rules", [])]
        body["excerpt"] = p.payload.get("excerpt", "")
        body["own"] = bool(p.payload.get("own"))
    if p.type == "YONETMELIK":
        key = p.payload["article_key"]
        body["article"] = {"key": key, "kind": article_kind(key),
                           "title": article_title(key, p.payload.get("new_value")
                                                  or p.payload.get("old_value"))}
    if p.type != "KAPANIS":
        key = threshold_key(p)
        raw = ctx.reg.raw(key)
        body["threshold"] = {"key": key, "oran": raw["oran"],
                             "karsilastirma": raw.get("karsilastirma", ">=")}
    if p.type == "KAPANIS":
        texts = closure_texts(ctx, p)
        tn = nickname_map(ctx, [ct.author_id for ct in texts])
        body["texts"] = [{"id": ct.id, "author": tn.get(ct.author_id), "text": ct.text,
                          "created_at": ct.created_at, "ledger_hash": ct.ledger_hash}
                         for ct in texts]
        d = ctx.db.execute(select(Decision).where(Decision.proposal_id == p.id)).scalar_one_or_none()
        body["decision_id"] = d.id if d else None
    if p.type in ("KONU", "ALT_KONU"):
        body["cover"] = media.cover(ctx, p.id)
    if p.type in ("KONU", "ALT_KONU") and p.status == "ACCEPTED":
        body["topic_id"] = ctx.db.execute(
            select(Topic.id).where(Topic.accepted_proposal_id == p.id)
        ).scalar_one_or_none()
    if p.session_id is not None:
        item = ctx.db.execute(select(SessionItem).where(
            SessionItem.session_id == p.session_id, SessionItem.proposal_id == p.id,
            SessionItem.concurrent.is_(False),
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
