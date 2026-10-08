"""Meşveret Takvimi: takvime giden konunun etkinliği, "Geliyorum" ve etkinlik raporu.

Muhatabı takvim olan KONU/ALT_KONU önerisi bir etkinlik bildirebilir: başlangıç, süre ve yer
(ortak toplantı salonu, bir adres ya da çevrim içi). Ortak salon bir kaynaktır; öneri onu
ETKILER etiketiyle taşır, bu yüzden salon hakkında yalnızca sahibi (Genel) karar verir (R2).
Salonda saatleri kesişen planlı bir etkinlik varsa öneri açılışta reddedilir.

Konu kabul edilince (``events.TopicAccepted``) etkinlik planlanır ve deftere yazılır
(``ETKINLIK_PLANLANDI``). Etkinlik bitince "Geliyorum" diyenler kısa bir rapor ve fotoğraf ekler
(``ETKINLIK_RAPORU``). Etkinliğin durumu saatten hesaplanır; zamanlayıcı işi gerekmez.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from mesveret.context import Ctx
from mesveret.db.models import (
    CalendarEvent,
    EventAttendance,
    EventReport,
    Message,
    Notification,
    Proposal,
    Topic,
    User,
)
from mesveret.domain.addressees import TAKVIM
from mesveret.domain.rules import format_date
from mesveret.errors import Conflict, DomainError, Forbidden, NotFound
from mesveret.services import events, ledger, media, ontology
from mesveret.services.profile import nickname_map

TZ = ZoneInfo("Europe/Istanbul")
VENUES = {"SALON": "Ortak toplantı salonu", "ADRES": "Adres", "CEVRIMICI": "Çevrim içi"}
SALON_RESOURCE_ID = "salon"
MIN_MINUTES, MAX_MINUTES = 15, 12 * 60
MAX_REPORT = 4000
MAX_PHOTOS = 4


# --- öneri anında -------------------------------------------------------------------------------


def _parse_start(raw: Any) -> datetime:
    if not isinstance(raw, str):
        raise DomainError("Etkinliğin başlangıcı belirtilmeli.")
    try:
        at = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise DomainError("Etkinliğin başlangıç tarihi geçersiz.") from exc
    if at.tzinfo is None:
        at = at.replace(tzinfo=TZ)
    return at.astimezone(UTC)


def slot_conflict(ctx: Ctx, venue_resource_id: str | None, starts_at: datetime,
                  ends_at: datetime, *, exclude_topic_id: int | None = None) -> CalendarEvent | None:
    """Aynı salonda saatleri kesişen planlı etkinlik (adres ve çevrim içi çakışmaz)."""
    if venue_resource_id is None:
        return None
    q = select(CalendarEvent).where(
        CalendarEvent.venue_resource_id == venue_resource_id,
        CalendarEvent.starts_at < ends_at, CalendarEvent.ends_at > starts_at,
    )
    if exclude_topic_id is not None:
        q = q.where(CalendarEvent.topic_id != exclude_topic_id)
    return ctx.db.execute(q.order_by(CalendarEvent.starts_at).limit(1)).scalar_one_or_none()


def _conflict_message(ev: CalendarEvent) -> str:
    return (f"{VENUES['SALON']} {format_date(ev.starts_at)} – "
            f"{ev.ends_at.astimezone(TZ):%H:%M} arasında dolu: «{ev.title}».")


def prepare_event(ctx: Ctx, addressee: str | None, raw: dict[str, Any] | None) -> dict | None:
    """Öneriyle gelen etkinlik bilgisini doğrular ve saklanacak biçime çevirir."""
    if not raw:
        return None
    if addressee != TAKVIM.id:
        raise DomainError("Etkinlik bilgisi yalnızca Meşveret Takvimi'ne giden konuya eklenir.")
    starts_at = _parse_start(raw.get("starts_at"))
    try:
        minutes = int(raw.get("duration_min") or 0)
    except (TypeError, ValueError) as exc:
        raise DomainError("Etkinliğin süresi dakika olarak verilmeli.") from exc
    if not MIN_MINUTES <= minutes <= MAX_MINUTES:
        raise DomainError(f"Etkinliğin süresi {MIN_MINUTES} dakika ile {MAX_MINUTES // 60} saat "
                          "arasında olmalı.")
    earliest = ctx.now + ctx.reg.duration("sessiz_onay_suresi")
    if starts_at < earliest:
        raise DomainError(
            f"Etkinlik, önerinin karara bağlanabileceği en erken andan ({format_date(earliest)}) "
            "sonra başlamalı (sessiz onay süresi)."
        )
    venue = raw.get("venue") or {}
    kind = venue.get("kind")
    if kind not in VENUES:
        raise DomainError("Etkinliğin yeri seçilmeli: ortak salon, bir adres ya da çevrim içi.")
    text = (venue.get("text") or "").strip()
    resource = None
    if kind == "SALON":
        r = ctx.graph.resource(SALON_RESOURCE_ID)
        if r is None:
            raise DomainError("Ortak toplantı salonu tanımlı değil.")
        text, resource = r.name, r.id
    elif not 3 <= len(text) <= 200:
        raise DomainError("Adres ya da bağlantı 3–200 karakter olmalı."
                          if kind == "ADRES" else "Çevrim içi bağlantı 3–200 karakter olmalı.")
    ends_at = starts_at + timedelta(minutes=minutes)
    if (taken := slot_conflict(ctx, resource, starts_at, ends_at)) is not None:
        raise DomainError(_conflict_message(taken))
    return {"starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat(),
            "duration_min": minutes, "venue_kind": kind, "venue_text": text,
            "venue_resource_id": resource}


# --- kabulde ------------------------------------------------------------------------------------


def _notify(ctx: Ctx, user_id: str, title: str, lines: list[str], link: str) -> None:
    ctx.db.add(Notification(user_id=user_id, kind="TAKVIM", title=title, lines=lines, link=link,
                            created_at=ctx.now))


@events.subscribe(events.TopicAccepted)
def _on_topic_accepted(ctx: Ctx, e: events.TopicAccepted) -> None:
    info = e.proposal.payload.get("event")
    if not info or e.topic.addressee != TAKVIM.id:
        return
    starts_at = datetime.fromisoformat(info["starts_at"])
    ends_at = datetime.fromisoformat(info["ends_at"])
    link = f"/konu/{e.topic.id}"
    if starts_at <= ctx.now:
        _notify(ctx, e.proposal.proposer_id, "Etkinlik takvime eklenemedi",
                [(f"{e.topic.title}: konu kabul edildiğinde etkinliğin başlangıcı "
                  f"({format_date(starts_at)}) geçmişti.")], link)
        return
    taken = slot_conflict(ctx, info.get("venue_resource_id"), starts_at, ends_at)
    if taken is not None:
        _notify(ctx, e.proposal.proposer_id, "Etkinlik takvime eklenemedi",
                [f"{e.topic.title}: {_conflict_message(taken)}"], link)
        return
    ev = CalendarEvent(
        topic_id=e.topic.id, proposal_id=e.proposal.id, title=e.topic.title,
        starts_at=starts_at, ends_at=ends_at, venue_kind=info["venue_kind"],
        venue_text=info["venue_text"], venue_resource_id=info.get("venue_resource_id"),
        created_at=ctx.now,
    )
    ctx.db.add(ev)
    ctx.db.flush()
    ledger.enqueue(ctx, "ETKINLIK_PLANLANDI", {
        "etkinlik": ev.id, "konu": e.topic.id, "oneri": e.proposal.id, "baslik": ev.title,
        "baslangic": ev.starts_at.isoformat(), "bitis": ev.ends_at.isoformat(),
        "yer": {"tur": ev.venue_kind, "metin": ev.venue_text},
    }, ref=ev)
    _notify(ctx, e.proposal.proposer_id, "Etkinliğiniz takvime eklendi",
            [f"{ev.title} · {format_date(ev.starts_at)}", f"Yer: {ev.venue_text}"],
            f"/etkinlik/{ev.id}")


# --- katılım ve rapor ---------------------------------------------------------------------------


def get_event(ctx: Ctx, event_id: int) -> CalendarEvent:
    ev = ctx.db.get(CalendarEvent, event_id)
    topic = ctx.db.get(Topic, ev.topic_id) if ev is not None else None
    if ev is None or topic is None or topic.deleted_by_proposal_id is not None:
        raise NotFound("Etkinlik bulunamadı.")
    return ev


def status(ctx: Ctx, ev: CalendarEvent) -> str:
    if ctx.now < ev.starts_at:
        return "YAKLASIYOR"
    return "SURUYOR" if ctx.now < ev.ends_at else "GERCEKLESTI"


def _attending(ctx: Ctx, ev: CalendarEvent, user_id: str) -> EventAttendance | None:
    return ctx.db.execute(select(EventAttendance).where(
        EventAttendance.event_id == ev.id, EventAttendance.user_id == user_id,
    )).scalar_one_or_none()


def attend(ctx: Ctx, user: User, event_id: int, coming: bool) -> dict:
    """"Geliyorum" bildirir ya da geri alır; yalnızca etkinlik başlamadan."""
    ev = get_event(ctx, event_id)
    if ctx.now >= ev.starts_at:
        raise Conflict("Etkinlik başladı; katılım artık değiştirilemez.")
    row = _attending(ctx, ev, user.id)
    if coming and row is None:
        ctx.db.add(EventAttendance(event_id=ev.id, user_id=user.id, created_at=ctx.now))
    elif not coming and row is not None:
        ctx.db.delete(row)
    ctx.commit()
    return {"attending": coming, "count": _attendee_count(ctx, ev)}


def _attendee_count(ctx: Ctx, ev: CalendarEvent) -> int:
    return ctx.db.execute(select(func.count()).select_from(EventAttendance).where(
        EventAttendance.event_id == ev.id)).scalar_one()


def report_refusal(ctx: Ctx, ev: CalendarEvent, user: User | None) -> str | None:
    if user is None:
        return "Rapor yazmak için giriş yapın."
    if ctx.now < ev.ends_at:
        return f"Rapor etkinlik bittikten sonra yazılır ({format_date(ev.ends_at)})."
    if _attending(ctx, ev, user.id) is None:
        return "Raporu etkinliğe katılacağını bildirenler yazar."
    exists = ctx.db.execute(select(EventReport.id).where(
        EventReport.event_id == ev.id, EventReport.author_id == user.id)).first()
    if exists:
        return "Bu etkinliğe zaten bir rapor yazdınız."
    return None


def add_report(ctx: Ctx, user: User, event_id: int, text: str, headcount: int | None,
               media_ids: list[str]) -> EventReport:
    ev = get_event(ctx, event_id)
    if (refusal := report_refusal(ctx, ev, user)) is not None:
        raise Forbidden(refusal)
    text = text.strip()
    if len(text) < 10:
        raise DomainError("Rapor en az 10 karakter olmalı.")
    if len(text) > MAX_REPORT:
        raise DomainError(f"Rapor en fazla {MAX_REPORT} karakter olabilir.")
    if headcount is not None and not 0 <= headcount <= 100_000:
        raise DomainError("Katılımcı sayısı 0 ile 100.000 arasında olmalı.")
    photos = media.check_attachable(ctx, user.id, media_ids, limit=MAX_PHOTOS)
    report = EventReport(event_id=ev.id, author_id=user.id, text=text, headcount=headcount,
                         created_at=ctx.now)
    ctx.db.add(report)
    ctx.db.flush()
    ledger.enqueue(ctx, "ETKINLIK_RAPORU", {
        "etkinlik": ev.id, "konu": ev.topic_id, "yazar": user.nickname, "metin": text,
        "katilimci": headcount, "gorsel": len(photos),
    }, ref=report)
    media.attach(ctx, photos, "rapor", report.id)
    proposer = ctx.db.get(Proposal, ev.proposal_id)
    people = set(ctx.db.execute(select(EventAttendance.user_id).where(
        EventAttendance.event_id == ev.id)).scalars())
    if proposer is not None:
        people.add(proposer.proposer_id)
    people.discard(user.id)
    for uid in sorted(people):
        _notify(ctx, uid, f"{ev.title}: etkinlik raporu",
                [f"{user.nickname} raporunu yazdı.", text[:157] + ("…" if len(text) > 157 else "")],
                f"/etkinlik/{ev.id}")
    ctx.commit()
    return report


# --- görünümler ---------------------------------------------------------------------------------


def summary(ctx: Ctx, ev: CalendarEvent) -> dict[str, Any]:
    topic = ctx.db.get(Topic, ev.topic_id)
    reports = ctx.db.execute(select(func.count()).select_from(EventReport).where(
        EventReport.event_id == ev.id)).scalar_one()
    return {
        "id": ev.id, "title": ev.title, "topic_id": ev.topic_id,
        "area_name": ontology.area_name(ctx, topic.area_id) if topic else None,
        "scope": ontology.scope_label(ctx, topic.owner_scope_id) if topic else None,
        "starts_at": ev.starts_at, "ends_at": ev.ends_at,
        "venue": {"kind": ev.venue_kind, "label": VENUES[ev.venue_kind], "text": ev.venue_text},
        "status": status(ctx, ev), "attendees": _attendee_count(ctx, ev), "reports": reports,
        "cover": media.cover(ctx, ev.proposal_id),
    }


def for_topic(ctx: Ctx, topic: Topic) -> dict | None:
    ev = ctx.db.execute(select(CalendarEvent).where(
        CalendarEvent.topic_id == topic.id)).scalar_one_or_none()
    return summary(ctx, ev) if ev is not None else None


def _visible(ctx: Ctx) -> list[CalendarEvent]:
    rows = ctx.db.execute(select(CalendarEvent, Topic).join(
        Topic, Topic.id == CalendarEvent.topic_id).where(
        Topic.deleted_by_proposal_id.is_(None)).order_by(CalendarEvent.starts_at)).all()
    return [ev for ev, _ in rows]


def listing(ctx: Ctx) -> dict[str, list[dict]]:
    """Yaklaşan (sürenler dahil, yakından uzağa) ve geçmiş (yakından eskiye) etkinlikler."""
    upcoming, past = [], []
    for ev in _visible(ctx):
        (past if ctx.now >= ev.ends_at else upcoming).append(summary(ctx, ev))
    return {"upcoming": upcoming, "past": list(reversed(past))}


def upcoming(ctx: Ctx, limit: int = 3) -> list[dict]:
    return [summary(ctx, ev) for ev in _visible(ctx) if ctx.now < ev.ends_at][:limit]


def view(ctx: Ctx, event_id: int, viewer: User | None) -> dict:
    ev = get_event(ctx, event_id)
    body = summary(ctx, ev)
    topic = ctx.db.get(Topic, ev.topic_id)
    attendees = list(ctx.db.execute(select(EventAttendance.user_id).where(
        EventAttendance.event_id == ev.id).order_by(EventAttendance.created_at)).scalars())
    reports = list(ctx.db.execute(select(EventReport).where(
        EventReport.event_id == ev.id).order_by(EventReport.created_at)).scalars())
    names = nickname_map(ctx, [*attendees, *(r.author_id for r in reports)])
    photos = media.attached(ctx, "rapor", [r.id for r in reports])
    participants = ctx.db.execute(select(func.count(func.distinct(Message.author_id))).where(
        Message.topic_id == ev.topic_id)).scalar_one()
    body.update({
        "topic": {"id": topic.id, "title": topic.title, "participants": participants},
        "proposal_id": ev.proposal_id, "ledger_hash": ev.ledger_hash,
        "attendee_names": [names.get(u, u) for u in attendees],
        "reports": [{"id": r.id, "author": names.get(r.author_id), "text": r.text,
                     "headcount": r.headcount, "created_at": r.created_at,
                     "ledger_hash": r.ledger_hash, "media": photos.get(r.id, [])}
                    for r in reports],
    })
    viewer_info: dict[str, Any] = {"attending": False, "can_attend": False,
                                   "attend_refusal": None, "report_refusal": None}
    if viewer is None:
        viewer_info["attend_refusal"] = "Katılımınızı bildirmek için giriş yapın."
    else:
        viewer_info["attending"] = viewer.id in attendees
        if ctx.now >= ev.starts_at:
            viewer_info["attend_refusal"] = "Etkinlik başladı; katılım artık değiştirilemez."
        else:
            viewer_info["can_attend"] = True
    viewer_info["report_refusal"] = report_refusal(ctx, ev, viewer)
    viewer_info["can_report"] = viewer_info["report_refusal"] is None
    body["viewer"] = viewer_info
    return body


# --- iCalendar (RFC 5545) -------------------------------------------------------------------------


def _ics_text(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\n", "\\n"))


def _ics_time(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _fold(line: str) -> str:
    """75 sekizliği aşan satırı katlar (RFC 5545 §3.1)."""
    raw = line.encode()
    if len(raw) <= 75:
        return line
    parts, chunk = [], b""
    for ch in line:
        b = ch.encode()
        if len(chunk) + len(b) > (75 if not parts else 74):
            parts.append(chunk.decode())
            chunk = b""
        chunk += b
    parts.append(chunk.decode())
    return "\r\n ".join(parts)


def ics(ctx: Ctx, evs: list[CalendarEvent], base_url: str) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Meşveret//Takvim//TR",
             "CALSCALE:GREGORIAN", "X-WR-CALNAME:Meşveret Takvimi"]
    for ev in evs:
        where = ev.venue_text if ev.venue_kind != "CEVRIMICI" else f"Çevrim içi: {ev.venue_text}"
        lines += [
            "BEGIN:VEVENT", f"UID:etkinlik-{ev.id}@mesveret", f"DTSTAMP:{_ics_time(ev.created_at)}",
            f"DTSTART:{_ics_time(ev.starts_at)}", f"DTEND:{_ics_time(ev.ends_at)}",
            f"SUMMARY:{_ics_text(ev.title)}", f"LOCATION:{_ics_text(where)}",
            f"DESCRIPTION:{_ics_text(f'Meşveret konusu №{ev.topic_id}')}",
            f"URL:{base_url.rstrip('/')}/etkinlik/{ev.id}", "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def ics_for(ctx: Ctx, event_id: int | None, base_url: str) -> str:
    evs = [get_event(ctx, event_id)] if event_id is not None else [
        ev for ev in _visible(ctx) if ctx.now < ev.ends_at]
    return ics(ctx, evs, base_url)
