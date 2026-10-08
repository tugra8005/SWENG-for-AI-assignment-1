from datetime import timedelta

from sqlalchemy import select

from mesveret import clock
from mesveret.db.models import CalendarEvent, Notification, Topic
from mesveret.services import proposals
from mesveret.services.proposals import ProposalInput
from tests.integration.helpers import headers_for
from tests.integration.test_media import _upload
from tests.integration.world import make_user

SALON = {"kind": "SALON"}


def _event(ctx, *, days=3, hour=19, minutes=120, venue=None):
    """Başlangıç: bugünden ``days`` gün sonra, İstanbul saatiyle ``hour``:00."""
    local = (ctx.now + timedelta(days=days)).astimezone(clock.ISTANBUL)
    start = local.replace(hour=hour, minute=0, second=0, microsecond=0)
    return {"starts_at": start.isoformat(), "duration_min": minutes, "venue": venue or SALON}


def _open(ctx, user, *, event, title="Dekalog I gösterimi", scope="genel", addressee="takvim"):
    return proposals.open_proposal(ctx, user, ProposalInput(
        type="KONU", title=title, body="Kieślowski'nin Dekalog'unun ilk bölümünü izleyelim.",
        area_id="sinema", scope_id=scope, addressee=addressee, event=event))


def _accept(ctx, p):
    later = ctx.at(p.deadline_at)
    proposals.accept(later, p)
    later.commit()
    return ctx.db.execute(select(Topic).where(Topic.accepted_proposal_id == p.id)).scalar_one()


def _set(ctx, at):
    clock.set_now(ctx.db, at)
    ctx.db.commit()
    return ctx.at(at)


def test_accepted_calendar_topic_plans_the_event(ctx, client, ledger):
    a = make_user(ctx, "ayse")
    p = _open(ctx, a, event=_event(ctx))
    assert p.resource_ids == ["salon"]  # salon kaynağı kendiliğinden etiketlenir (R2)
    assert p.payload["event"]["venue_kind"] == "SALON"
    topic = _accept(ctx, p)

    view = client.get(f"/topics/{topic.id}").json()
    ev = view["event"]
    assert ev["title"] == "Dekalog I gösterimi" and ev["status"] == "YAKLASIYOR"
    assert ev["venue"] == {"kind": "SALON", "label": "Ortak toplantı salonu",
                           "text": "Ortak toplantı salonu"}
    assert [e["id"] for e in client.get("/calendar").json()["upcoming"]] == [ev["id"]]
    rec = ledger.of_type("ETKINLIK_PLANLANDI")[0]["payload"]
    assert rec["konu"] == topic.id and rec["yer"]["tur"] == "SALON"
    note = ctx.db.execute(select(Notification).where(Notification.kind == "TAKVIM")).scalar_one()
    assert note.user_id == a.id and note.title == "Etkinliğiniz takvime eklendi"

    ics = client.get(f"/events/{ev['id']}/ics")
    assert ics.headers["content-type"].startswith("text/calendar")
    assert "SUMMARY:Dekalog I gösterimi" in ics.text and ics.text.endswith("END:VCALENDAR\r\n")
    assert "BEGIN:VEVENT" in client.get("/calendar.ics").text


def test_event_requires_calendar_addressee_and_enough_lead_time(ctx, client):
    a = make_user(ctx, "ayse")
    body = {"type": "KONU", "title": "Film", "body": "Film izleyelim.", "area_id": "sinema",
            "scope_id": "genel", "addressee": "bakanlik:kultur", "event": _event(ctx)}
    r = client.post("/proposals", headers=headers_for(ctx, a), json=body)
    assert r.status_code == 422 and "yalnızca Meşveret Takvimi" in r.json()["detail"]
    soon = _event(ctx, days=0, hour=23)
    r = client.post("/proposals", headers=headers_for(ctx, a),
                    json={**body, "addressee": "takvim", "event": soon})
    assert r.status_code == 422 and "sessiz onay süresi" in r.json()["detail"]
    r = client.post("/proposals", headers=headers_for(ctx, a), json={
        **body, "addressee": "takvim",
        "event": {**_event(ctx), "venue": {"kind": "ADRES", "text": ""}}})
    assert r.status_code == 422 and "3–200" in r.json()["detail"]


def test_salon_is_owned_by_general_scope_and_cannot_be_double_booked(ctx, client):
    a = make_user(ctx, "ayse")
    r = client.post("/proposals", headers=headers_for(ctx, a), json={
        "type": "KONU", "title": "İstanbul film gecesi", "body": "Salonda film.",
        "area_id": "sinema", "scope_id": "sehir:istanbul", "addressee": "takvim",
        "event": _event(ctx)})
    assert r.status_code == 422
    assert [v["rule"] for v in r.json()["violations"]] == ["R2"]

    _accept(ctx, _open(ctx, a, event=_event(ctx, hour=19, minutes=120)))
    clash = _event(ctx, hour=20, minutes=60)
    r = client.post("/proposals", headers=headers_for(ctx, a), json={
        "type": "KONU", "title": "Şiir akşamı", "body": "Salonda şiir.", "area_id": "sinema",
        "scope_id": "genel", "addressee": "takvim", "event": clash})
    assert r.status_code == 422 and "dolu" in r.json()["detail"]
    online = {**clash, "venue": {"kind": "CEVRIMICI", "text": "meet.example.org/siir"}}
    r = client.post("/proposals", headers=headers_for(ctx, a), json={
        "type": "KONU", "title": "Şiir akşamı", "body": "Çevrim içi şiir.",
        "area_id": "sinema", "scope_id": "genel", "addressee": "takvim", "event": online})
    assert r.status_code == 201, r.text


def test_attendance_then_report_with_photo_after_the_event(ctx, client, ledger):
    a, b, c = make_user(ctx, "ayse"), make_user(ctx, "bora"), make_user(ctx, "cem")
    topic = _accept(ctx, _open(ctx, a, event=_event(ctx)))
    ev = ctx.db.execute(select(CalendarEvent).where(CalendarEvent.topic_id == topic.id)).scalar_one()
    url = f"/events/{ev.id}"
    r = client.put(f"{url}/attendance", headers=headers_for(ctx, b), json={"coming": True})
    assert r.json() == {"attending": True, "count": 1}
    client.put(f"{url}/attendance", headers=headers_for(ctx, c), json={"coming": True})
    r = client.put(f"{url}/attendance", headers=headers_for(ctx, c), json={"coming": False})
    assert r.json() == {"attending": False, "count": 1}
    view = client.get(url, headers=headers_for(ctx, b)).json()
    assert view["attendee_names"] == ["bora"] and view["viewer"]["attending"]
    assert "bittikten sonra" in view["viewer"]["report_refusal"]

    during = _set(ctx, ev.starts_at + timedelta(minutes=10))
    r = client.put(f"{url}/attendance", headers=headers_for(during, c), json={"coming": True})
    assert r.status_code == 409
    after = _set(ctx, ev.ends_at + timedelta(hours=1))
    report = {"text": "On dört kişi geldik, gösterimden sonra bir saat konuştuk.", "headcount": 14}
    r = client.post(f"{url}/reports", headers=headers_for(after, c), json=report)
    assert r.status_code == 403 and "bildirenler" in r.json()["detail"]
    pic = _upload(client, after, b, alt="Salonda perdeye yansıyan film").json()
    r = client.post(f"{url}/reports", headers=headers_for(after, b),
                    json={**report, "media_ids": [pic["id"]]})
    assert r.status_code == 201, r.text
    assert client.post(f"{url}/reports", headers=headers_for(after, b),
                       json=report).status_code == 403

    view = client.get(url).json()
    assert view["status"] == "GERCEKLESTI" and view["reports"][0]["headcount"] == 14
    assert view["reports"][0]["media"][0]["id"] == pic["id"]
    assert client.get("/calendar").json()["past"][0]["reports"] == 1
    assert ledger.of_type("ETKINLIK_RAPORU")[0]["payload"]["yazar"] == "bora"
    notes = ctx.db.execute(select(Notification.user_id).where(
        Notification.title == "Dekalog I gösterimi: etkinlik raporu")).scalars().all()
    assert notes == [a.id]


def test_topic_accepted_after_the_start_time_gets_no_event(ctx):
    a = make_user(ctx, "ayse")
    p = _open(ctx, a, event=_event(ctx, days=2))
    late = ctx.at(ctx.now + timedelta(days=5))
    proposals.accept(late, p)
    ctx.db.commit()
    assert ctx.db.execute(select(CalendarEvent)).first() is None
    note = ctx.db.execute(select(Notification).where(Notification.kind == "TAKVIM")).scalar_one()
    assert note.title == "Etkinlik takvime eklenemedi" and "geçmişti" in note.lines[0]
