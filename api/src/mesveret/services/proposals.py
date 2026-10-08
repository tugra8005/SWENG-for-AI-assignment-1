"""Öneri motoru (Facade): açılış denetimi, şeritler, itiraz, rakip metinler ve karar.

Hızlı şerit (sessiz onay): KONU, ALT_KONU, DUZENLEME.
Yavaş şerit (Karar Saati): SILME, YONETMELIK, KAPANIS ve itiraz eşiğine ulaşan hızlı şerit
önerileri.

Routers ve diğer servisler yalnızca bu modülü bilir. Arkasındaki parçalar:
- ``proposal_kinds``: türe özgü davranış (Strategy + Registry),
- ``domain.lifecycle``: durum geçişleri (State),
- ``domain.rules``: açılış denetimi (Chain of Responsibility),
- ``events``: kararın dünyadaki sonuçları (Observer).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from mesveret.context import Ctx
from mesveret.db.models import ClosureText, Media, Objection, Proposal, SessionItem, Topic, User
from mesveret.domain.lifecycle import (
    DECIDED_STATUSES,
    PENDING_STATUSES,
    InvalidTransition,
    ProposalState,
    opening_state,
    state_of,
)
from mesveret.domain.maturation import LABELS as MATURITY_LABELS
from mesveret.domain.maturation import (
    first_session_at,
    matures_at,
    maturity_class,
    maturity_duration,
)
from mesveret.domain.oracle import ContentCheck, label_check, oracle_comment
from mesveret.domain.rules import ProposalDraft, RuleContext, RuleReport, check_proposal
from mesveret.domain.scopes import GENERAL_SCOPE_ID
from mesveret.domain.shares import ShareImpact, impact_lines, pct, share_impact
from mesveret.domain.types import Lane, ProposalType, initial_lane
from mesveret.errors import Conflict, DomainError, Forbidden, NotFound
from mesveret.services import events, ledger, media, ontology, petitions, topics
from mesveret.services.profile import nickname_map
from mesveret.services.proposal_kinds import (  # noqa: F401  (dış kullanıcılar buradan alır)
    INTERNAL,
    MAX_BODY,
    MAX_TITLE,
    Prepared,
    ProposalInput,
    clean_body,
    closure_texts,
    deletion_target_text,
    kind_for,
    kind_for_input,
)

OPEN_STATUSES = PENDING_STATUSES


# --- yardımcılar --------------------------------------------------------------------------------


def get_proposal(ctx: Ctx, proposal_id: int) -> Proposal:
    p = ctx.db.get(Proposal, proposal_id)
    if p is None:
        raise NotFound("Öneri bulunamadı.")
    return p


def _move(p: Proposal, step: Callable[[ProposalState], ProposalState]) -> None:
    """Durum geçişi: geçerli değilse durumun kendi gerekçesiyle Conflict."""
    try:
        p.status = str(step(state_of(p.status)).status)
    except InvalidTransition as exc:
        raise Conflict(exc.message) from exc


def _allowed(p: Proposal, check: Callable[[ProposalState], None]) -> None:
    try:
        check(state_of(p.status))
    except InvalidTransition as exc:
        raise Conflict(exc.message) from exc


def is_pending(p: Proposal) -> bool:
    return state_of(p.status).pending


# --- denetim ------------------------------------------------------------------------------------


def last_rejection(ctx: Ctx, target_key: str, exclude_id: int | None = None):
    q = select(func.max(Proposal.decided_at)).where(
        Proposal.target_key == target_key, Proposal.status == "REJECTED"
    )
    if exclude_id is not None:
        q = q.where(Proposal.id != exclude_id)
    return ctx.db.execute(q).scalar()


def draft_of(ctx: Ctx, p: Proposal | Prepared, proposer_id: str) -> ProposalDraft:
    parent = p.parent_resource_id if isinstance(p, Prepared) else (
        f"konu:{p.payload['parent_topic_id']}" if p.payload.get("parent_topic_id") else None
    )
    return ProposalDraft(
        type=ProposalType(p.type), proposer_id=proposer_id, scope_id=p.scope_id,
        area_id=p.area_id, resource_ids=tuple(p.resource_ids), parent_topic_id=parent,
        target_key=p.target_key, title=p.title, body=p.body,
        share_effect=p.payload.get("share_effect"), addressee=p.payload.get("addressee"),
        **kind_for(p).draft_fields(ctx, p),
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
    return kind_for(p).content_check(ctx, p)


def threshold_key(p: Proposal) -> str | None:
    """Karar Saati'nde uygulanacak eşik maddesi (onay oylamasında ``None``)."""
    return kind_for(p).threshold_key(p)


def ballot_kind(p: Proposal) -> str:
    """Karar Saati'ndeki oylama biçimi: "binary" ya da "approval"."""
    return kind_for(p).ballot


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
    lane = initial_lane(t)
    if lane is Lane.FAST and concurrent_scopes(ctx, p):
        # Orantısız etkilenen kapsamın vetosu sessiz onayla atlanamaz: doğrudan yavaş şerit.
        lane = Lane.SLOW
    p.lane = str(lane)
    state = opening_state(t, lane)
    p.status = str(state.status)
    if state.status == "RIVAL_PERIOD":
        p.deadline_at = ctx.now + ctx.reg.duration("kapanis_rakip_suresi")
    elif state.status == "SILENT":
        p.deadline_at = ctx.now + ctx.reg.duration("sessiz_onay_suresi")
    else:
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
    name = proposer.nickname if proposer else p.proposer_id
    ledger.enqueue(ctx, "ONERI_ACILDI", {
        "oneri": p.id, "tur": p.type, "baslik": p.title, "metin": p.body,
        "oneren": name, "secmen": p.scope_id, "alan": p.area_id, "etkiler": list(p.resource_ids),
        "daraltma": [n["message"] for n in p.narrowings], "ayrinti": p.payload,
    }, ref=p)
    kind_for(p).after_open(ctx, p, name)


def _cover(ctx: Ctx, user: User, inp: ProposalInput) -> list[Media]:
    if not inp.cover_media_id:
        return []
    if not kind_for_input(inp).takes_cover:
        raise DomainError("Kapak görseli yalnızca yeni konu önerisine eklenir.")
    return media.check_attachable(ctx, user.id, [inp.cover_media_id], limit=1)


def open_proposal(ctx: Ctx, user: User, inp: ProposalInput) -> Proposal:
    """Şablon: türün hazırlığı → kapak → kural zinciri → açılış kaydı → türün kancası."""
    prep = kind_for_input(inp).prepare(ctx, user, inp)
    cover = _cover(ctx, user, inp)
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
    _allowed(p, lambda s: s.submit())
    if p.proposer_id != user.id:
        raise Forbidden("Taslağı yalnızca sahibi gönderebilir.")
    konu = ProposalInput(
        type="KONU", title=inp.title or p.title, body=inp.body or p.body, area_id=inp.area_id,
        scope_id=inp.scope_id, resource_ids=inp.resource_ids, addressee=inp.addressee,
        cover_media_id=inp.cover_media_id, event=inp.event,
    )
    prep = kind_for_input(konu).prepare(ctx, user, konu)
    cover = _cover(ctx, user, konu)
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
    _allowed(p, lambda s: s.object())
    if p.proposer_id == user.id:
        raise Forbidden("Kendi önerinize itiraz edemezsiniz.")
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
        _move(p, lambda s: s.escalate())
        p.lane, p.queued_at = "SLOW", ctx.now
        ctx.graph.set_proposal_status(p.id, p.status)
        ledger.enqueue(ctx, "ONERI_YAVAS_SERIDE", {
            "oneri": p.id, "itiraz": count, "esik": threshold,
        })
        events.publish(ctx, events.MovedToSlowLane(p, count, threshold))
    ctx.commit()
    return {"count": count, "threshold": threshold, "moved": moved}


def add_rival(ctx: Ctx, user: User, proposal_id: int, text: str) -> ClosureText:
    p = get_proposal(ctx, proposal_id)
    if p.type != "KAPANIS":
        raise DomainError("Rakip metin yalnızca kapanış önerisine eklenir.")
    _allowed(p, lambda s: s.add_rival())
    if p.deadline_at and ctx.now >= p.deadline_at:
        raise Conflict("Rakip metin süresi doldu.")
    topic = topics.get_topic(ctx, p.payload["topic_id"])
    if not topics.is_participant(ctx, topic, user.id):
        raise Forbidden("Rakip metni yalnızca konunun katılımcıları ekleyebilir.")
    if any(ct.author_id == user.id for ct in closure_texts(ctx, p)):
        raise Conflict("Bu kapanışa zaten bir metin eklediniz.")
    ct = ClosureText(proposal_id=p.id, author_id=user.id,
                     text=clean_body(text, label="Karar metni"), created_at=ctx.now)
    ctx.db.add(ct)
    ctx.db.flush()
    ledger.enqueue(ctx, "KAPANIS_METNI", {
        "oneri": p.id, "metin_no": ct.id, "yazar": user.nickname, "metin": ct.text,
    }, ref=ct)
    ctx.commit()
    return ct


# --- zamanlanmış geçişler ------------------------------------------------------------------------


def end_silent_period(ctx: Ctx, p: Proposal) -> None:
    """Sessiz onay süresi doldu ve itiraz eşiği aşılmadı: kabul (pay çakışması yoksa).
    İdempotent: öneri sessiz onayda değilse (zaten karara bağlandıysa) hiçbir şey yapmaz."""
    if p.status == "SILENT":
        accept_or_conflict(ctx, p)
        events.publish(ctx, events.SilentPeriodEnded(p))


def end_rival_period(ctx: Ctx, p: Proposal) -> None:
    if p.status == "RIVAL_PERIOD":
        _move(p, lambda s: s.end_rival_period())
        p.queued_at = ctx.now
        ctx.graph.set_proposal_status(p.id, p.status)


def enter_session(ctx: Ctx, p: Proposal, session_id: int) -> None:
    """Karar Saati açıldı: kuyruktaki öneri oylamaya alınır."""
    _move(p, lambda s: s.enter_session())
    p.session_id = session_id
    ctx.graph.set_proposal_status(p.id, p.status)


# --- sonuç --------------------------------------------------------------------------------------


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
    _move(p, lambda s: s.conflict())
    p.decided_at, p.outcome_note = ctx.now, note
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
    new_state = state_of(p.status)
    try:
        new_state = new_state.accept()
    except InvalidTransition as exc:
        raise Conflict(exc.message) from exc
    kind_for(p).apply(ctx, p, winner_text_id)
    p.status, p.decided_at, p.outcome_note = str(new_state.status), ctx.now, note
    ctx.graph.set_proposal_status(p.id, p.status)
    ledger.enqueue(ctx, "ONERI_SONUCU", {"oneri": p.id, "sonuc": "KABUL", "not": note})
    ctx.db.flush()


def reject(ctx: Ctx, p: Proposal, note: str) -> None:
    _move(p, lambda s: s.reject())
    p.decided_at, p.outcome_note = ctx.now, note
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


def list_proposals(ctx: Ctx, state: str | None, viewer: User | None,
                   mine: bool = False) -> list[dict]:
    q = select(Proposal).order_by(Proposal.id.desc())
    if state == "open":
        q = q.where(Proposal.status.in_(PENDING_STATUSES))
    elif state == "decided":
        q = q.where(Proposal.status.in_(DECIDED_STATUSES))
    elif state == "draft":
        if viewer is None:
            return []
        q = q.where(Proposal.status == "DRAFT", Proposal.proposer_id == viewer.id)
    if mine:
        if viewer is None:
            return []
        q = q.where(Proposal.proposer_id == viewer.id)
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
    if (is_pending(p) or p.status == "CONFLICT") and (changed := share_conflicts(ctx, p)):
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
    kind = kind_for(p)
    kind.view(ctx, p, body)
    if (key := kind.threshold_key(p)) is not None:
        raw = ctx.reg.raw(key)
        body["threshold"] = {"key": key, "oran": raw["oran"],
                             "karsilastirma": raw.get("karsilastirma", ">=")}
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
