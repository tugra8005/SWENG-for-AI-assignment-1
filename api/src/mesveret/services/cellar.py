"""Mahzen: anonim, geçici, isteğe bağlı diskur alanı.

- Yazar olarak yalnızca başlığa özel Gölge kimliği görünür (HMAC, ilk 8 karakter).
- Yeni yanıt başlığı yükseltir; kapasite aşılınca en alttaki başlık kalıcı silinir;
  üst sınıra ulaşan başlık yükselemez. Yaşayan başlıklar deftere yazılmaz.
- "Öneriye dönüştür" oylaması: süresiz, seçmenler oylama açılmadan önce yazmış olanlar,
  oylar gizli ve değiştirilebilir; EVET sayısı seçmen listesinin yarısını aştığı an ifşa.
"""

from __future__ import annotations

from sqlalchemy import delete, func, select

from mesveret.context import Ctx
from mesveret.db.models import CellarBallot, CellarPost, CellarThread, CellarVote, User
from mesveret.domain.cellar import (
    ThreadState,
    cellar_thread_refs,
    lifetime_remaining,
    post_refs,
    reveal_passes,
    should_bump,
    threads_to_prune,
)
from mesveret.domain.raid import detect_raids
from mesveret.domain.shade import shade_id
from mesveret.errors import Conflict, DomainError, Forbidden, NotFound
from mesveret.services import interactions, ledger, proposals
from mesveret.services.profile import nickname_map

WARNING = ("Bu başlık katılımcılarının oylamasıyla öneriye dönüştürülürse, burada yazan "
           "herkesin takma adı açığa çıkar.")
MAX_POST = 5000
PREVIEW = 240


class WarningRequired(Conflict):
    pass


# --- yardımcılar --------------------------------------------------------------------------------


def _shade(ctx: Ctx, user_id: str, thread_id: int) -> str:
    return shade_id(ctx.settings.shade_key.encode(), user_id, str(thread_id))


def _thread(ctx: Ctx, thread_id: int) -> CellarThread:
    t = ctx.db.get(CellarThread, thread_id)
    if t is None:
        raise NotFound("Bu başlık yok ya da Mahzen'in dibine düşüp silindi.")
    return t


def _posts(ctx: Ctx, thread_id: int) -> list[CellarPost]:
    return list(ctx.db.execute(
        select(CellarPost).where(CellarPost.thread_id == thread_id).order_by(CellarPost.id)
    ).scalars())


def _open_vote(ctx: Ctx, thread_id: int) -> CellarVote | None:
    return ctx.db.execute(select(CellarVote).where(
        CellarVote.thread_id == thread_id, CellarVote.status == "OPEN"
    )).scalar_one_or_none()


def _is_poster(ctx: Ctx, thread_id: int, user_id: str) -> bool:
    return ctx.db.execute(select(CellarPost.id).where(
        CellarPost.thread_id == thread_id, CellarPost.author_id == user_id
    ).limit(1)).first() is not None


def _require_entry(user: User) -> None:
    if user.cellar_warned_at is None:
        raise WarningRequired(f"Mahzen'e girmeden önce uyarıyı onaylayın. {WARNING}")


def _check_text(ctx: Ctx, text: str, thread_id: int | None) -> str:
    text = text.strip()
    if not text:
        raise DomainError("Metin boş olamaz.")
    if len(text) > MAX_POST:
        raise DomainError(f"Metin en fazla {MAX_POST} karakter olabilir.")
    if cellar_thread_refs(text) - ({thread_id} if thread_id else set()):
        raise DomainError("Başka Mahzen başlıklarına referans verilemez.")
    refs = post_refs(text)
    if refs:
        if thread_id is None:
            raise DomainError("Başka başlıklardaki mesajlara referans verilemez.")
        own = set(ctx.db.execute(select(CellarPost.id).where(
            CellarPost.thread_id == thread_id, CellarPost.id.in_(refs)
        )).scalars())
        if refs - own:
            raise DomainError("Başka başlıklardaki mesajlara referans verilemez.")
    return text


def _living(ctx: Ctx) -> list[CellarThread]:
    return list(ctx.db.execute(
        select(CellarThread).where(CellarThread.frozen.is_(False))
        .order_by(CellarThread.bumped_at.desc(), CellarThread.id.desc())
    ).scalars())


def _prune(ctx: Ctx) -> list[int]:
    states = [ThreadState(t.id, t.bumped_at, t.frozen) for t in _living(ctx)]
    doomed = threads_to_prune(states, ctx.reg.integer("mahzen_kapasite"))
    for tid in doomed:
        ctx.db.execute(delete(CellarThread).where(CellarThread.id == tid))
        ctx.graph.remove_discourse(tid)
    return doomed


def _add_post(ctx: Ctx, t: CellarThread, user: User, text: str) -> CellarPost:
    firsts = dict(ctx.db.execute(
        select(CellarPost.author_id, func.min(CellarPost.created_at))
        .where(CellarPost.thread_id == t.id).group_by(CellarPost.author_id)
    ).all())
    post = CellarPost(thread_id=t.id, author_id=user.id, text=text, created_at=ctx.now)
    ctx.db.add(post)
    ctx.db.flush()
    if user.id not in firsts:
        ctx.graph.add_discourse_author(t.id, user.id, ctx.now)
        interactions.on_first_participation(ctx, user.id, firsts)
    refs = post_refs(text)
    if refs:
        for author in ctx.db.execute(
            select(CellarPost.author_id).where(CellarPost.id.in_(refs))
        ).scalars():
            interactions.on_reply(ctx, user.id, author)
    return post


# --- giriş --------------------------------------------------------------------------------------


def entry_status(user: User) -> dict:
    return {"needs_warning": user.cellar_warned_at is None, "warning": WARNING}


def acknowledge_entry(ctx: Ctx, user: User) -> None:
    if user.cellar_warned_at is None:
        user.cellar_warned_at = ctx.now
    ctx.commit()


# --- başlıklar ve yanıtlar ------------------------------------------------------------------------


def create_thread(ctx: Ctx, user: User, title: str, text: str, *, acknowledge: bool) -> CellarThread:
    _require_entry(user)
    if not acknowledge:
        raise WarningRequired(WARNING)
    title = title.strip()
    if not 3 <= len(title) <= 120:
        raise DomainError("Başlık 3–120 karakter olmalı.")
    text = _check_text(ctx, text, None)
    t = CellarThread(title=title, creator_id=user.id, created_at=ctx.now, bumped_at=ctx.now,
                     reply_count=0)
    ctx.db.add(t)
    ctx.db.flush()
    _add_post(ctx, t, user, text)
    _prune(ctx)
    ctx.commit()
    return t


def reply(ctx: Ctx, user: User, thread_id: int, text: str, *, acknowledge: bool) -> CellarPost:
    _require_entry(user)
    t = _thread(ctx, thread_id)
    if t.frozen:
        raise Conflict("Bu başlık ifşa edildi ve donduruldu.")
    if not _is_poster(ctx, t.id, user.id) and not acknowledge:
        raise WarningRequired(WARNING)
    text = _check_text(ctx, text, t.id)
    post = _add_post(ctx, t, user, text)
    if should_bump(t.reply_count, ctx.reg.integer("mahzen_ust_sinir")):
        t.bumped_at = ctx.now
    t.reply_count += 1
    ctx.commit()
    return post


def sign_post(ctx: Ctx, user: User, post_id: int) -> None:
    post = ctx.db.get(CellarPost, post_id)
    if post is None:
        raise NotFound("Mesaj bulunamadı.")
    if post.author_id != user.id:
        raise Forbidden("Yalnızca kendi mesajınızı imzalayabilirsiniz.")
    if post.signed:
        raise Conflict("Bu mesaj zaten imzalı.")
    if _thread(ctx, post.thread_id).frozen:
        raise Conflict("Başlık ifşa edildi; tüm takma adlar zaten açık.")
    post.signed = True
    ctx.commit()


# --- ifşa oylaması ------------------------------------------------------------------------------


def open_reveal_vote(ctx: Ctx, user: User, thread_id: int) -> CellarVote:
    t = _thread(ctx, thread_id)
    if t.frozen:
        raise Conflict("Başlık zaten ifşa edildi.")
    if not _is_poster(ctx, t.id, user.id):
        raise Forbidden("Bu başlıkta yazmamış biri başlık üzerinde işlem yapamaz.")
    if _open_vote(ctx, t.id) is not None:
        raise Conflict("Bu başlıkta zaten açık bir oylama var.")
    authors = sorted(set(ctx.db.execute(
        select(CellarPost.author_id).where(CellarPost.thread_id == t.id)
    ).scalars()))
    # Başlığa katılım herkes için yenidir; baskın tespitinde hesabın açılış anı kullanılır.
    created = dict(ctx.db.execute(select(User.id, User.created_at).where(User.id.in_(authors))).all())
    clusters = detect_raids(created, ctx.graph.interactions_among(authors), ctx.now, ctx.reg)
    flagged = [{"user_id": u, "reason": c.reason} for c in clusters for u in sorted(c.members)]
    flagged_ids = {f["user_id"] for f in flagged}
    vote = CellarVote(thread_id=t.id, opened_by=user.id, opened_at=ctx.now,
                      electorate=[u for u in authors if u not in flagged_ids], flagged=flagged,
                      status="OPEN")
    ctx.db.add(vote)
    ctx.commit()
    return vote


def cast_reveal_vote(ctx: Ctx, user: User, thread_id: int, yes: bool) -> dict:
    t = _thread(ctx, thread_id)
    vote = _open_vote(ctx, t.id)
    if vote is None:
        raise Conflict("Bu başlıkta açık bir oylama yok.")
    flagged = {f["user_id"]: f["reason"] for f in vote.flagged}
    if user.id in flagged:
        raise Forbidden(f"Bu oylamada baskın şüphesiyle dışlandınız. {flagged[user.id]}")
    if user.id not in vote.electorate:
        raise Forbidden("Yalnızca oylama açılmadan önce bu başlıkta yazmış olanlar oy verebilir.")
    ballot = ctx.db.execute(select(CellarBallot).where(
        CellarBallot.vote_id == vote.id, CellarBallot.user_id == user.id
    )).scalar_one_or_none()
    if ballot is None:
        ctx.db.add(CellarBallot(vote_id=vote.id, user_id=user.id, yes=yes, updated_at=ctx.now))
    else:
        ballot.yes, ballot.updated_at = yes, ctx.now
    ctx.db.flush()
    yes_count = ctx.db.execute(select(func.count()).select_from(CellarBallot).where(
        CellarBallot.vote_id == vote.id, CellarBallot.yes.is_(True)
    )).scalar_one()
    revealed = reveal_passes(yes_count, len(vote.electorate), ctx.reg.ratio("mahzen_ifsa_esigi"))
    if revealed:
        _reveal(ctx, t, vote, yes_count)
    ctx.commit()
    return {"revealed": revealed}


def _reveal(ctx: Ctx, t: CellarThread, vote: CellarVote, yes_count: int) -> None:
    vote.status, vote.passed_at = "PASSED", ctx.now
    t.frozen, t.revealed_at = True, ctx.now
    posts = _posts(ctx, t.id)
    names = nickname_map(ctx, [p.author_id for p in posts])
    ledger.enqueue(ctx, "MAHZEN_IFSA", {
        "baslik": t.id, "baslik_adi": t.title,
        "mesajlar": [
            {"no": p.id, "golge": _shade(ctx, p.author_id, t.id), "takma_ad": names.get(p.author_id),
             "metin": p.text, "zaman": p.created_at.isoformat(), "imzali": p.signed}
            for p in posts
        ],
        "oylama": {"evet": yes_count, "secmen": len(vote.electorate),
                   "dislanan": len(vote.flagged)},
    }, ref=t)
    first = posts[0].text if posts else ""
    draft = proposals.create_draft(
        ctx, vote.opened_by, t.title,
        f"{first}\n\n— Mahzen başlığı #{t.id} katılımcılarının oylamasıyla öneriye dönüştürüldü.",
        {"cellar_thread_id": t.id},
    )
    t.draft_proposal_id = draft.id


# --- görünümler ---------------------------------------------------------------------------------


def list_threads(ctx: Ctx, viewer: User | None) -> dict:
    capacity = ctx.reg.integer("mahzen_kapasite")
    limit = ctx.reg.integer("mahzen_ust_sinir")
    threads = _living(ctx)
    firsts = {}
    if threads:
        rows = ctx.db.execute(
            select(CellarPost).where(CellarPost.thread_id.in_([t.id for t in threads]))
            .order_by(CellarPost.id)
        ).scalars()
        for p in rows:
            firsts.setdefault(p.thread_id, p)
    open_votes = set(ctx.db.execute(
        select(CellarVote.thread_id).where(CellarVote.status == "OPEN")
    ).scalars())
    out = []
    for rank, t in enumerate(threads):
        op = firsts.get(t.id)
        out.append({
            "id": t.id, "title": t.title, "created_at": t.created_at, "bumped_at": t.bumped_at,
            "reply_count": t.reply_count, "rank": rank,
            "lifetime": lifetime_remaining(rank, capacity),
            "bump_locked": t.reply_count >= limit, "has_vote": t.id in open_votes,
            "op_shade": _shade(ctx, op.author_id, t.id) if op else None,
            "op_preview": (op.text[:PREVIEW] if op else ""),
        })
    return {"capacity": capacity, "bump_limit": limit, "threads": out}


def thread_view(ctx: Ctx, thread_id: int, viewer: User | None) -> dict:
    t = _thread(ctx, thread_id)
    posts = _posts(ctx, t.id)
    names = nickname_map(ctx, [p.author_id for p in posts])
    living = _living(ctx)
    rank = next((i for i, x in enumerate(living) if x.id == t.id), None)
    capacity = ctx.reg.integer("mahzen_kapasite")
    body = {
        "id": t.id, "title": t.title, "created_at": t.created_at, "bumped_at": t.bumped_at,
        "reply_count": t.reply_count, "frozen": t.frozen,
        "rank": rank, "lifetime": lifetime_remaining(rank, capacity) if rank is not None else None,
        "bump_locked": t.reply_count >= ctx.reg.integer("mahzen_ust_sinir"),
        "posts": [
            {
                "no": p.id, "shade": _shade(ctx, p.author_id, t.id), "text": p.text,
                "created_at": p.created_at, "signed": p.signed,
                "nickname": names.get(p.author_id) if (p.signed or t.frozen) else None,
                "is_mine": viewer is not None and p.author_id == viewer.id,
            }
            for p in posts
        ],
        "revealed": None if not t.frozen else {
            "at": t.revealed_at, "draft_proposal_id": t.draft_proposal_id,
            "ledger_hash": t.ledger_hash,
        },
        "warning": WARNING,
    }
    vote = ctx.db.execute(
        select(CellarVote).where(CellarVote.thread_id == t.id).order_by(CellarVote.id.desc())
    ).scalars().first()
    vote_view = None
    if vote is not None:
        ratio = ctx.reg.ratio("mahzen_ifsa_esigi")
        needed = next(n for n in range(len(vote.electorate) + 2)
                      if reveal_passes(n, len(vote.electorate), ratio)) if vote.electorate else None
        vote_view = {"status": vote.status, "opened_at": vote.opened_at,
                     "electorate_size": len(vote.electorate), "needed_yes": needed,
                     "flagged_count": len(vote.flagged)}
        if viewer is not None:
            mine = ctx.db.execute(select(CellarBallot.yes).where(
                CellarBallot.vote_id == vote.id, CellarBallot.user_id == viewer.id
            )).scalar_one_or_none()
            flagged = {f["user_id"]: f["reason"] for f in vote.flagged}
            vote_view.update({
                "i_am_voter": viewer.id in vote.electorate, "my_vote": mine,
                "flagged_self": flagged.get(viewer.id),
            })
    body["vote"] = vote_view
    if viewer is not None:
        body["viewer"] = {
            "is_poster": _is_poster(ctx, t.id, viewer.id),
            "needs_thread_warning": not _is_poster(ctx, t.id, viewer.id),
        }
    return body


def revealed_thread(ctx: Ctx, thread_id: int) -> dict:
    """Meydan'dan bağlantıyla okunan ifşa edilmiş başlık (yalnızca donmuş başlıklar)."""
    t = _thread(ctx, thread_id)
    if not t.frozen:
        raise NotFound("Bu başlık ifşa edilmedi.")
    return thread_view(ctx, thread_id, None)

