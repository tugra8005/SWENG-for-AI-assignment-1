from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from mesveret.db.models import SessionItem
from mesveret.services import decision_hour, proposals
from mesveret.services.proposals import ProposalInput
from tests.integration.helpers import open_topic, post, reload
from tests.integration.world import make_user

T0 = datetime(2026, 9, 29, 7, 0, tzinfo=UTC)  # Salı 10:00 İstanbul


def items(ctx, session) -> set[int]:
    return set(ctx.db.execute(
        select(SessionItem.proposal_id).where(SessionItem.session_id == session.id)
    ).scalars())


def close(ctx, session):
    later = ctx.at(session.closes_at)
    decision_hour.close_session(later, session)
    later.commit()
    return later


def test_general_proposal_opened_just_before_session_waits_seven_days(ctx):
    a = make_user(ctx, "aylin")
    p = proposals.open_proposal(ctx, a, ProposalInput(
        type="YONETMELIK", article_key="musavir_esigi", new_value={"deger": 3},
    ))
    session = decision_hour.open_session(ctx.at(T0 + timedelta(minutes=10)))
    assert p.id not in items(ctx, session)
    assert reload(ctx, p).status == "QUEUED"
    later = close(ctx, session)
    view = proposals.proposal_view(later, reload(later, p), None)
    m = view["maturity"]
    assert m["klass"] == "genel" and m["mature"] is False
    assert m["matures_at"] == T0 + timedelta(days=7)
    # Salı + 7 gün = Salı; o haftanın Pazar oturumu (4 Ekim) olgunlaşmadan önce: 11 Ekim.
    assert m["first_session_at"] == datetime(2026, 10, 11, 17, 0, tzinfo=UTC)
    mature = later.at(T0 + timedelta(days=7, minutes=1))
    s2 = decision_hour.open_session(mature)
    assert p.id in items(mature, s2)


def test_fast_lane_fall_starts_the_clock_at_the_fall(ctx):
    a = make_user(ctx, "aylin", city="İstanbul")
    objectors = [make_user(ctx, f"itiraz{i}", city="İstanbul") for i in range(3)]
    p = proposals.open_proposal(ctx, a, ProposalInput(
        type="KONU", title="Kadıköy çarşısı", body="Çarşı pazar günü de açık olsun.",
        area_id="kent", scope_id="sehir:istanbul",
    ))
    fall = T0 + timedelta(hours=20)
    for o in objectors:
        proposals.object_to(ctx.at(fall), o, p.id)
    p = reload(ctx, p)
    assert p.status == "QUEUED" and p.queued_at == fall
    view = proposals.proposal_view(ctx.at(fall), p, None)
    assert view["maturity"]["klass"] == "dar"
    assert view["maturity"]["matures_at"] == fall + timedelta(hours=48)
    # Açılıştan 48 saat geçti ama düşüşten geçmedi: oturuma alınmaz.
    s1 = decision_hour.open_session(ctx.at(T0 + timedelta(hours=50)))
    assert p.id not in items(ctx, s1)
    after = close(ctx, s1)
    s2 = decision_hour.open_session(after.at(fall + timedelta(hours=48)))
    assert p.id in items(after, s2)


def test_interest_scope_of_non_leaf_area_is_wide(ctx):
    a = make_user(ctx, "aylin", interests=("sinema",))
    p = proposals.open_proposal(ctx, a, ProposalInput(
        type="KONU", title="Sinema kulübü", body="Haftalık gösterim.", area_id="sinema",
        scope_id="ilgi:sinema",
    ))
    p.status, p.lane, p.queued_at = "QUEUED", "SLOW", ctx.now
    ctx.db.commit()
    view = proposals.proposal_view(ctx, p, None)
    assert view["maturity"]["klass"] == "genis"
    assert view["maturity"]["matures_at"] == ctx.now + timedelta(hours=72)


def test_status_lists_maturing_queue(client, ctx):
    a = make_user(ctx, "aylin")
    proposals.open_proposal(ctx, a, ProposalInput(
        type="YONETMELIK", article_key="musavir_esigi", new_value={"deger": 3},
    ))
    queued = client.get("/decision-hour").json()["queued"]
    assert queued[0]["maturity"]["mature"] is False
    assert queued[0]["maturity"]["first_session_at"].startswith("2026-10-11T17:00")
    listing = client.get("/proposals", params={"state": "open"}).json()
    assert listing[0]["maturity"]["first_session_at"].startswith("2026-10-11T17:00")


def test_dev_open_reports_proposals_left_to_mature(ctx):
    from mesveret.services import devtools

    a = make_user(ctx, "aylin")
    p = proposals.open_proposal(ctx, a, ProposalInput(
        type="YONETMELIK", article_key="musavir_esigi", new_value={"deger": 3},
    ))
    out = devtools.open_decision_hour(ctx.at(T0 + timedelta(minutes=10)), scripted=False)
    assert out["session"]["items"] == []
    assert [q["id"] for q in out["maturing"]] == [p.id]
    assert out["maturing"][0]["maturity"]["first_session_at"] == datetime(2026, 10, 11, 17, 0, tzinfo=UTC)


def test_topic_page_lists_related_proposal_maturity(ctx, client):
    a, b = make_user(ctx, "ayse"), make_user(ctx, "bora")
    topic = open_topic(ctx, a)
    msg = post(ctx, a, topic, "Silinecek mesaj.")
    p = proposals.open_proposal(ctx, b, ProposalInput(type="SILME", target_message_id=msg.id))
    related = client.get(f"/topics/{topic.id}").json()["proposals"]
    assert [r["id"] for r in related] == [p.id]
    assert related[0]["maturity"]["klass"] == "genel"
    assert related[0]["maturity"]["mature"] is False
    assert related[0]["effective_title"] is None
