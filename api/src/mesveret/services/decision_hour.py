"""Karar Saati: planlı oylama oturumu.

Pencere açılırken her öneri için anlık görüntü alınır (seçmenler, baskın dışlaması, havale
çözümlemesi, yönetmelik değerleri) ve havale grafı kilitlenir. Bölünebilir kaynakta orantısız
etkilenen her alt kapsam için aynı oturumda ayrı bir oylama açılır; öneri ancak hepsinde gerekli
çoğunluğu alırsa geçer (eşzamanlı çoğunluk). Oylar pencere boyunca
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
from mesveret.domain.text import decimal_tr
from mesveret.errors import Conflict, DomainError, Forbidden, NotFound
from mesveret.services import ledger, ontology, proposals, regulation, topics
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


def _item(ctx: Ctx, session: DecisionSession, proposal_id: int,
          vote_scope_id: str | None = None) -> SessionItem:
    """Önerinin ana oylaması ya da ``vote_scope_id`` verilirse o kapsamdaki oylaması."""
    q = select(SessionItem).where(
        SessionItem.session_id == session.id, SessionItem.proposal_id == proposal_id
    )
    q = (q.where(SessionItem.concurrent.is_(False)) if vote_scope_id is None
         else q.where(SessionItem.vote_scope_id == vote_scope_id))
    item = ctx.db.execute(q).scalar_one_or_none()
    if item is None:
        raise NotFound("Bu oylama bu oturumda yok.")
    return item


def _proposal_count(items: list[SessionItem]) -> int:
    return len({i.proposal_id for i in items})


# --- açılış -------------------------------------------------------------------------------------


def _snapshot(ctx: Ctx, session: DecisionSession, p: Proposal, delegations,
              vote_scope_id: str | None = None) -> SessionItem:
    concurrent = vote_scope_id is not None
    scope = vote_scope_id or p.scope_id
    members = ontology.eligible_voters(ctx, scope)
    joined = {uid: m.since for uid, m in members.items()}
    clusters = detect_raids(joined, ctx.graph.interactions_among(members), ctx.now, ctx.reg)
    flagged = [{"user_id": uid, "reason": c.reason} for c in clusters for uid in sorted(c.members)]
    flagged_ids = {f["user_id"] for f in flagged}
    eligible = sorted(set(members) - flagged_ids)
    if concurrent:
        # Alt kapsam oylamasında havale yalnızca o kapsamın seçmenleri arasında çözülür: dışarıya
        # giden havale bu oylamada uygulanmaz, üye oyunu kendisi verir.
        inside = set(eligible)
        delegations = {k: v for k, v in delegations.items() if k[0] in inside and v in inside}
    item = SessionItem(
        session_id=session.id, proposal_id=p.id, vote_scope_id=scope, concurrent=concurrent,
        area_id=p.area_id, eligible=eligible,
        resolved=resolve_all(delegations, p.area_id, ctx.graph, eligible), flagged=flagged,
    )
    ctx.db.add(item)
    if not concurrent:
        p.status, p.session_id = "VOTING", session.id
        ctx.graph.set_proposal_status(p.id, p.status)
    return item


def _item_key(p: Proposal, item: SessionItem) -> str:
    return f"{p.id}:{item.vote_scope_id}" if item.concurrent else str(p.id)


def _oracle_decision(ctx: Ctx, p: Proposal) -> tuple[bool, str]:
    report = proposals.run_rules(ctx, proposals.draft_of(ctx, p, p.proposer_id), exclude_id=p.id)
    findings = label_check(proposals.oracle_text(p), p.area_id, p.scope_id, p.resource_ids,
                           ctx.graph)
    content = proposals.deletion_check(ctx, p)
    parts = [f"{v.rule}: {v.message}" for v in report.violations]
    parts += [f"{f.kind}: {f.message}" for f in findings]
    if content is not None:
        parts += [f"H4: {m.code} ({m.title}) kuralının belirtilen kısımda karşılığı yok."
                  for m in content.matches if not m.ok]
    vote = oracle_vote(report, findings, content)
    if not vote:
        return vote, " ".join(parts)
    reason = "R1–R8 geçti; etiketler uyumlu."
    if content is not None and content.own:
        reason += " Yazar kendi mesajının silinmesini istiyor."
    elif content is not None:
        reason += " " + " ".join(
            f"{m.code} kuralının karşılığı var ({', '.join(repr(h) for h in m.hits)})."
            for m in content.matches
        )
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
    queued = [
        p for p in ctx.db.execute(
            select(Proposal).where(Proposal.status == "QUEUED", Proposal.queued_at <= ctx.now)
            .order_by(Proposal.id)
        ).scalars()
        # Olgunlaşmamış öneri bu oturuma alınmaz; kuyrukta kalır ve sonraki uygun oturuma kayar.
        if proposals.is_mature(ctx, p)
    ]
    # Açılış anında yürürlükteki havaleler: pencere sırasında süresi dolan havale bu oturum için
    # geçerli kalır, bitişi açılıştan önce gelmiş (zamanlayıcının henüz silmediği) havale alınmaz.
    delegations = ctx.graph.delegations(active_at=ctx.now)
    items: list[tuple[Proposal, SessionItem]] = []
    concurrent: dict[str, list[str]] = {}
    for p in queued:
        items.append((p, _snapshot(ctx, session, p, delegations)))
        for sid in proposals.concurrent_scopes(ctx, p):
            items.append((p, _snapshot(ctx, session, p, delegations, sid)))
            concurrent.setdefault(str(p.id), []).append(sid)
    ctx.db.flush()
    names = nickname_map(ctx, [f["user_id"] for _, it in items for f in it.flagged])
    ledger.enqueue(ctx, "OTURUM_ACILDI", {
        "oturum": session.id, "acilis": ctx.now.isoformat(),
        "kapanis": session.closes_at.isoformat(), "oneriler": [p.id for p in queued],
        "secmen_sayilari": {_item_key(p, it): len(it.eligible) for p, it in items},
        "eszamanli_oylamalar": concurrent,
        "baskin_isaretli": {_item_key(p, it): [names.get(f["user_id"]) for f in it.flagged]
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
        q = select(DevVotePlan).where(DevVotePlan.proposal_id == item.proposal_id)
        q = (q.where(DevVotePlan.vote_scope_id == item.vote_scope_id) if item.concurrent
             else q.where(DevVotePlan.vote_scope_id.is_(None)))
        plan = ctx.db.execute(q.order_by(DevVotePlan.id)).scalars().all()
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
        Ballot.session_id == session.id, Ballot.proposal_id == p.id,
        Ballot.vote_scope_id == item.vote_scope_id, Ballot.voter_id == user.id,
    )).first()
    if existing:
        raise Conflict("Bu oylamada oyunuzu zaten verdiniz; mühürlü oy değiştirilemez.")
    normalized = _normalize_choice(p, choice, ctx)
    salt = new_salt()
    doc = _ballot_doc(session.id, p.id, item.vote_scope_id, user.id, normalized)
    b = Ballot(session_id=session.id, proposal_id=p.id, vote_scope_id=item.vote_scope_id,
               voter_id=user.id, choice=normalized, salt=salt, commit=make_commit(doc, salt),
               created_at=ctx.now)
    ctx.db.add(b)
    ctx.db.flush()
    ledger.enqueue(ctx, "OY_MUHUR", {
        "oturum": session.id, "oneri": p.id, "kapsam": item.vote_scope_id,
        "secmen": user.nickname, "commit": b.commit,
    }, ref=b, ref_attr="commit_ledger_hash")
    return b


def _ballot_doc(session_id: int, proposal_id: int, scope_id: str, voter_id: str, choice: Any) -> dict:
    return {"oturum": session_id, "oneri": proposal_id, "kapsam": scope_id, "secmen": voter_id,
            "secim": choice}


def cast_vote(ctx: Ctx, user: User, proposal_id: int, choice: Any,
              vote_scope_id: str | None = None) -> Ballot:
    session = open_session_row(ctx)
    if session is None:
        raise Conflict("Şu anda açık bir Karar Saati penceresi yok.")
    if ctx.now >= session.closes_at:
        raise Conflict("Oy penceresi kapandı.")
    item = _item(ctx, session, proposal_id, vote_scope_id)
    b = _cast(ctx, session, item, proposals.get_proposal(ctx, proposal_id), user, choice)
    ctx.commit()
    return b


# --- kapanış ------------------------------------------------------------------------------------


def _reveal(ctx: Ctx, session: DecisionSession, p: Proposal, item: SessionItem) -> list[Ballot]:
    ballots = list(ctx.db.execute(select(Ballot).where(
        Ballot.session_id == session.id, Ballot.proposal_id == p.id,
        Ballot.vote_scope_id == item.vote_scope_id,
    ).order_by(Ballot.id)).scalars())
    names = nickname_map(ctx, [b.voter_id for b in ballots])
    for b in ballots:
        doc = _ballot_doc(session.id, p.id, b.vote_scope_id, b.voter_id, b.choice)
        ledger.enqueue(ctx, "OY_ACILDI", {
            "oturum": session.id, "oneri": p.id, "kapsam": b.vote_scope_id,
            "secmen": names.get(b.voter_id), "oy": doc, "tuz": b.salt, "commit": b.commit,
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


def _base_result(ctx: Ctx, item: SessionItem) -> dict[str, Any]:
    flagged_names = nickname_map(ctx, [f["user_id"] for f in item.flagged])
    return {
        "eligible": len(item.eligible),
        "flagged": [{"nickname": flagged_names.get(f["user_id"]), "reason": f["reason"]}
                    for f in item.flagged],
        "oracle": item.oracle_note,
        "vote_scope": {"id": item.vote_scope_id,
                       "name": ontology.scope_label(ctx, item.vote_scope_id)},
        "concurrent": item.concurrent,
    }


def _binary_result(ctx: Ctx, session: DecisionSession, item: SessionItem, p: Proposal,
                   reg: Regulation) -> dict[str, Any]:
    ballots = _reveal(ctx, session, p, item)
    votes = {b.voter_id: b.choice == YES for b in ballots}
    t = tally_binary(votes, item.resolved, set(item.eligible))
    key = proposals.threshold_key(p)
    passed = reg.ratio(key).passes(t.yes, t.cast)
    result = {
        **_base_result(ctx, item), "kind": "binary", "yes": t.yes, "no": t.no, "cast": t.cast,
        "abstained": len(t.abstained), "passed": passed,
        "threshold": {"key": key, "oran": reg.raw(key)["oran"],
                      "karsilastirma": reg.raw(key).get("karsilastirma", ">=")},
        "votes": _votes_view(ctx, item, ballots, t.weights),
    }
    result["note"] = (f"{t.yes}/{t.cast} ağırlıklı EVET ({_pct(t.yes, t.cast)}); eşik {key} "
                      f"{result['threshold']['karsilastirma']} {result['threshold']['oran']}.")
    return result


def _pct(yes: int, cast: int) -> str:
    return f"%{decimal_tr(100 * yes / cast)}" if cast else "oy yok"


def _pct_whole(yes: int, cast: int) -> str:
    """Özet satırı için tam sayı yüzde (yarım yukarı yuvarlanır): 7/8 → "%88"."""
    return f"%{(200 * yes + cast) // (2 * cast)}" if cast else "oy yok"


def _close_approval(ctx: Ctx, session: DecisionSession, item: SessionItem, p: Proposal) -> None:
    ballots = _reveal(ctx, session, p, item)
    texts = proposals.closure_texts(ctx, p)
    votes = {b.voter_id: set(b.choice) for b in ballots}
    t = tally_approval(votes, item.resolved, set(item.eligible), [ct.id for ct in texts])
    tn = nickname_map(ctx, [ct.author_id for ct in texts])
    result = {
        **_base_result(ctx, item), "kind": "approval", "winner": t.winner, "tie": t.tie,
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


def _close_proposal(ctx: Ctx, session: DecisionSession, p: Proposal, items: list[SessionItem],
                    reg: Regulation) -> None:
    """Önerinin bütün oylamalarını açar ve sayar; öneri ancak hepsinde çoğunluk alırsa geçer."""
    main = next(i for i in items if not i.concurrent)
    subs = [i for i in items if i.concurrent]
    if p.type == "KAPANIS":
        _close_approval(ctx, session, main, p)
    else:
        results = {it.id: _binary_result(ctx, session, it, p, reg) for it in [main, *subs]}
        passed = all(r["passed"] for r in results.values())
        summary = None
        if subs:
            parts = [f"{r['vote_scope']['name']}: {_pct_whole(r['yes'], r['cast'])} EVET "
                     f"{'✓' if r['passed'] else '✗'}" for r in results.values()]
            summary = " · ".join(parts) + (" → Kabul edildi" if passed else " → Reddedildi")
        for it in subs:
            it.result = results[it.id]
        main.result = {**results[main.id], "overall": {"passed": passed, "summary": summary}}
        note = summary or results[main.id]["note"]
        if passed:
            try:
                proposals.accept(ctx, p, note=note)
            except DomainError as exc:
                proposals.reject(ctx, p, f"Kabul edildi ama uygulanamadı: {exc.message}")
        else:
            proposals.reject(ctx, p, note)
    for it in items:
        ledger.enqueue(ctx, "OYLAMA_SONUCU", {
            "oturum": session.id, "oneri": p.id, "kapsam": it.vote_scope_id,
            "sonuc": {k: v for k, v in (it.result or {}).items() if k != "votes"},
        })


def close_session(ctx: Ctx, session: DecisionSession) -> None:
    if session.status != "OPEN":
        raise Conflict("Oturum zaten kapalı.")
    # Oturumun değişikliklerinden önce: oylamasız farkları deftere yaz ve son oylanmış hâle dön.
    regulation.restore_voted_state(ctx, session.id)
    reg = Regulation(session.regulation)
    groups: dict[int, list[SessionItem]] = {}
    for item in items_of(ctx, session):
        groups.setdefault(item.proposal_id, []).append(item)
    for pid, items in groups.items():
        _close_proposal(ctx, session, ctx.db.get(Proposal, pid), items, reg)
    session.status, session.closed_at = "CLOSED", ctx.now
    ledger.enqueue(ctx, "OTURUM_KAPANDI", {"oturum": session.id, "kapanis": ctx.now.isoformat()})
    # Oturumda kabul edilen değişikliklerden sonra yönetmeliğin tam hâli ve hash'i.
    regulation.record_state(ctx, session.id)
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
            "item_count": _proposal_count(items_of(ctx, current)),
        },
        "next_scheduled_at": next_occurrence(ctx.now, spec),
        "window_minutes": int(spec.window.total_seconds() // 60),
        "last_session": None if last is None else {"id": last.id, "closed_at": last.closed_at},
        "queued": [
            {"id": p.id, "type": p.type, "title": p.title,
             "effective_title": proposals.effective_title(p),
             "maturity": proposals.maturity(ctx, p)}
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
            Ballot.session_id == session.id, Ballot.proposal_id == p.id,
            Ballot.vote_scope_id == item.vote_scope_id, Ballot.voter_id == user.id,
        )).first() is not None
        entry: dict[str, Any] = {
            "proposal": proposals.summary(ctx, p, nickname_map(ctx, [p.proposer_id])),
            "vote_scope": {"id": item.vote_scope_id,
                           "name": ontology.scope_label(ctx, item.vote_scope_id)},
            "concurrent": item.concurrent,
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
             "item_count": _proposal_count(items_of(ctx, s))} for s in rows]


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
            "vote_scope": {"id": item.vote_scope_id,
                           "name": ontology.scope_label(ctx, item.vote_scope_id)},
            "concurrent": item.concurrent,
            "eligible_count": len(item.eligible),
            "sealed_votes": sum(1 for b in commits if b.proposal_id == p.id
                                and b.vote_scope_id == item.vote_scope_id),
            "result": result,
        })
    return {"id": s.id, "status": s.status, "opened_at": s.opened_at, "closes_at": s.closes_at,
            "closed_at": s.closed_at, "ledger_hash": s.ledger_hash, "items": items}


# --- şerh ---------------------------------------------------------------------------------------


def dissent_refusal(ctx: Ctx, d: Decision, user: User) -> Forbidden | Conflict | None:
    """Kullanıcı bu karara şerh ekleyemiyorsa nedenini (hata olarak) döner; ekleyebiliyorsa None."""
    losing = {ct.id: ct for ct in ctx.db.execute(select(ClosureText).where(
        ClosureText.proposal_id == d.proposal_id, ClosureText.id != d.closure_text_id
    )).scalars()}
    owns_losing = any(ct.author_id == user.id for ct in losing.values())
    p = ctx.db.get(Proposal, d.proposal_id)
    b = ctx.db.execute(select(Ballot).where(
        Ballot.session_id == p.session_id, Ballot.proposal_id == p.id,
        Ballot.vote_scope_id == p.scope_id, Ballot.voter_id == user.id,
    )).scalar_one_or_none() if p and p.session_id else None
    supported_losing = b is not None and bool(set(b.choice or []) & set(losing))
    if not (owns_losing or supported_losing):
        return Forbidden("Şerhi yalnızca kaybeden metinlerin sahipleri ya da destekçileri ekleyebilir.")
    if ctx.db.execute(select(Dissent.id).where(
        Dissent.decision_id == d.id, Dissent.author_id == user.id
    )).first():
        return Conflict("Bu karara zaten şerh düştünüz; şerh düzenlenemez.")
    return None


def add_dissent(ctx: Ctx, user: User, decision_id: int, text: str) -> Dissent:
    d = ctx.db.get(Decision, decision_id)
    if d is None:
        raise NotFound("Karar bulunamadı.")
    if (refusal := dissent_refusal(ctx, d, user)) is not None:
        raise refusal
    text = topics.check_square_text(text, max_len=5000)
    dissent = Dissent(decision_id=d.id, author_id=user.id, text=text, created_at=ctx.now)
    ctx.db.add(dissent)
    ctx.db.flush()
    ledger.enqueue(ctx, "SERH", {
        "karar": d.id, "yazar": user.nickname, "metin": text,
    }, ref=dissent)
    ctx.commit()
    return dissent
