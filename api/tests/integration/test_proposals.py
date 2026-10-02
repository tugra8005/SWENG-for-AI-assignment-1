from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from mesveret.db.models import Message, MessageVersion, Proposal, Topic
from mesveret.errors import Conflict, DomainError, Forbidden
from mesveret.services import proposals, topics
from mesveret.services.proposals import ProposalInput
from tests.integration.helpers import advance, headers_for, open_topic, post, reload
from tests.integration.world import make_user


def konu_input(**kw) -> ProposalInput:
    base = {"type": "KONU", "addressee": "takvim", "title": "Film günleri", "body": "Her ay bir film.",
            "area_id": "sinema", "scope_id": "genel"}
    base.update(kw)
    return ProposalInput(**base)


# --- açılış ve denetim ------------------------------------------------------------------------


def test_topic_proposal_opens_in_fast_lane_with_oracle_comment(ctx, ledger):
    u = make_user(ctx, "ayse")
    p = proposals.open_proposal(ctx, u, konu_input())
    assert p.status == "SILENT" and p.lane == "FAST"
    assert p.deadline_at == ctx.now + timedelta(hours=24)
    assert "Denetimler: R1–R9 geçti." in p.oracle_comment
    assert ledger.of_type("ONERI_ACILDI")[0]["payload"]["baslik"] == "Film günleri"
    assert p.ledger_hash == ledger.of_type("ONERI_ACILDI")[0]["hash"]


def test_rule_violation_rejects_with_turkish_reasons(client, ctx):
    u = make_user(ctx, "ayse", city="İstanbul")
    r = client.post("/proposals", headers=headers_for(ctx, u), json={
        "type": "KONU", "addressee": "takvim", "title": "Salon İstanbul'a", "body": "Salonu İstanbul kullansın.",
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
        "type": "KONU", "addressee": "takvim", "title": "Etkinlik bütçesinin tamamı İstanbul'a",
        "body": "Bütçenin tamamı İstanbul etkinliklerine.", "area_id": "kent",
        "scope_id": "sehir:istanbul", "resource_ids": ["butce"],
    })
    assert r.status_code == 201, r.text
    view = client.get(f"/proposals/{r.json()['id']}").json()
    n = view["narrowings"][0]
    assert n["message"] == "Bu karar yalnızca İstanbul payını etkiler (4.000 puan)."
    assert (n["share"], n["total"]) == (4000, 9000)
    assert view["title"] == "Etkinlik bütçesinin tamamı İstanbul'a"
    assert view["effective_title"] == "Etkinlik bütçesinin İstanbul payı"
    [res] = view["resources"]
    assert res["narrowed"] == {"scope": "İstanbul", "share": 4000, "total": 9000}
    assert "Talep kaynağın tamamını hedefliyordu" in view["oracle_comment"]
    [card] = client.get("/proposals", params={"state": "open"}).json()
    assert card["effective_title"] == "Etkinlik bütçesinin İstanbul payı"

    # Kabul edilince doğan konu da talebi değil etkiyi başlık yapar; öneri konuya bağlanır.
    p = ctx.db.get(Proposal, view["id"])
    proposals.accept(ctx.at(p.deadline_at), p)
    ctx.db.commit()
    view = client.get(f"/proposals/{p.id}").json()
    topic = client.get(f"/topics/{view['topic_id']}").json()
    assert topic["title"] == "Etkinlik bütçesinin tamamı İstanbul'a"
    assert topic["effective_title"] == "Etkinlik bütçesinin İstanbul payı"
    assert topic["narrowings"][0]["share"] == 4000
    assert topic["proposed_at"] < topic["created_at"]  # önerilme anı ≠ kabul anı
    [listed] = [t for t in client.get("/topics").json() if t["id"] == topic["id"]]
    assert listed["effective_title"] == "Etkinlik bütçesinin İstanbul payı"


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


SPAM = "Kaçırmayın! Katlanır bisiklette büyük indirim, sipariş için profilime tıklayın."


def test_deletion_goes_to_slow_lane_and_hides_content(ctx, client, ledger):
    a, b = make_user(ctx, "ayse"), make_user(ctx, "bora")
    topic = open_topic(ctx, a)
    msg = post(ctx, a, topic, SPAM)
    p = proposals.open_proposal(ctx, b, ProposalInput(
        type="SILME", target_message_id=msg.id, content_rules=["IK-1"],
        excerpt="sipariş için profilime tıklayın",
    ))
    assert p.status == "QUEUED" and p.lane == "SLOW"
    assert p.payload["rules"] == ["IK-1"] and p.payload["own"] is False
    assert proposals.threshold_key(p) == "silme_esigi"
    assert "İçerik kuralı IK-1 (Spam ve reklam): belirtilen kısımda karşılığı var" in p.oracle_comment
    view = client.get(f"/proposals/{p.id}").json()
    assert view["content_rules"] == [{"code": "IK-1", "title": "Spam ve reklam"}]
    assert view["excerpt"] == "sipariş için profilime tıklayın"
    assert view["threshold"] == {"key": "silme_esigi", "oran": "2/3", "karsilastirma": ">="}
    # Oylama sürerken mesajın üstünde işaret: hangi öneri, ne zaman karara bağlanacak.
    pending = next(m for m in client.get(f"/topics/{topic.id}").json()["messages"]
                   if m["id"] == msg.id)["pending_deletion"]
    assert pending["proposal_id"] == p.id
    assert datetime.fromisoformat(pending["decides_at"]) == proposals.maturity(ctx, p)["first_session_at"]
    proposals.accept(ctx, p)
    ctx.commit()
    view = client.get(f"/topics/{topic.id}").json()
    deleted = next(m for m in view["messages"] if m["id"] == msg.id)
    assert set(deleted) == {"id", "deleted_by_proposal_id", "ledger_hash", "deletion_basis"}
    assert deleted["deleted_by_proposal_id"] == p.id
    assert deleted["deletion_basis"] == {"rules": ["IK-1"], "own": False}
    assert client.get(f"/messages/{msg.id}/history").status_code == 410
    texts = [r["payload"].get("metin") for r in ledger.records]
    assert SPAM in texts  # defterde duruyor
    assert ledger.of_type("ICERIK_SILINDI")[0]["payload"]["kurallar"] == ["IK-1"]


def test_deletion_without_justification_is_rejected_by_r7(ctx, client):
    a, b = make_user(ctx, "ayse"), make_user(ctx, "bora")
    topic = open_topic(ctx, a)
    msg = post(ctx, a, topic, "Bu görüşe katılmıyorum.")
    r = client.post("/proposals", headers=headers_for(ctx, b), json={
        "type": "SILME", "target_message_id": msg.id,
    })
    assert r.status_code == 422, r.text
    violations = r.json()["violations"]
    assert {v["rule"] for v in violations} == {"R7"}
    assert "en az bir içerik kuralına dayanmalı" in violations[0]["message"]
    assert "hangi kısmının" in violations[1]["message"]
    r = client.post("/proposals", headers=headers_for(ctx, b), json={
        "type": "SILME", "target_message_id": msg.id, "content_rules": ["IK-2"],
        "excerpt": "hepsi cahil",
    })
    assert r.status_code == 422
    assert "metinde geçmiyor" in r.json()["violations"][0]["message"]


def test_own_message_deletion_needs_no_justification_and_simple_majority(ctx, client):
    a = make_user(ctx, "ayse")
    topic = open_topic(ctx, a)
    msg = post(ctx, a, topic, "Pişmanım.")
    p = proposals.open_proposal(ctx, a, ProposalInput(type="SILME", target_message_id=msg.id))
    assert p.status == "QUEUED"
    assert p.payload["own"] is True and p.payload["rules"] == []
    assert proposals.threshold_key(p) == "basit_cogunluk"
    assert "kendi mesajının silinmesini istiyor" in p.oracle_comment
    proposals.accept(ctx, p)
    ctx.db.commit()
    [deleted] = [m for m in client.get(f"/topics/{topic.id}").json()["messages"] if m["id"] == msg.id]
    assert deleted["deletion_basis"] == {"rules": [], "own": True}


def test_topic_deletion_is_never_treated_as_own(ctx):
    a = make_user(ctx, "ayse")
    topic = open_topic(ctx, a)
    with pytest.raises(DomainError) as err:
        proposals.open_proposal(ctx, a, ProposalInput(type="SILME", target_topic_id=topic.id))
    assert err.value.violations[0]["rule"] == "R7"


# --- yönetmelik -----------------------------------------------------------------------------------


# --- içerik kuralı ekleme ve kaldırma --------------------------------------------------------------

NEW_RULE = {"baslik": "Dolandırıcılık", "metin": "Sahte bağış ya da yatırım çağrısı.",
            "anahtar_kelimeler": ["bağış", "yatırım", "havale et"]}


def test_content_rule_can_be_added_by_regulation_vote(ctx, client):
    a, b = make_user(ctx, "ayse"), make_user(ctx, "bora")
    p = proposals.open_proposal(ctx, a, ProposalInput(
        type="YONETMELIK", article_action="ekle", new_value=NEW_RULE, body="Dolandırıcılık artıyor.",
    ))
    assert p.payload["article_key"] == "IK-4" and p.payload["action"] == "ekle"
    assert p.payload["old_value"] is None and p.status == "QUEUED" and p.scope_id == "genel"
    assert proposals.threshold_key(p) == "yonetmelik_esigi"
    assert p.title == "Yönetmelik: IK-4 eklensin (Dolandırıcılık)"
    # Aynı anda açılan ikinci ekleme önerisi başka bir kod alır.
    q = proposals.open_proposal(ctx, b, ProposalInput(
        type="YONETMELIK", article_action="ekle",
        new_value={**NEW_RULE, "baslik": "Kimlik taklidi", "anahtar_kelimeler": ["ben aslında"]},
    ))
    assert q.payload["article_key"] == "IK-5"
    proposals.accept(ctx, p)
    ctx.commit()
    assert "IK-4" in ctx.reg.content_rules()
    listing = {a["key"]: a for a in client.get("/regulation").json()}
    assert listing["IK-4"]["value"]["baslik"] == "Dolandırıcılık"
    assert listing["IK-4"]["history"][0]["proposal_id"] == p.id
    # Yeni kurala dayanan silme önerisi açılabilir.
    topic = open_topic(ctx, a)
    msg = post(ctx, a, topic, "Acil bağış lazım, hemen hesabıma havale edin.")
    s = proposals.open_proposal(ctx, b, ProposalInput(
        type="SILME", target_message_id=msg.id, content_rules=["IK-4"], excerpt="Acil bağış lazım",
    ))
    assert "IK-4 (Dolandırıcılık): belirtilen kısımda karşılığı var" in s.oracle_comment


def test_content_rule_can_be_removed_and_its_code_is_never_reused(ctx, client, ledger):
    a, b = make_user(ctx, "ayse"), make_user(ctx, "bora")
    p = proposals.open_proposal(ctx, a, ProposalInput(
        type="YONETMELIK", article_action="kaldir", article_key="IK-3", body="Gereksiz.",
    ))
    assert p.payload == {"article_key": "IK-3", "action": "kaldir",
                         "old_value": ctx.reg.raw("IK-3"), "new_value": None,
                         "addressee": "mesveret"}
    assert p.title == "Yönetmelik: IK-3 kaldırılsın (Başkasının kişisel bilgilerini ifşa etme)"
    proposals.accept(ctx, p)
    ctx.commit()
    assert list(ctx.reg.content_rules()) == ["IK-1", "IK-2"]
    assert ledger.of_type("YONETMELIK_DEGISTI")[0]["payload"]["islem"] == "kaldir"
    listing = {a["key"]: a for a in client.get("/regulation").json()}
    assert listing["IK-3"]["value"] is None and listing["IK-3"]["removed"] is True
    # Kaldırılan kurala dayanan silme R7'de reddedilir; kaldırılan kod yeniden kullanılmaz.
    topic = open_topic(ctx, a)
    msg = post(ctx, a, topic, "Ayşe'nin telefonu 0532 000 00 00.")
    with pytest.raises(DomainError) as err:
        proposals.open_proposal(ctx, b, ProposalInput(
            type="SILME", target_message_id=msg.id, content_rules=["IK-3"], excerpt="telefonu",
        ))
    assert "Böyle bir içerik kuralı yok: IK-3" in err.value.violations[0]["message"]
    n = proposals.open_proposal(ctx, b, ProposalInput(
        type="YONETMELIK", article_action="ekle", new_value=NEW_RULE,
    ))
    assert n.payload["article_key"] == "IK-4"
    with pytest.raises(DomainError):  # kaldırılmış kural değiştirilemez
        proposals.open_proposal(ctx, b, ProposalInput(
            type="YONETMELIK", article_key="IK-3", new_value=NEW_RULE,
        ))


def test_parameters_cannot_be_added_or_removed_and_bad_rules_are_rejected(ctx):
    a = make_user(ctx, "ayse")
    for inp in (
        ProposalInput(type="YONETMELIK", article_action="kaldir", article_key="red_bekleme"),
        ProposalInput(type="YONETMELIK", article_action="kaldir", article_key="IK-9"),
        ProposalInput(type="YONETMELIK", article_action="ekle", new_value={"baslik": "Boş"}),
        ProposalInput(type="YONETMELIK", article_action="sil", article_key="IK-1"),
    ):
        with pytest.raises(DomainError):
            proposals.open_proposal(ctx, a, inp)


def test_accepting_a_change_to_a_removed_rule_does_not_resurrect_it(ctx):
    a, b = make_user(ctx, "ayse"), make_user(ctx, "bora")
    change = proposals.open_proposal(ctx, a, ProposalInput(
        type="YONETMELIK", article_key="IK-3", new_value={**NEW_RULE, "baslik": "Kişisel bilgi"},
    ))
    removal = proposals.open_proposal(ctx, b, ProposalInput(
        type="YONETMELIK", article_action="kaldir", article_key="IK-3",
    ))
    proposals.accept(ctx, removal)
    with pytest.raises(DomainError):
        proposals.accept(ctx, change)
    assert "IK-3" not in ctx.reg.content_rules()


def test_rejected_rule_addition_cannot_return_under_a_new_code(ctx):
    a = make_user(ctx, "ayse")
    p = proposals.open_proposal(ctx, a, ProposalInput(
        type="YONETMELIK", article_action="ekle", new_value=NEW_RULE,
    ))
    proposals.reject(ctx, p, "18/30")
    ctx.commit()
    with pytest.raises(DomainError) as err:
        proposals.open_proposal(ctx, a, ProposalInput(
            type="YONETMELIK", article_action="ekle", new_value={**NEW_RULE, "baslik": "dolandırıcılık"},
        ))
    assert err.value.violations[0]["rule"] == "R6"


def test_regulation_proposal_validates_value_and_goes_to_slow_lane(ctx, client):
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
    # Başlıkta okunur ad; snake_case anahtar yalnızca detayda.
    assert p.title == "Yönetmelik: Red bekleme süresi"
    assert client.get(f"/proposals/{p.id}").json()["article"] == {
        "key": "red_bekleme", "kind": "sure", "title": "Red bekleme süresi"}
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
    # Açılış metni de rakip metinler gibi kendi defter kaydıyla mühürlenir.
    texts = proposals.closure_texts(later, p)
    assert len(texts) == 2 and all(t.ledger_hash for t in texts)
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
            type="KONU", addressee="takvim", reopens_topic_id=topic.id, body="Yeniden konuşalım.",
        ))
    p2 = proposals.open_proposal(ctx.at(ctx.now + timedelta(days=91)), a, ProposalInput(
        type="KONU", addressee="takvim", reopens_topic_id=topic.id, body="Yeniden konuşalım.",
    ))
    proposals.accept(ctx.at(ctx.now + timedelta(days=92)), p2)
    ctx.db.refresh(topic)
    assert topic.status == "OPEN"


# --- API ------------------------------------------------------------------------------------------


def test_api_objection_and_listing(client, ctx):
    a, b = make_user(ctx, "ayse"), make_user(ctx, "bora")
    r = client.post("/proposals", headers=headers_for(ctx, a), json={
        "type": "KONU", "addressee": "takvim", "title": "Metro saatleri", "body": "Metro gece de çalışsın.",
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



# --- R2'nin ters yönü: pay etkisi ve orantısızlık -------------------------------------------------

HALF_TO_ANKARA = {"butce": {"sehir:istanbul": 2000, "sehir:ankara": 5000}}
EQUAL_CUT = {"butce": {"sehir:istanbul": 3600, "sehir:ankara": 2700, "sehir:izmir": 1800}}


def budget_input(effect, title="İstanbul payının yarısı Ankara'ya"):
    return ProposalInput(type="KONU", addressee="takvim", title=title, body="Etkinlik bütçesi yeniden dağıtılsın.",
                         area_id="kent", scope_id="genel", resource_ids=["butce"],
                         share_effect=effect)


def test_general_budget_proposal_must_declare_structured_effect(ctx, client):
    a = make_user(ctx, "aylin", city="Ankara")
    r = client.post("/proposals", headers=headers_for(ctx, a), json={
        "type": "KONU", "addressee": "takvim", "title": "İstanbul payının yarısı Ankara'ya",
        "body": "İstanbul payının yarısı Ankara'ya aktarılsın.", "area_id": "kent",
        "scope_id": "genel", "resource_ids": ["butce"],
    })
    assert r.status_code == 422
    assert r.json()["violations"][0]["rule"] == "R2"
    assert "kapsam başına yeni paylarla bildirmeli" in r.json()["violations"][0]["message"]


def test_disproportionate_proposal_goes_to_slow_lane_and_oracle_lists_scopes(ctx, client):
    a = make_user(ctx, "aylin", city="Ankara")
    p = proposals.open_proposal(ctx, a, budget_input(HALF_TO_ANKARA))
    assert p.status == "QUEUED" and p.lane == "SLOW"  # sessiz onay veto kuralını atlayamaz
    assert "Orantısız etkilenen kapsam: İstanbul" in p.oracle_comment
    assert "İstanbul seçmenleri ayrıca oylar" in p.oracle_comment
    view = client.get(f"/proposals/{p.id}").json()
    assert view["concurrent_scopes"] == [{"id": "sehir:istanbul", "name": "İstanbul"}]
    [effect] = view["share_effect"]
    rows = {r["scope_id"]: r for r in effect["rows"]}
    assert (rows["sehir:istanbul"]["old"], rows["sehir:istanbul"]["new"]) == (4000, 2000)
    assert rows["sehir:istanbul"]["disproportionate"] is True
    assert rows["sehir:izmir"]["change_pct"] == "%0,0"
    assert rows["sehir:istanbul"]["change_pct"] == "-%50,0"  # Türkçe: eksi, yüzde, sayı


def test_equal_cut_stays_in_fast_lane_and_applies_shares_on_acceptance(ctx, client, ledger):
    a = make_user(ctx, "aylin", city="Ankara")
    p = proposals.open_proposal(ctx, a, budget_input(EQUAL_CUT, "Tüm şehirlerde %10 kesinti"))
    assert p.status == "SILENT"
    assert "orantısız etkilenen kapsam yok" in p.oracle_comment
    assert client.get(f"/proposals/{p.id}").json()["concurrent_scopes"] == []
    proposals.accept(ctx.at(p.deadline_at), p)
    ctx.commit()
    assert dict(ctx.graph.resource("butce").shares) == EQUAL_CUT["butce"]
    [rec] = ledger.of_type("PAY_DEGISTI")
    assert rec["payload"]["kaynak"] == "butce" and rec["payload"]["yeni"] == EQUAL_CUT["butce"]



# --- yönetmeliğin tabanı: değiştirilemez maddeler (R8) ----------------------------------------------


def test_lowering_regulation_threshold_to_half_is_rejected_at_opening(ctx, client):
    a = make_user(ctx, "ayse")
    r = client.post("/proposals", headers=headers_for(ctx, a), json={
        "type": "YONETMELIK", "article_key": "yonetmelik_esigi",
        "new_value": {"oran": "1/2", "karsilastirma": ">="},
    })
    assert r.status_code == 422
    [v] = r.json()["violations"]
    assert v["rule"] == "R8"
    assert v["message"].startswith("yonetmelik_esigi değiştirilemez izinli aralığın dışında: ≥ 2/3 – ≥ 3/4")
    # Tabanın üstüne çıkmak serbest.
    p = proposals.open_proposal(ctx, a, ProposalInput(
        type="YONETMELIK", article_key="yonetmelik_esigi", new_value={"oran": "3/4", "karsilastirma": ">="},
    ))
    assert p.status == "QUEUED"


def test_removing_the_right_of_dissent_is_rejected_at_opening(ctx, client):
    a = make_user(ctx, "ayse")
    for body in (
        {"type": "YONETMELIK", "article_key": "D3", "article_action": "kaldir"},
        {"type": "YONETMELIK", "article_key": "D3",
         "new_value": {"baslik": "Şerh yoktur.", "metin": "Kaybeden taraf şerh ekleyemez."}},
        {"type": "YONETMELIK", "article_key": "D7",
         "new_value": {"baslik": "Bu liste değişebilir.", "metin": "—"}},
    ):
        r = client.post("/proposals", headers=headers_for(ctx, a), json=body)
        assert r.status_code == 422, body
        [v] = r.json()["violations"]
        assert v["rule"] == "R8" and v["message"].startswith("Bu madde değiştirilemez"), v


def test_regulation_listing_marks_unchangeable_articles_and_ranges(ctx, client):
    listing = {a["key"]: a for a in client.get("/regulation").json()}
    assert listing["D1"]["unchangeable"] is True and listing["D1"]["kind"] == "temel_ilke"
    assert listing["D1"]["range"] is None
    assert listing["yonetmelik_esigi"]["unchangeable"] is False
    assert listing["yonetmelik_esigi"]["range"] == "≥ 2/3 – ≥ 3/4"
    assert listing["mahzen_kapasite"]["range"] == "30 – 300 başlık"
    assert ctx.graph.unchangeable_articles() == {f"D{i}" for i in range(1, 8)}


def test_every_out_of_range_parameter_change_is_rejected_at_opening(ctx):
    a = make_user(ctx, "ayse")
    for key, value in (("basit_cogunluk", {"oran": "3/4", "karsilastirma": ">="}),
                       ("sessiz_onay_suresi", {"saat": 6}),
                       ("itiraz_esigi", {"min": 3, "oran": "1/100", "aktiflik_gun": 30}),
                       ("musavir_esigi", {"deger": 100})):
        with pytest.raises(DomainError) as err:
            proposals.open_proposal(ctx, a, ProposalInput(type="YONETMELIK", article_key=key,
                                                          new_value=value))
        assert err.value.violations[0]["rule"] == "R8", key


def test_unchangeable_article_cannot_be_applied_even_directly(ctx):
    from mesveret.services import regulation

    with pytest.raises(DomainError):
        regulation.apply_change(ctx, "D6", {"baslik": "Defter düzenlenebilir.", "metin": "—"}, None)
