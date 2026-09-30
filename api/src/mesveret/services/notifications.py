"""Site içi bildirimler: kişinin oy verdiği ya da açtığı önerilerin sonucu.

Bildirimler yalnızca sitedeki zilde görünür; e-posta ya da push yoktur. Üç tür:

- ``KARAR_SAATI``: oturum kapanınca, oturumda oy veren (doğrudan ya da havaleyle) ya da önerisi
  oylanan her yurttaşa tek bildirim; her öneri için sonuç ve kişinin oyu.
- ``SESSIZ_ONAY``: hızlı şeritteki öneri itiraz eşiği aşılmadan süresini doldurunca öneri sahibine.
- ``YAVAS_SERIT``: itiraz eşiği aşılıp öneri Karar Saati kuyruğuna geçince öneri sahibine.

Gizli oy yalnızca sahibine gösterilir. Havaleyle kullanılan oyda temsilcinin oyu zaten açıktır.
Bildirimler deftere yazılmaz: kişiye özeldir ve karar kaydı değildir.

Bu modül ``proposals``'ı içe aktarmaz; ``proposals`` bildirim üretmek için bunu çağırır.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, update

from mesveret.context import Ctx
from mesveret.db.models import Ballot, DecisionSession, Notification, Proposal, SessionItem, User
from mesveret.services import ontology
from mesveret.services.oracle import ORACLE_ID
from mesveret.services.profile import nickname_map

LIST_LIMIT = 50
OUTCOME = {
    "ACCEPTED": "kabul edildi",
    "REJECTED": "reddedildi",
    "CONFLICT": "kabul oyu aldı ama pay çakışması nedeniyle uygulanamadı",
}


def _add(ctx: Ctx, user_id: str, kind: str, title: str, lines: list[str], link: str) -> None:
    if user_id == ORACLE_ID:
        return
    ctx.db.add(Notification(user_id=user_id, kind=kind, title=title, lines=lines, link=link,
                            created_at=ctx.now))


def _label(p: Proposal) -> str:
    """Önerinin numarası ve başlığı; R2 daraltması varsa etkiyi anlatan başlık."""
    effect = [n["effect_title"] for n in p.narrowings or [] if n.get("effect_title")]
    return f"№{p.id} {' ve '.join(effect) if effect else p.title}"


def _choice(choice: Any) -> str:
    if isinstance(choice, list):  # kapanış: onaylanan metinler
        return f"{len(choice)} metne onay" if choice else "hiçbir metne onay yok"
    return str(choice)


# --- üretim --------------------------------------------------------------------------------------


def session_closed(ctx: Ctx, session: DecisionSession, items: list[SessionItem]) -> None:
    """Oturumun bütün sonuçları uygulandıktan sonra: kişi başına tek bildirim."""
    ballots = ctx.db.execute(select(Ballot).where(Ballot.session_id == session.id)).scalars()
    cast: dict[tuple[int, str], dict[str, Any]] = {}
    for b in ballots:
        cast.setdefault((b.proposal_id, b.vote_scope_id), {})[b.voter_id] = b.choice
    by_proposal: dict[int, list[SessionItem]] = {}
    for item in items:
        by_proposal.setdefault(item.proposal_id, []).append(item)
    delegates = {t for item in items for u, t in item.resolved.items() if u != t}
    names = nickname_map(ctx, sorted(delegates))

    # kişi → öneri → notlar ("oyunuz EVET", "oyunuz havaleyle ceren üzerinden: EVET")
    notes: dict[str, dict[int, list[str]]] = {}
    for pid, group in by_proposal.items():
        many = len(group) > 1
        for item in sorted(group, key=lambda i: i.concurrent):
            votes = cast.get((pid, item.vote_scope_id), {})
            where = f" ({ontology.scope_label(ctx, item.vote_scope_id)})" if many else ""
            for uid, choice in votes.items():
                notes.setdefault(uid, {}).setdefault(pid, []).append(
                    f"oyunuz {_choice(choice)}{where}")
            eligible = set(item.eligible)
            for uid, terminal in item.resolved.items():
                if uid != terminal and uid in eligible and terminal in votes:
                    notes.setdefault(uid, {}).setdefault(pid, []).append(
                        f"oyunuz havaleyle {names.get(terminal, terminal)} üzerinden: "
                        f"{_choice(votes[terminal])}{where}")

    props = {pid: ctx.db.get(Proposal, pid) for pid in by_proposal}
    for p in props.values():
        notes.setdefault(p.proposer_id, {}).setdefault(p.id, [])
    for uid in sorted(notes):
        lines = []
        for pid in sorted(notes[uid]):
            p = props[pid]
            parts = list(notes[uid][pid])
            if p.proposer_id == uid:
                parts.append("sizin öneriniz")
            lines.append(f"{_label(p)}: {OUTCOME.get(p.status, p.status)} · {'; '.join(parts)}")
        _add(ctx, uid, "KARAR_SAATI", f"Karar Saati #{session.id} sonuçlandı", lines,
             f"/karar-saati/{session.id}")
    ctx.db.flush()


def silent_period_ended(ctx: Ctx, p: Proposal) -> None:
    if p.status == "ACCEPTED":
        title = "Öneriniz kabul edildi"
        line = f"{_label(p)}: sessiz onay süresi itiraz eşiği aşılmadan doldu; öneri kabul edildi."
    elif p.status == "CONFLICT":
        title = "Öneriniz uygulanamadı"
        line = (f"{_label(p)}: sessiz onayla kabul edildi ama pay çakışması nedeniyle "
                "uygulanamadı.")
    else:
        return
    _add(ctx, p.proposer_id, "SESSIZ_ONAY", title, [line], f"/oneri/{p.id}")
    ctx.db.flush()


def moved_to_slow_lane(ctx: Ctx, p: Proposal, count: int, threshold: int) -> None:
    line = (f"{_label(p)}: itiraz eşiği aşıldı ({count}/{threshold}); öneri Karar Saati'nde "
            "oylanacak.")
    _add(ctx, p.proposer_id, "YAVAS_SERIT", "Önerinize itiraz edildi", [line], f"/oneri/{p.id}")
    ctx.db.flush()


# --- okuma ---------------------------------------------------------------------------------------


def unread_count(ctx: Ctx, user: User) -> int:
    return ctx.db.execute(select(func.count()).select_from(Notification).where(
        Notification.user_id == user.id, Notification.read_at.is_(None),
    )).scalar_one()


def list_for(ctx: Ctx, user: User) -> dict:
    rows = ctx.db.execute(
        select(Notification).where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc()).limit(LIST_LIMIT)
    ).scalars()
    return {
        "unread": unread_count(ctx, user),
        "items": [{"id": n.id, "kind": n.kind, "title": n.title, "lines": n.lines,
                   "link": n.link, "created_at": n.created_at, "read": n.read_at is not None}
                  for n in rows],
    }


def mark_read(ctx: Ctx, user: User, ids: list[int] | None = None) -> int:
    """Okundu işaretler (``ids`` yoksa hepsini); işaretlenen sayısını döner."""
    q = update(Notification).where(Notification.user_id == user.id,
                                   Notification.read_at.is_(None))
    if ids is not None:
        q = q.where(Notification.id.in_(ids))
    n = ctx.db.execute(q.values(read_at=ctx.now)).rowcount
    ctx.commit()
    return n
