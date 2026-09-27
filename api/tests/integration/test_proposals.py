from datetime import timedelta

import pytest
from sqlalchemy import select

from mesveret.db.models import Message, MessageVersion, Proposal, Topic
from mesveret.errors import Conflict, DomainError, Forbidden
from mesveret.services import proposals, topics
from mesveret.services.proposals import ProposalInput
from tests.integration.helpers import advance, headers_for, open_topic, post, reload
from tests.integration.world import make_user


def konu_input(**kw) -> ProposalInput:
    base = {"type": "KONU", "title": "Film günleri", "body": "Her ay bir film.",
            "area_id": "sinema", "scope_id": "genel"}
    base.update(kw)
    return ProposalInput(**base)


# --- açılış ve denetim ------------------------------------------------------------------------


def test_topic_proposal_opens_in_fast_lane_with_oracle_comment(ctx, ledger):
    u = make_user(ctx, "ayse")
    p = proposals.open_proposal(ctx, u, konu_input())
    assert p.status == "SILENT" and p.lane == "FAST"
    assert p.deadline_at == ctx.now + timedelta(hours=24)
    assert "Denetimler: R1–R6 geçti." in p.oracle_comment
    assert ledger.of_type("ONERI_ACILDI")[0]["payload"]["baslik"] == "Film günleri"
    assert p.ledger_hash == ledger.of_type("ONERI_ACILDI")[0]["hash"]


def test_rule_violation_rejects_with_turkish_reasons(client, ctx):
    u = make_user(ctx, "ayse", city="İstanbul")
    r = client.post("/proposals", headers=headers_for(ctx, u), json={
        "type": "KONU", "title": "Salon İstanbul'a", "body": "Salonu İstanbul kullansın.",
        "area_id": "kent", "scope_id": "sehir:istanbul", "resource_ids": ["salon"],
    })
    assert r.status_code == 422
    body = r.json()
    assert body["violations"][0]["rule"] == "R2"
    assert body["violations"][0]["message"].startswith("Bu kapsam bu kaynak hakkında karar veremez")
    assert ctx.db.execute(select(Proposal)).first() is None


def test_istanbul_budget_proposal_is_narrowed_to_its_share(client, ctx):
    u = make_user(ctx, "ayse", city="İstanbul")
    r = client.post("/proposals", headers=headers_for(ctx, u), json={
        "type": "KONU", "title": "Etkinlik bütçesinin tamamı İstanbul'a",
        "body": "Bütçenin tamamı İstanbul etkinliklerine.", "area_id": "kent",
        "scope_id": "sehir:istanbul", "resource_ids": ["butce"],
    })
    assert r.status_code == 201, r.text
    view = client.get(f"/proposals/{r.json()['id']}").json()
    assert view["narrowings"][0]["message"] == "Bu karar yalnızca İstanbul payını etkiler (4.000 puan)."


def test_proposer_needs_vote_right_in_scope(ctx):
    u = make_user(ctx, "ayse", city="Ankara")
    with pytest.raises(DomainError) as err:
        proposals.open_proposal(ctx, u, konu_input(scope_id="sehir:istanbul", area_id="kent"))
    assert err.value.violations[0]["rule"] == "R5"


def test_recently_rejected_target_cannot_reopen(ctx):
    u = make_user(ctx, "ayse")
    p = proposals.open_proposal(ctx, u, konu_input())
    proposals.reject(ctx, p, "test")
    ctx.db.commit()
    with pytest.raises(DomainError) as err:
        proposals.open_proposal(ctx.at(ctx.now + timedelta(days=10)), u,
                                konu_input(title="  film GÜNLERİ "))
    assert err.value.violations[0]["rule"] == "R6"
    proposals.open_proposal(ctx.at(ctx.now + timedelta(days=31)), u, konu_input())


# --- hızlı şerit ----------------------------------------------------------------------------------


def test_silent_approval_accepts_and_creates_topic(ctx, graph):
    u = make_user(ctx, "ayse", interests=("sinema",))
    p = proposals.open_proposal(ctx, u, konu_input(scope_id="ilgi:sinema"))
    ctx.db.commit()
    later = advance(ctx, timedelta(hours=24, seconds=1))
    p = reload(later, p)
    assert p.status == "ACCEPTED"
    assert p.decided_at == p.deadline_at
    topic = ctx.db.execute(select(Topic).where(Topic.accepted_proposal_id == p.id)).scalar_one()
    assert topic.owner_scope_id == "ilgi:sinema"
    assert graph.resource(f"konu:{topic.id}").owner_scope_id == "ilgi:sinema"
    assert graph.topic_area(f"konu:{topic.id}") == "sinema"
    opening = ctx.db.execute(select(Message).where(Message.topic_id == topic.id)).scalar_one()
    assert opening.is_opening


def test_objections_below_threshold_do_not_stop_silent_approval(ctx):
    u = make_user(ctx, "ayse")
    objectors = [make_user(ctx, f"itiraz{i}") for i in range(2)]
    p = proposals.open_proposal(ctx, u, konu_input())
    for o in objectors:
        proposals.object_to(ctx, o, p.id)
    later = advance(ctx, timedelta(hours=25))
    assert reload(later, p).status == "ACCEPTED"


def test_objection_threshold_moves_to_slow_lane_immediately(ctx):
    u = make_user(ctx, "ayse")
    objectors = [make_user(ctx, f"itiraz{i}") for i in range(3)]
    p = proposals.open_proposal(ctx, u, konu_input())
    results = [proposals.object_to(ctx, o, p.id) for o in objectors]
    assert results[-1]["threshold"] == 3
    assert results[-1]["moved"] is True
    p = reload(ctx, p)
    assert p.status == "QUEUED" and p.lane == "SLOW"
    later = advance(ctx, timedelta(hours=25))
    assert reload(later, p).status == "QUEUED"


def test_objection_threshold_uses_five_percent_of_active_members(ctx):
    from mesveret.services import ontology

    for i in range(80):
        user = make_user(ctx, f"aktif{i}")
        user.last_login_at = ctx.now - timedelta(days=1)
    ctx.db.commit()
    assert ontology.active_member_count(ctx, "genel") == 80
    assert ctx.reg.objection_threshold(80) == 4


def test_objection_requires_vote_right_and_is_personal(ctx):
    u = make_user(ctx, "ayse", interests=("sinema",))
    outsider = make_user(ctx, "yabanci")
    p = proposals.open_proposal(ctx, u, konu_input(scope_id="ilgi:sinema"))
    with pytest.raises(Forbidden):
        proposals.object_to(ctx, outsider, p.id)
    member = make_user(ctx, "uye", interests=("sinema",))
    proposals.object_to(ctx, member, p.id)
    with pytest.raises(Conflict):
        proposals.object_to(ctx, member, p.id)


# --- alt konu -------------------------------------------------------------------------------------


def test_subtopic_must_stay_in_parent_area_subtree(ctx):
    u = make_user(ctx, "ayse")
    topic = open_topic(ctx, u)
    with pytest.raises(DomainError) as err:
        proposals.open_proposal(ctx, u, konu_input(
            type="ALT_KONU", parent_topic_id=topic.id, area_id="edebiyat", title="Roman uyarlamaları",
        ))
    assert err.value.violations[0]["rule"] == "R1"
    p = proposals.open_proposal(ctx, u, konu_input(
        type="ALT_KONU", parent_topic_id=topic.id, area_id="belgesel", title="Belgesel ayı",
    ))
    proposals.accept(ctx, p)
    sub = ctx.db.execute(select(Topic).where(Topic.accepted_proposal_id == p.id)).scalar_one()
    assert sub.parent_id == topic.id


# --- tartışma alanı ve düzenleme ------------------------------------------------------------------


def test_discussion_messages_are_versioned_with_public_history(ctx, ledger, client):
    u = make_user(ctx, "ayse")
    topic = open_topic(ctx, u)
    msg = post(ctx, u, topic, "İlk hâli.")
    topics.edit_own_message(ctx, u, msg.id, "İkinci hâli.")
    history = client.get(f"/messages/{msg.id}/history").json()
    assert [v["text"] for v in history["versions"]] == ["İlk hâli.", "İkinci hâli."]
    assert history["versions"][1]["diff"] == [
        ["delete", "İlk"], ["insert", "İkinci"], ["equal", " hâli."],
    ]
    assert all(v["ledger_hash"] for v in history["versions"])


def test_editing_someone_elses_message_directly_is_forbidden(ctx):
    a, b = make_user(ctx, "ayse"), make_user(ctx, "bora")
    topic = open_topic(ctx, a)
    msg = post(ctx, a, topic, "Ayşe yazdı.")
    with pytest.raises(Forbidden):
        topics.edit_own_message(ctx, b, msg.id, "Bora değiştirdi.")


def test_edit_proposal_for_others_message_adds_version_via_proposal(ctx):
    a, b = make_user(ctx, "ayse"), make_user(ctx, "bora")
    topic = open_topic(ctx, a)
    msg = post(ctx, a, topic, "Toplantı salı.")
    p = proposals.open_proposal(ctx, b, ProposalInput(
        type="DUZENLEME", target_message_id=msg.id, new_text="Toplantı çarşamba.",
    ))
    assert p.status == "SILENT"
    assert p.scope_id == topic.owner_scope_id
    view = proposals.proposal_view(ctx, p, None)
    assert ["insert", "çarşamba"] in [list(c) for c in view["diff"]]
    proposals.accept(ctx, p)
    versions = ctx.db.execute(
        select(MessageVersion).where(MessageVersion.message_id == msg.id)
        .order_by(MessageVersion.version_no)
    ).scalars().all()
    assert versions[-1].text == "Toplantı çarşamba." and versions[-1].via_proposal_id == p.id


def test_edit_proposal_for_own_message_is_rejected(ctx):
    a = make_user(ctx, "ayse")
    topic = open_topic(ctx, a)
    msg = post(ctx, a, topic, "Kendi mesajım.")
    with pytest.raises(DomainError):
        proposals.open_proposal(ctx, a, ProposalInput(
            type="DUZENLEME", target_message_id=msg.id, new_text="Değişti.",
        ))


def test_opening_text_can_only_change_by_proposal_even_for_author(ctx):
    a = make_user(ctx, "ayse")
    topic = open_topic(ctx, a)
    opening = ctx.db.execute(
        select(Message).where(Message.topic_id == topic.id, Message.is_opening)
    ).scalar_one()
    with pytest.raises(Forbidden):
        topics.edit_own_message(ctx, a, opening.id, "Yeni açılış.")
    p = proposals.open_proposal(ctx, a, ProposalInput(
        type="DUZENLEME", target_message_id=opening.id, new_text="Yeni açılış.",
    ))
    assert p.status == "SILENT"


def test_cellar_links_are_rejected_in_square(ctx):
    a = make_user(ctx, "ayse")
    topic = open_topic(ctx, a)
    with pytest.raises(DomainError):
        post(ctx, a, topic, "Şuna bakın: /mahzen/12")


# --- silme ----------------------------------------------------------------------------------------


def test_deletion_goes_to_slow_lane_and_hides_content(ctx, client, ledger):
    a, b = make_user(ctx, "ayse"), make_user(ctx, "bora")
    topic = open_topic(ctx, a)
    msg = post(ctx, a, topic, "Silinecek mesaj.")
    p = proposals.open_proposal(ctx, b, ProposalInput(type="SILME", target_message_id=msg.id))
    assert p.status == "QUEUED" and p.lane == "SLOW"
    proposals.accept(ctx, p)
    ctx.db.commit()
    view = client.get(f"/topics/{topic.id}").json()
    deleted = next(m for m in view["messages"] if m["id"] == msg.id)
    assert set(deleted) == {"id", "deleted_by_proposal_id", "ledger_hash"}
    assert deleted["deleted_by_proposal_id"] == p.id
    assert client.get(f"/messages/{msg.id}/history").status_code == 410
    texts = [r["payload"].get("metin") for r in ledger.records]
    assert "Silinecek mesaj." in texts  # defterde duruyor


def test_own_message_deletion_also_requires_vote(ctx):
    a = make_user(ctx, "ayse")
    topic = open_topic(ctx, a)
    msg = post(ctx, a, topic, "Pişmanım.")
    p = proposals.open_proposal(ctx, a, ProposalInput(type="SILME", target_message_id=msg.id))
    assert p.status == "QUEUED"


# --- yönetmelik -----------------------------------------------------------------------------------


def test_regulation_proposal_validates_value_and_goes_to_slow_lane(ctx):
    a = make_user(ctx, "ayse")
    with pytest.raises(DomainError):
        proposals.open_proposal(ctx, a, ProposalInput(
            type="YONETMELIK", article_key="yonetmelik_esigi",
            new_value={"oran": "1/3", "karsilastirma": ">="},
        ))
    p = proposals.open_proposal(ctx, a, ProposalInput(
        type="YONETMELIK", article_key="red_bekleme", new_value={"gun": 45}, body="Daha uzun olsun.",
    ))
    assert p.status == "QUEUED" and p.scope_id == "genel" and p.area_id is None
    proposals.accept(ctx, p)
    ctx.invalidate_regulation()
    assert ctx.reg.duration("red_bekleme") == timedelta(days=45)


def test_regulation_proposal_outside_general_scope_is_rejected(ctx):
    a = make_user(ctx, "ayse")
    with pytest.raises(DomainError) as err:
        proposals.open_proposal(ctx, a, ProposalInput(
            type="YONETMELIK", article_key="red_bekleme", new_value={"gun": 45},
            scope_id="sehir:istanbul",
        ))
    assert "R3" in [v["rule"] for v in err.value.violations]


# --- kapanış --------------------------------------------------------------------------------------


def test_closure_needs_participant_and_collects_rivals(ctx):
    a, b, c = make_user(ctx, "ayse"), make_user(ctx, "bora"), make_user(ctx, "cem")
    topic = open_topic(ctx, a)
    post(ctx, b, topic, "Katılıyorum.")
    with pytest.raises(Forbidden):
        proposals.open_proposal(ctx, c, ProposalInput(
            type="KAPANIS", target_topic_id=topic.id, body="Karar: her ay film.",
        ))
    p = proposals.open_proposal(ctx, a, ProposalInput(
        type="KAPANIS", target_topic_id=topic.id, body="Karar: her ay film.",
    ))
    assert p.status == "RIVAL_PERIOD"
    assert p.deadline_at == ctx.now + timedelta(hours=48)
    proposals.add_rival(ctx, b, p.id, "Karar: iki ayda bir film.")
    with pytest.raises(Conflict):
        proposals.add_rival(ctx, b, p.id, "İkinci metin.")
    with pytest.raises(Conflict):
        proposals.open_proposal(ctx, b, ProposalInput(
            type="KAPANIS", target_topic_id=topic.id, body="Başka kapanış.",
        ))
    later = advance(ctx, timedelta(hours=48, seconds=1))
    p = reload(later, p)
    assert p.status == "QUEUED" and p.queued_at == p.deadline_at
    with pytest.raises(Conflict):
        proposals.add_rival(later, a, p.id, "Geç kalan metin.")


def test_closed_topic_is_read_only_and_reopens_after_waiting_period(ctx):
    a, b = make_user(ctx, "ayse"), make_user(ctx, "bora")
    topic = open_topic(ctx, a)
    p = proposals.open_proposal(ctx, a, ProposalInput(
        type="KAPANIS", target_topic_id=topic.id, body="Karar: her ay film.",
    ))
    text_id = proposals.closure_texts(ctx, p)[0].id
    proposals.accept(ctx, p, winner_text_id=text_id)
    ctx.db.refresh(topic)
    assert topic.status == "CLOSED"
    with pytest.raises(Conflict):
        post(ctx, b, topic, "Geç kaldım.")
    with pytest.raises(DomainError):
        proposals.open_proposal(ctx.at(ctx.now + timedelta(days=30)), a, ProposalInput(
            type="KONU", reopens_topic_id=topic.id, body="Yeniden konuşalım.",
        ))
    p2 = proposals.open_proposal(ctx.at(ctx.now + timedelta(days=91)), a, ProposalInput(
        type="KONU", reopens_topic_id=topic.id, body="Yeniden konuşalım.",
    ))
    proposals.accept(ctx.at(ctx.now + timedelta(days=92)), p2)
    ctx.db.refresh(topic)
    assert topic.status == "OPEN"


# --- API ------------------------------------------------------------------------------------------


def test_api_objection_and_listing(client, ctx):
    a, b = make_user(ctx, "ayse"), make_user(ctx, "bora")
    r = client.post("/proposals", headers=headers_for(ctx, a), json={
        "type": "KONU", "title": "Metro saatleri", "body": "Metro gece de çalışsın.",
        "area_id": "ulasim", "scope_id": "genel",
    })
    pid = r.json()["id"]
    r = client.post(f"/proposals/{pid}/objections", headers=headers_for(ctx, b))
    assert r.status_code == 200 and r.json()["count"] == 1
    listing = client.get("/proposals", params={"state": "open"}).json()
    assert [x["id"] for x in listing] == [pid]
    view = client.get(f"/proposals/{pid}", headers=headers_for(ctx, b)).json()
    assert view["objections"] == {"count": 1, "threshold": 3}
    assert view["viewer"]["has_objected"] is True
