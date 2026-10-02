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

from mesveret import clock
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
from mesveret.domain.commit import derived_salt, make_commit, new_salt, verify_commit
from mesveret.domain.decision_hour import next_occurrence
from mesveret.domain.delegation import resolve_all
from mesveret.domain.oracle import label_check, oracle_vote
from mesveret.domain.raid import detect_raids
from mesveret.domain.regulation import Regulation
from mesveret.domain.shade import vote_pseudonym
from mesveret.domain.tally import tally_approval, tally_binary
from mesveret.domain.text import locative_name, percent_tr
from mesveret.errors import Conflict, DomainError, Forbidden, NotFound
from mesveret.services import ledger, notifications, ontology, proposals, regulation, topics
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
    resolved = resolve_all(delegations, p.area_id, ctx.graph, eligible)
    carried: dict[str, int] = {}
    for e in eligible:
        carried[resolved.get(e, e)] = carried.get(resolved.get(e, e), 0) + 1
    item = SessionItem(
        session_id=session.id, proposal_id=p.id, vote_scope_id=scope, concurrent=concurrent,
        area_id=p.area_id, eligible=eligible, resolved=resolved, flagged=flagged,
        open_voters=sorted(u for u in eligible if carried.get(u, 0) > 1 or u == ORACLE_ID),
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
    reason = "R1–R9 geçti; etiketler uyumlu."
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
    session = DecisionSession(
        scheduled_for=scheduled_for, opened_at=ctx.now, closes_at=ctx.now,
        status="OPEN", regulation={}, scripted=scripted,
    )
    ctx.db.add(session)
    ctx.db.flush()
    # Anlık görüntülerden (pencere uzunluğu, yönetmelik değerleri, seçmenler, havaleler) önce:
    # oylamasız farkları deftere yaz ve son oylanmış hâle dön. Oturum oylamasız değerle açılmaz.
    regulation.restore_voted_state(ctx, session.id, stage="acilis")
    session.closes_at = ctx.now + ctx.reg.decision_hour().window
    session.regulation = ctx.graph.articles()
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
    # Baskın şüphesiyle dışlananlar deftere isimle değil sayıyla yazılır: yanlış pozitifler
    # herkese teşhir edilmez.
    ledger.enqueue(ctx, "OTURUM_ACILDI", {
        "oturum": session.id, "acilis": ctx.now.isoformat(),
        "kapanis": session.closes_at.isoformat(), "oneriler": [p.id for p in queued],
        "secmen_sayilari": {_item_key(p, it): len(it.eligible) for p, it in items},
        "acik_oy_sayilari": {_item_key(p, it): len(it.open_voters) for p, it in items},
        "eszamanli_oylamalar": concurrent,
        "baskin_isaretli_sayisi": {_item_key(p, it): len(it.flagged)
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
    # Geliştirme ortamında tuz türetilir: demo ve tohum iki çalıştırmada aynı defteri üretir.
    salt = (derived_salt(ctx.settings.shade_key.encode(), session.id, p.id, item.vote_scope_id,
                         user.id) if ctx.settings.is_dev else new_salt())
    ref = _voter_ref(ctx, item, session.id, user.id, {user.id: user.nickname})
    doc = _ballot_doc(session.id, p.id, item.vote_scope_id, ref, normalized)
    b = Ballot(session_id=session.id, proposal_id=p.id, vote_scope_id=item.vote_scope_id,
               voter_id=user.id, choice=normalized, salt=salt, commit=make_commit(doc, salt),
               created_at=ctx.now)
    ctx.db.add(b)
    ctx.db.flush()
    # Gizli oy deftere kimlikle değil oturuma özel takma kimlikle yazılır; çift oy engeli sunucuda.
    ledger.enqueue(ctx, "OY_MUHUR", {
        "oturum": session.id, "oneri": p.id, "kapsam": item.vote_scope_id,
        "secmen": ref, "acik": is_open_vote(item, user.id), "commit": b.commit,
    }, ref=b, ref_attr="commit_ledger_hash")
    return b


def _ballot_doc(session_id: int, proposal_id: int, scope_id: str, voter_ref: str, choice: Any) -> dict:
    """Commit'in üzerine kurulduğu belge. ``voter_ref`` açık oyda takma ad, gizli oyda oturuma
    özel takma kimliktir; belge açılışta deftere yazıldığı için kimlik bilgisi taşımaz."""
    return {"oturum": session_id, "oneri": proposal_id, "kapsam": scope_id, "secmen": voter_ref,
            "secim": choice}


def pseudonym(ctx: Ctx, user_id: str, session_id: int) -> str:
    return vote_pseudonym(ctx.settings.shade_key.encode(), user_id, session_id)


def is_open_vote(item: SessionItem, user_id: str) -> bool:
    return user_id in (item.open_voters or [])


def _voter_ref(ctx: Ctx, item: SessionItem, session_id: int, user_id: str,
               names: dict[str, str] | None = None) -> str:
    if is_open_vote(item, user_id):
        return (names or nickname_map(ctx, [user_id])).get(user_id, user_id)
    return pseudonym(ctx, user_id, session_id)


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
    names = nickname_map(ctx, [b.voter_id for b in ballots if is_open_vote(item, b.voter_id)])
    for b in ballots:
        ref = _voter_ref(ctx, item, session.id, b.voter_id, names)
        doc = _ballot_doc(session.id, p.id, b.vote_scope_id, ref, b.choice)
        ledger.enqueue(ctx, "OY_ACILDI", {
            "oturum": session.id, "oneri": p.id, "kapsam": b.vote_scope_id,
            "secmen": ref, "acik": is_open_vote(item, b.voter_id), "oy": doc, "tuz": b.salt,
            "commit": b.commit,
        }, ref=b, ref_attr="reveal_ledger_hash")
    return ballots


def _votes_view(ctx: Ctx, item: SessionItem, ballots: list[Ballot], weights: dict) -> list[dict]:
    """Sonuçta saklanan oylar. Açık oy (temsilci, Hâtif) takma ad, ağırlık ve havale edenlerle;
    gizli oy yalnızca oturuma özel takma kimlik, oy ve ağırlıkla. Gizli oyda kimlik bilgisi yok."""
    delegators: dict[str, list[str]] = {}
    for u, t in item.resolved.items():
        if u != t:
            delegators.setdefault(t, []).append(u)
    public = [b.voter_id for b in ballots if is_open_vote(item, b.voter_id)]
    names = nickname_map(ctx, public + [u for v in public for u in delegators.get(v, [])])
    out = []
    for b in ballots:
        if is_open_vote(item, b.voter_id):
            out.append({
                "ballot_id": b.id, "open": True, "voter": names.get(b.voter_id),
                "choice": b.choice, "weight": weights.get(b.voter_id, 0),
                "delegators": sorted(names.get(u, u) for u in delegators.get(b.voter_id, [])
                                     if u in item.eligible),
            })
        else:
            out.append({
                "ballot_id": b.id, "open": False,
                "pseudonym": pseudonym(ctx, b.voter_id, b.session_id),
                "choice": b.choice, "weight": weights.get(b.voter_id, 0),
            })
    return out


def _base_result(ctx: Ctx, item: SessionItem) -> dict[str, Any]:
    # Baskın şüphesiyle dışlananlar isimle listelenmez; yalnızca sayı ve gerekçe (kişi adı içermez).
    return {
        "eligible": len(item.eligible),
        "flagged_count": len(item.flagged),
        "flagged_reasons": list(dict.fromkeys(f["reason"] for f in item.flagged)),
        "open_count": len(item.open_voters or []),
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
    return percent_tr(100 * yes / cast) if cast else "oy yok"


def _pct_whole(yes: int, cast: int) -> str:
    """Özet satırı için tam sayı yüzde (yarım yukarı yuvarlanır): 7/8 → "%88"."""
    return percent_tr((200 * yes + cast) // (2 * cast), 0) if cast else "oy yok"


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
            # "Genel'de geçti (%64) · İstanbul'da geçemedi (%22) → Reddedildi"
            parts = [f"{locative_name(r['vote_scope']['name'])} "
                     f"{'geçti' if r['passed'] else 'geçemedi'} ({_pct_whole(r['yes'], r['cast'])})"
                     for r in results.values()]
            summary = " · ".join(parts) + (" → Kabul edildi" if passed else " → Reddedildi")
        for it in subs:
            it.result = results[it.id]
        overall: dict[str, Any] = {"passed": passed, "summary": summary}
        note = summary or results[main.id]["note"]
        if passed:
            try:
                conflicts = proposals.accept_or_conflict(ctx, p, note=note)
            except DomainError as exc:
                conflicts = []
                proposals.reject(ctx, p, f"Kabul edildi ama uygulanamadı: {exc.message}")
            if conflicts:
                # Öneriler numara sırasıyla uygulanır; önce uygulanan öneri aynı kaynağın paylarını
                # değiştirdiyse bu önerinin hedefleri geçersizdir.
                overall["conflict"] = {"note": p.outcome_note,
                                       "by": [c["by"] for c in conflicts if c["by"]]}
        else:
            proposals.reject(ctx, p, note)
        main.result = {**results[main.id], "overall": overall}
    for it in items:
        ledger.enqueue(ctx, "OYLAMA_SONUCU", {
            "oturum": session.id, "oneri": p.id, "kapsam": it.vote_scope_id,
            "sonuc": {k: v for k, v in (it.result or {}).items() if k != "votes"},
        })


def close_session(ctx: Ctx, session: DecisionSession) -> None:
    if session.status != "OPEN":
        raise Conflict("Oturum zaten kapalı.")
    # Oturumun değişikliklerinden önce: oylamasız farkları deftere yaz ve son oylanmış hâle dön.
    regulation.restore_voted_state(ctx, session.id, stage="kapanis")
    reg = Regulation(session.regulation)
    groups: dict[int, list[SessionItem]] = {}
    all_items = items_of(ctx, session)
    for item in all_items:
        groups.setdefault(item.proposal_id, []).append(item)
    for pid, items in groups.items():
        _close_proposal(ctx, session, ctx.db.get(Proposal, pid), items, reg)
    session.status, session.closed_at = "CLOSED", ctx.now
    # Oy verenlere ve öneri sahiplerine sonuç bildirimi (site içi zil).
    notifications.session_closed(ctx, session, all_items)
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
                       lambda c, sid=sid: _close_scheduled(c, sid)))
    if last is not None:
        occ = next_occurrence(last, ctx.reg.decision_hour())
        if occ <= until:
            events.append((occ, "haftalık Karar Saati açıldı",
                           lambda c, occ=occ: _open_scheduled(c, occ)))
    return events


def _close_scheduled(ctx: Ctx, session_id: int) -> None:
    """Zamanlanmış kapanış idempotenttir: oturum zaten kapandıysa hiçbir şey yazmaz."""
    session = get_session(ctx, session_id)
    if session.status == "OPEN":
        close_session(ctx, session)


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
        # Demo modunda saat durur; istemci de bu anda durur (geri sayımlar akmaz).
        "frozen": clock.is_frozen(ctx.db),
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


def shared_resource_notes(ctx: Ctx, session: DecisionSession) -> dict[int, list[str]]:
    """Aynı bölünebilir kaynağın paylarına dokunan öneriler kapanışta numara sırasıyla uygulanır;
    önce uygulanan kabul edilirse sonrakinin pay hedefleri geçersiz olur."""
    touched: dict[int, set[str]] = {}
    for item in items_of(ctx, session):
        if not item.concurrent:
            p = ctx.db.get(Proposal, item.proposal_id)
            if rids := set(p.payload.get("share_base") or {}):
                touched[p.id] = rids
    notes: dict[int, list[str]] = {}
    for pid, rids in touched.items():
        for other in sorted(touched):
            if other == pid or not rids & touched[other]:
                continue
            notes.setdefault(pid, []).append(
                f"№{other} ile aynı kaynağı etkiliyor; önce №{other} uygulanır." if other < pid
                else f"№{other} ile aynı kaynağı etkiliyor; önce bu öneri uygulanır, kabul "
                     f"edilirse №{other} uygulanamaz.")
    return notes


def ballot(ctx: Ctx, user: User) -> dict:
    session = open_session_row(ctx)
    if session is None:
        return {"session": None, "items": []}
    shared = shared_resource_notes(ctx, session)
    out = []
    for item in items_of(ctx, session):
        p = ctx.db.get(Proposal, item.proposal_id)
        flagged = {f["user_id"]: f["reason"] for f in item.flagged}
        terminal = item.resolved.get(user.id)
        mine = ctx.db.execute(select(Ballot).where(
            Ballot.session_id == session.id, Ballot.proposal_id == p.id,
            Ballot.vote_scope_id == item.vote_scope_id, Ballot.voter_id == user.id,
        )).scalar_one_or_none()
        voted = mine is not None
        weight = sum(1 for e in item.eligible if item.resolved.get(e) == user.id)
        open_vote = is_open_vote(item, user.id)
        entry: dict[str, Any] = {
            "proposal": proposals.summary(ctx, p, nickname_map(ctx, [p.proposer_id])),
            "vote_scope": {"id": item.vote_scope_id,
                           "name": ontology.scope_label(ctx, item.vote_scope_id)},
            "concurrent": item.concurrent,
            "kind": "approval" if p.type == "KAPANIS" else "binary",
            "voted": voted,
            "eligible": user.id in item.eligible or user.id in flagged,
            "my_choice": mine.choice if mine is not None else None,
            "weight": weight,
            "open_vote": open_vote,
            "secrecy_note": (
                f"Oyunuz açık olacak: {weight - 1} yurttaşın oyunu taşıyorsunuz." if open_vote
                else "Oyunuz gizli: sonuçta yalnızca toplamlar görünür."),
            "narrowings": p.narrowings,
            "shared_resource_notes": shared.get(p.id, []),
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


def my_votes(ctx: Ctx, user: User, session_id: int | None = None) -> dict:
    """"Oyumu doğrula": kullanıcının kendi oyları, yalnızca kendisine. Gizli oyda o oturumdaki
    takma kimlik; mühür ve açılış kayıtlarının defterdeki hash'leri; commit yeniden hesaplanır.
    Baskın şüphesiyle dışlandığı oylamalar da (yalnızca kendisine) listelenir."""
    q = select(Ballot).where(Ballot.voter_id == user.id).order_by(Ballot.id)
    if session_id is not None:
        q = q.where(Ballot.session_id == session_id)
    out = []
    for b in ctx.db.execute(q).scalars():
        s = ctx.db.get(DecisionSession, b.session_id)
        item = _item(ctx, s, b.proposal_id, b.vote_scope_id)
        p = ctx.db.get(Proposal, b.proposal_id)
        ref = _voter_ref(ctx, item, s.id, user.id, {user.id: user.nickname})
        closed = s.status == "CLOSED"
        out.append({
            "session_id": s.id, "proposal_id": p.id, "title": p.title, "type": p.type,
            "vote_scope": {"id": item.vote_scope_id,
                           "name": ontology.scope_label(ctx, item.vote_scope_id)},
            "open": is_open_vote(item, user.id),
            "pseudonym": None if is_open_vote(item, user.id) else ref,
            "choice": b.choice, "commit": b.commit,
            "salt": b.salt if closed else None,  # tuz pencere kapanınca defterde açılır
            "commit_ledger_hash": b.commit_ledger_hash,
            "reveal_ledger_hash": b.reveal_ledger_hash,
            "verified": verify_commit(b.commit,
                                      _ballot_doc(s.id, p.id, b.vote_scope_id, ref, b.choice),
                                      b.salt),
        })
    excluded = []
    sessions = ([ctx.db.get(DecisionSession, session_id)] if session_id is not None else
                ctx.db.execute(select(DecisionSession).order_by(DecisionSession.id)).scalars())
    for s in sessions:
        if s is None:
            continue
        for item in items_of(ctx, s):
            reason = next((f["reason"] for f in item.flagged if f["user_id"] == user.id), None)
            if reason:
                p = ctx.db.get(Proposal, item.proposal_id)
                excluded.append({"session_id": s.id, "proposal_id": p.id, "title": p.title,
                                 "reason": reason})
    return {"votes": out, "excluded": excluded}


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
    shared = shared_resource_notes(ctx, s)
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
            "shared_resource_notes": shared.get(p.id, []),
            "result": result,
        })
    return {"id": s.id, "status": s.status, "opened_at": s.opened_at, "closes_at": s.closes_at,
            "closed_at": s.closed_at, "ledger_hash": s.ledger_hash, "items": items}


# --- şerh ---------------------------------------------------------------------------------------


def dissent_options(ctx: Ctx, d: Decision, user: User) -> list[ClosureText]:
    """Kullanıcının şerhini dayandırabileceği kaybeden metinler: sahibi olduğu ya da onay verdiği."""
    losing = ctx.db.execute(select(ClosureText).where(
        ClosureText.proposal_id == d.proposal_id, ClosureText.id != d.closure_text_id
    ).order_by(ClosureText.id)).scalars().all()
    p = ctx.db.get(Proposal, d.proposal_id)
    b = ctx.db.execute(select(Ballot).where(
        Ballot.session_id == p.session_id, Ballot.proposal_id == p.id,
        Ballot.vote_scope_id == p.scope_id, Ballot.voter_id == user.id,
    )).scalar_one_or_none() if p and p.session_id else None
    approved = set(b.choice or []) if b is not None else set()
    return [ct for ct in losing if ct.author_id == user.id or ct.id in approved]


def dissent_refusal(ctx: Ctx, d: Decision, user: User) -> Forbidden | Conflict | None:
    """Kullanıcı bu karara şerh ekleyemiyorsa nedenini (hata olarak) döner; ekleyebiliyorsa None."""
    if not dissent_options(ctx, d, user):
        return Forbidden("Şerhi yalnızca kaybeden metinlerin sahipleri ya da destekçileri ekleyebilir.")
    if ctx.db.execute(select(Dissent.id).where(
        Dissent.decision_id == d.id, Dissent.author_id == user.id
    )).first():
        return Conflict("Bu karara zaten şerh düştünüz; şerh düzenlenemez.")
    return None


def add_dissent(ctx: Ctx, user: User, decision_id: int, text: str,
                closure_text_id: int | None = None) -> Dissent:
    d = ctx.db.get(Decision, decision_id)
    if d is None:
        raise NotFound("Karar bulunamadı.")
    if (refusal := dissent_refusal(ctx, d, user)) is not None:
        raise refusal
    options = {ct.id: ct for ct in dissent_options(ctx, d, user)}
    if closure_text_id is None and len(options) == 1:
        closure_text_id = next(iter(options))
    if closure_text_id not in options:
        raise DomainError("Şerhin dayandığı kaybeden metni seçin (sahibi olduğunuz ya da onay "
                          "verdiğiniz metinlerden biri).")
    text = topics.check_square_text(text, max_len=5000)
    dissent = Dissent(decision_id=d.id, author_id=user.id, closure_text_id=closure_text_id,
                      text=text, created_at=ctx.now)
    ctx.db.add(dissent)
    ctx.db.flush()
    basis = options[closure_text_id]
    ledger.enqueue(ctx, "SERH", {
        "karar": d.id, "yazar": user.nickname, "metin": text,
        "dayandigi_metin": {"id": basis.id, "metin": basis.text},
    }, ref=dissent)
    ctx.commit()
    return dissent
