"""Karar Saati: planlı oylama oturumu.

Pencere açılırken her öneri için anlık görüntü alınır (seçmenler, baskın dışlaması, havale
çözümlemesi, yönetmelik değerleri) ve havale grafı kilitlenir. Oylar pencere boyunca
mühürlüdür: deftere yalnızca commit yazılır. Pencere kapanınca oylar açılır, anlık görüntü
üzerinden ağırlıklı sayım yapılır ve sonuçlar uygulanır.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import select

from mesveret.context import Ctx
from mesveret.db.models import (
    Ballot,
    ClosureText,
    Decision,
    DecisionSession,
    DevVotePlan,
    Dissent,
    Proposal,
    SessionItem,
    User,
)
from mesveret.domain.commit import make_commit, new_salt
from mesveret.domain.decision_hour import next_occurrence
from mesveret.domain.delegation import resolve_all
from mesveret.domain.oracle import label_check, oracle_vote
from mesveret.domain.raid import detect_raids
from mesveret.domain.regulation import Regulation
from mesveret.domain.tally import tally_approval, tally_binary
from mesveret.errors import Conflict, DomainError, Forbidden, NotFound
from mesveret.services import ledger, ontology, proposals, topics
from mesveret.services.oracle import ORACLE_ID
from mesveret.services.profile import nickname_map

log = logging.getLogger("mesveret.karar_saati")

YES, NO = "EVET", "HAYIR"


# --- oturum sorguları ---------------------------------------------------------------------------


def open_session_row(ctx: Ctx) -> DecisionSession | None:
    return ctx.db.execute(
        select(DecisionSession).where(DecisionSession.status == "OPEN")
    ).scalar_one_or_none()


def get_session(ctx: Ctx, session_id: int) -> DecisionSession:
    s = ctx.db.get(DecisionSession, session_id)
    if s is None:
        raise NotFound("Oturum bulunamadı.")
    return s


def items_of(ctx: Ctx, session: DecisionSession) -> list[SessionItem]:
    return list(ctx.db.execute(
        select(SessionItem).where(SessionItem.session_id == session.id).order_by(SessionItem.id)
    ).scalars())


def _item(ctx: Ctx, session: DecisionSession, proposal_id: int) -> SessionItem:
    item = ctx.db.execute(select(SessionItem).where(
        SessionItem.session_id == session.id, SessionItem.proposal_id == proposal_id
    )).scalar_one_or_none()
    if item is None:
        raise NotFound("Bu öneri bu oturumda oylanmıyor.")
    return item


# --- açılış -------------------------------------------------------------------------------------


def _snapshot(ctx: Ctx, session: DecisionSession, p: Proposal, delegations) -> SessionItem:
    members = ontology.eligible_voters(ctx, p.scope_id)
    joined = {uid: m.since for uid, m in members.items()}
    clusters = detect_raids(joined, ctx.graph.interactions_among(members), ctx.now, ctx.reg)
    flagged = [{"user_id": uid, "reason": c.reason} for c in clusters for uid in sorted(c.members)]
    flagged_ids = {f["user_id"] for f in flagged}
    eligible = sorted(set(members) - flagged_ids)
    item = SessionItem(
        session_id=session.id, proposal_id=p.id, area_id=p.area_id, eligible=eligible,
        resolved=resolve_all(delegations, p.area_id, ctx.graph, eligible), flagged=flagged,
    )
    ctx.db.add(item)
    p.status, p.session_id = "VOTING", session.id
    ctx.graph.set_proposal_status(p.id, p.status)
    return item


def _oracle_decision(ctx: Ctx, p: Proposal) -> tuple[bool, str]:
    report = proposals.run_rules(ctx, proposals.draft_of(p, p.proposer_id), exclude_id=p.id)
    findings = label_check(proposals.oracle_text(p), p.area_id, p.scope_id, p.resource_ids,
                           ctx.graph)
    parts = [f"{v.rule}: {v.message}" for v in report.violations]
    parts += [f"{f.kind}: {f.message}" for f in findings]
    vote = oracle_vote(report, findings)
    reason = "R1–R6 geçti; etiketler uyumlu." if vote else " ".join(parts)
    return vote, reason


def open_session(
    ctx: Ctx, *, scheduled_for: datetime | None = None, scripted: bool = False
) -> DecisionSession:
    if open_session_row(ctx) is not None:
        raise Conflict("Açık bir Karar Saati oturumu var.")
    spec = ctx.reg.decision_hour()
    session = DecisionSession(
        scheduled_for=scheduled_for, opened_at=ctx.now, closes_at=ctx.now + spec.window,
        status="OPEN", regulation=ctx.graph.articles(), scripted=scripted,
    )
    ctx.db.add(session)
    ctx.db.flush()
    queued = ctx.db.execute(
        select(Proposal).where(Proposal.status == "QUEUED", Proposal.queued_at <= ctx.now)
        .order_by(Proposal.id)
    ).scalars().all()
    delegations = ctx.graph.delegations()
    items = [(p, _snapshot(ctx, session, p, delegations)) for p in queued]
    ctx.db.flush()
    names = nickname_map(ctx, [f["user_id"] for _, it in items for f in it.flagged])
    ledger.enqueue(ctx, "OTURUM_ACILDI", {
        "oturum": session.id, "acilis": ctx.now.isoformat(),
        "kapanis": session.closes_at.isoformat(), "oneriler": [p.id for p, _ in items],
        "secmen_sayilari": {str(p.id): len(it.eligible) for p, it in items},
        "baskin_isaretli": {str(p.id): [names.get(f["user_id"]) for f in it.flagged]
                            for p, it in items if it.flagged},
    }, ref=session)

    oracle = ctx.db.get(User, ORACLE_ID)
    for p, item in items:
        if oracle is None or ORACLE_ID not in item.eligible or item.resolved.get(ORACLE_ID) != ORACLE_ID:
            continue
        vote, reason = _oracle_decision(ctx, p)
        item.oracle_note = {"choice": YES if vote else NO, "reason": reason}
        choice: Any = vote
        if p.type == "KAPANIS":
            choice = [ct.id for ct in proposals.closure_texts(ctx, p)] if vote else []
        _cast(ctx, session, item, p, oracle, choice)

    if scripted:
        apply_vote_plan(ctx, session)
    ctx.commit()
    return session


def apply_vote_plan(ctx: Ctx, session: DecisionSession) -> list[str]:
    """Yalnızca geliştirme: tohum kullanıcılarının planlı oylarını verir."""
    report = []
    for item in items_of(ctx, session):
        plan = ctx.db.execute(
            select(DevVotePlan).where(DevVotePlan.proposal_id == item.proposal_id)
            .order_by(DevVotePlan.id)
        ).scalars().all()
        p = ctx.db.get(Proposal, item.proposal_id)
        for row in plan:
            voter = ctx.db.get(User, row.voter_id)
            choice = row.choice == YES if isinstance(row.choice, str) else row.choice
            try:
                _cast(ctx, session, item, p, voter, choice)
            except DomainError as exc:
                report.append(f"#{p.id} {voter.nickname}: {exc.message}")
    ctx.db.flush()
    return report


# --- oy -----------------------------------------------------------------------------------------


def _normalize_choice(p: Proposal, choice: Any, ctx: Ctx) -> Any:
    if p.type == "KAPANIS":
        if not isinstance(choice, list):
            raise DomainError("Kapanış oylamasında kabul edilebilir metinleri işaretleyin.")
        valid = {ct.id for ct in proposals.closure_texts(ctx, p)}
        ids = sorted({int(c) for c in choice})
        if not set(ids) <= valid:
            raise DomainError("Geçersiz karar metni.")
        return ids
    if not isinstance(choice, bool):
        raise DomainError("Bu oylamada EVET ya da HAYIR seçilmeli.")
    return YES if choice else NO


def _cast(ctx: Ctx, session: DecisionSession, item: SessionItem, p: Proposal, user: User,
          choice: Any) -> Ballot:
    flagged = {f["user_id"]: f["reason"] for f in item.flagged}
    if user.id in flagged:
        raise Forbidden(f"Bu oylamada baskın şüphesiyle işaretlendiniz ve dışlandınız. "
                        f"{flagged[user.id]}")
    if user.id not in item.eligible:
        raise Forbidden("Bu öneride oy hakkınız yok (seçmen listesi pencere açılırken alındı).")
    terminal = item.resolved.get(user.id, user.id)
    if terminal != user.id:
        name = nickname_map(ctx, [terminal]).get(terminal, terminal)
        raise Forbidden(f"Bu alanda oyunuzu havale ettiniz (zincir {name} adlı yurttaşta "
                        "bitiyor); oy kullanamazsınız.")
    existing = ctx.db.execute(select(Ballot.id).where(
        Ballot.session_id == session.id, Ballot.proposal_id == p.id, Ballot.voter_id == user.id
    )).first()
    if existing:
        raise Conflict("Bu öneriye oyunuzu zaten verdiniz; mühürlü oy değiştirilemez.")
    normalized = _normalize_choice(p, choice, ctx)
    salt = new_salt()
    doc = {"oturum": session.id, "oneri": p.id, "secmen": user.id, "secim": normalized}
    b = Ballot(session_id=session.id, proposal_id=p.id, voter_id=user.id, choice=normalized,
               salt=salt, commit=make_commit(doc, salt), created_at=ctx.now)
    ctx.db.add(b)
    ctx.db.flush()
    ledger.enqueue(ctx, "OY_MUHUR", {
        "oturum": session.id, "oneri": p.id, "secmen": user.nickname, "commit": b.commit,
    }, ref=b, ref_attr="commit_ledger_hash")
    return b


def cast_vote(ctx: Ctx, user: User, proposal_id: int, choice: Any) -> Ballot:
    session = open_session_row(ctx)
    if session is None:
        raise Conflict("Şu anda açık bir Karar Saati penceresi yok.")
    if ctx.now >= session.closes_at:
        raise Conflict("Oy penceresi kapandı.")
    item = _item(ctx, session, proposal_id)
    b = _cast(ctx, session, item, proposals.get_proposal(ctx, proposal_id), user, choice)
    ctx.commit()
    return b


# --- kapanış ------------------------------------------------------------------------------------


def _reveal(ctx: Ctx, session: DecisionSession, p: Proposal) -> list[Ballot]:
    ballots = list(ctx.db.execute(select(Ballot).where(
        Ballot.session_id == session.id, Ballot.proposal_id == p.id
    ).order_by(Ballot.id)).scalars())
    names = nickname_map(ctx, [b.voter_id for b in ballots])
    for b in ballots:
        doc = {"oturum": session.id, "oneri": p.id, "secmen": b.voter_id, "secim": b.choice}
        ledger.enqueue(ctx, "OY_ACILDI", {
            "oturum": session.id, "oneri": p.id, "secmen": names.get(b.voter_id),
            "oy": doc, "tuz": b.salt, "commit": b.commit,
        }, ref=b, ref_attr="reveal_ledger_hash")
    return ballots


def _votes_view(ctx: Ctx, item: SessionItem, ballots: list[Ballot], weights: dict) -> list[dict]:
    delegators: dict[str, list[str]] = {}
    for u, t in item.resolved.items():
        if u != t:
            delegators.setdefault(t, []).append(u)
    names = nickname_map(ctx, [b.voter_id for b in ballots]
                         + [u for us in delegators.values() for u in us])
    return [
        {
            "ballot_id": b.id, "voter": names.get(b.voter_id), "choice": b.choice,
            "weight": weights.get(b.voter_id, 0),
            "delegators": sorted(names.get(u, u) for u in delegators.get(b.voter_id, [])
                                 if u in item.eligible),
        }
        for b in ballots
    ]


def _close_item(ctx: Ctx, session: DecisionSession, item: SessionItem, reg: Regulation) -> None:
    p = ctx.db.get(Proposal, item.proposal_id)
    ballots = _reveal(ctx, session, p)
    eligible = set(item.eligible)
    flagged_names = nickname_map(ctx, [f["user_id"] for f in item.flagged])
    base: dict[str, Any] = {
        "eligible": len(eligible),
        "flagged": [{"nickname": flagged_names.get(f["user_id"]), "reason": f["reason"]}
                    for f in item.flagged],
        "oracle": item.oracle_note,
    }
    if p.type == "KAPANIS":
        texts = proposals.closure_texts(ctx, p)
        votes = {b.voter_id: set(b.choice) for b in ballots}
        t = tally_approval(votes, item.resolved, eligible, [ct.id for ct in texts])
        tn = nickname_map(ctx, [ct.author_id for ct in texts])
        result = {
            **base, "kind": "approval", "winner": t.winner, "tie": t.tie,
            "scores": [{"text_id": ct.id, "author": tn.get(ct.author_id), "text": ct.text,
                        "score": t.scores[ct.id]} for ct in texts],
            "abstained": len(t.abstained), "votes": _votes_view(ctx, item, ballots, t.weights),
        }
        if t.winner is not None:
            result["note"] = "En çok onayı alan metin Karar oldu."
            item.result = result
            proposals.accept(ctx, p, winner_text_id=t.winner, note=result["note"])
        else:
            result["note"] = ("Eşitlik: Karar çıkmadı." if t.tie else "Hiç onay yok: Karar çıkmadı.")
            item.result = result
            proposals.reject(ctx, p, result["note"])
    else:
        votes = {b.voter_id: b.choice == YES for b in ballots}
        t = tally_binary(votes, item.resolved, eligible)
        key = "yonetmelik_esigi" if p.type == "YONETMELIK" else "basit_cogunluk"
        ratio = reg.ratio(key)
        passed = ratio.passes(t.yes, t.cast)
        result = {
            **base, "kind": "binary", "yes": t.yes, "no": t.no, "cast": t.cast,
            "abstained": len(t.abstained), "passed": passed,
            "threshold": {"key": key, "oran": reg.raw(key)["oran"],
                          "karsilastirma": reg.raw(key).get("karsilastirma", ">=")},
            "votes": _votes_view(ctx, item, ballots, t.weights),
        }
        pct = f"%{100 * t.yes / t.cast:.1f}" if t.cast else "oy yok"
        result["note"] = (f"{t.yes}/{t.cast} ağırlıklı EVET ({pct}); eşik {key} "
                          f"{result['threshold']['karsilastirma']} {result['threshold']['oran']}.")
        item.result = result
        if passed:
            try:
                proposals.accept(ctx, p, note=result["note"])
            except DomainError as exc:
                proposals.reject(ctx, p, f"Kabul edildi ama uygulanamadı: {exc.message}")
        else:
            proposals.reject(ctx, p, result["note"])
    ledger.enqueue(ctx, "OYLAMA_SONUCU", {
        "oturum": session.id, "oneri": p.id,
        "sonuc": {k: v for k, v in result.items() if k != "votes"},
    })


def close_session(ctx: Ctx, session: DecisionSession) -> None:
    if session.status != "OPEN":
        raise Conflict("Oturum zaten kapalı.")
    reg = Regulation(session.regulation)
    for item in items_of(ctx, session):
        _close_item(ctx, session, item, reg)
    session.status, session.closed_at = "CLOSED", ctx.now
    ledger.enqueue(ctx, "OTURUM_KAPANDI", {"oturum": session.id, "kapanis": ctx.now.isoformat()})
    ctx.db.flush()


# --- zamanlayıcı olayları -----------------------------------------------------------------------


def due_events(ctx: Ctx, until: datetime, last: datetime | None) -> list:
    events: list[tuple[datetime, str, Callable[[Ctx], None]]] = []
    current = open_session_row(ctx)
    if current is not None and current.closes_at <= until:
        sid = current.id
        events.append((current.closes_at, f"Karar Saati #{sid} kapandı",
                       lambda c, sid=sid: close_session(c, get_session(c, sid))))
    if last is not None:
        occ = next_occurrence(last, ctx.reg.decision_hour())
        if occ <= until:
            events.append((occ, "haftalık Karar Saati açıldı",
                           lambda c, occ=occ: _open_scheduled(c, occ)))
    return events


def _open_scheduled(ctx: Ctx, occ: datetime) -> None:
    exists = ctx.db.execute(
        select(DecisionSession.id).where(DecisionSession.scheduled_for == occ)
    ).first()
    if exists:
        return
    if open_session_row(ctx) is not None:
        log.warning("Haftalık oturum açılamadı: açık bir oturum var (%s).", occ)
        return
    open_session(ctx, scheduled_for=occ)


# --- görünümler ---------------------------------------------------------------------------------


def status(ctx: Ctx) -> dict:
    current = open_session_row(ctx)
    spec = ctx.reg.decision_hour()
    last = ctx.db.execute(
        select(DecisionSession).where(DecisionSession.status == "CLOSED")
        .order_by(DecisionSession.closed_at.desc()).limit(1)
    ).scalar_one_or_none()
    return {
        "now": ctx.now,
        "open_session": None if current is None else {
            "id": current.id, "opened_at": current.opened_at, "closes_at": current.closes_at,
            "item_count": len(items_of(ctx, current)),
        },
        "next_scheduled_at": next_occurrence(ctx.now, spec),
        "window_minutes": int(spec.window.total_seconds() // 60),
        "last_session": None if last is None else {"id": last.id, "closed_at": last.closed_at},
        "queued": [
            {"id": p.id, "type": p.type, "title": p.title}
            for p in ctx.db.execute(select(Proposal).where(Proposal.status == "QUEUED")
                                    .order_by(Proposal.id)).scalars()
        ],
    }


def ballot(ctx: Ctx, user: User) -> dict:
    session = open_session_row(ctx)
    if session is None:
        return {"session": None, "items": []}
    out = []
    for item in items_of(ctx, session):
        p = ctx.db.get(Proposal, item.proposal_id)
        flagged = {f["user_id"]: f["reason"] for f in item.flagged}
        terminal = item.resolved.get(user.id)
        voted = ctx.db.execute(select(Ballot.id).where(
            Ballot.session_id == session.id, Ballot.proposal_id == p.id, Ballot.voter_id == user.id
        )).first() is not None
        entry: dict[str, Any] = {
            "proposal": proposals.summary(ctx, p, nickname_map(ctx, [p.proposer_id])),
            "kind": "approval" if p.type == "KAPANIS" else "binary",
            "voted": voted,
            "weight": sum(1 for e in item.eligible if item.resolved.get(e) == user.id),
            "narrowings": p.narrowings,
        }
        if user.id in flagged:
            entry.update(can_vote=False, reason=f"Baskın şüphesiyle dışlandınız. {flagged[user.id]}")
        elif user.id not in item.eligible:
            entry.update(can_vote=False, reason="Bu öneride oy hakkınız yok.")
        elif terminal != user.id:
            name = nickname_map(ctx, [terminal]).get(terminal, terminal)
            entry.update(can_vote=False, reason=f"Oyunuz havale zinciriyle {name} adlı yurttaşa gidiyor.")
        else:
            entry.update(can_vote=not voted, reason=None if not voted else "Oyunuz mühürlendi.")
        if p.type == "KAPANIS":
            tn = nickname_map(ctx, [ct.author_id for ct in proposals.closure_texts(ctx, p)])
            entry["texts"] = [{"id": ct.id, "author": tn.get(ct.author_id), "text": ct.text}
                              for ct in proposals.closure_texts(ctx, p)]
        out.append(entry)
    return {"session": {"id": session.id, "opened_at": session.opened_at,
                        "closes_at": session.closes_at}, "items": out}


def list_sessions(ctx: Ctx) -> list[dict]:
    rows = ctx.db.execute(select(DecisionSession).order_by(DecisionSession.id.desc())).scalars()
    return [{"id": s.id, "opened_at": s.opened_at, "closes_at": s.closes_at, "status": s.status,
             "closed_at": s.closed_at, "scheduled": s.scheduled_for is not None,
             "item_count": len(items_of(ctx, s))} for s in rows]


def session_view(ctx: Ctx, session_id: int) -> dict:
    s = get_session(ctx, session_id)
    hashes = {b.id: b.reveal_ledger_hash for b in ctx.db.execute(
        select(Ballot).where(Ballot.session_id == s.id)).scalars()}
    commits = ctx.db.execute(select(Ballot).where(Ballot.session_id == s.id)).scalars().all()
    items = []
    for item in items_of(ctx, s):
        p = ctx.db.get(Proposal, item.proposal_id)
        result = None
        if s.status == "CLOSED" and item.result is not None:
            result = dict(item.result)
            result["votes"] = [{**v, "ledger_hash": hashes.get(v["ballot_id"])}
                               for v in item.result.get("votes", [])]
        items.append({
            "proposal": proposals.summary(ctx, p, nickname_map(ctx, [p.proposer_id])),
            "eligible_count": len(item.eligible),
            "sealed_votes": sum(1 for b in commits if b.proposal_id == p.id),
            "result": result,
        })
    return {"id": s.id, "status": s.status, "opened_at": s.opened_at, "closes_at": s.closes_at,
            "closed_at": s.closed_at, "ledger_hash": s.ledger_hash, "items": items}


# --- şerh ---------------------------------------------------------------------------------------


def add_dissent(ctx: Ctx, user: User, decision_id: int, text: str) -> Dissent:
    d = ctx.db.get(Decision, decision_id)
    if d is None:
        raise NotFound("Karar bulunamadı.")
    losing = {ct.id: ct for ct in ctx.db.execute(select(ClosureText).where(
        ClosureText.proposal_id == d.proposal_id, ClosureText.id != d.closure_text_id
    )).scalars()}
    owns_losing = any(ct.author_id == user.id for ct in losing.values())
    p = ctx.db.get(Proposal, d.proposal_id)
    b = ctx.db.execute(select(Ballot).where(
        Ballot.session_id == p.session_id, Ballot.proposal_id == p.id, Ballot.voter_id == user.id
    )).scalar_one_or_none() if p and p.session_id else None
    supported_losing = b is not None and bool(set(b.choice or []) & set(losing))
    if not (owns_losing or supported_losing):
        raise Forbidden("Şerhi yalnızca kaybeden metinlerin sahipleri ya da destekçileri ekleyebilir.")
    if ctx.db.execute(select(Dissent.id).where(
        Dissent.decision_id == d.id, Dissent.author_id == user.id
    )).first():
        raise Conflict("Bu karara zaten şerh düştünüz; şerh düzenlenemez.")
    text = topics.check_square_text(text, max_len=5000)
    dissent = Dissent(decision_id=d.id, author_id=user.id, text=text, created_at=ctx.now)
    ctx.db.add(dissent)
    ctx.db.flush()
    ledger.enqueue(ctx, "SERH", {
        "karar": d.id, "yazar": user.nickname, "metin": text,
    }, ref=dissent)
    ctx.commit()
    return dissent
