from datetime import timedelta

from sqlalchemy import select

from mesveret.db.models import Notification, Topic
from mesveret.services import proposals
from mesveret.services.proposals import ProposalInput
from tests.integration.helpers import headers_for, post
from tests.integration.world import make_user


def _accepted_topic(ctx, user, *, addressee, scope="genel", title="Bisiklet yolları",
                    area="ulasim", body="Ana caddelere korunaklı bisiklet yolu yapılsın."):
    p = proposals.open_proposal(ctx, user, ProposalInput(
        type="KONU", title=title, body=body, area_id=area, scope_id=scope, addressee=addressee))
    proposals.accept(ctx.at(p.deadline_at), p)
    ctx.commit()
    topic = ctx.db.execute(select(Topic).where(Topic.accepted_proposal_id == p.id)).scalar_one()
    return p, topic


def test_institution_topic_sends_a_petition_on_acceptance(ctx, client, ledger):
    a = make_user(ctx, "ayse")
    p, topic = _accepted_topic(ctx, a, addressee="belediye:istanbul", scope="sehir:istanbul",
                               title="Semt pazarları", area="kent",
                               body="Semt pazarlarının saatleri mahalleye göre ayarlansın.")
    view = client.get(f"/topics/{topic.id}").json()
    assert view["addressee"]["name"] == "İstanbul Büyükşehir Belediyesi"
    [pet] = view["petitions"]
    assert pet["number"] == "MŞV-2026-0001" and pet["kind"] == "TALEP"
    assert [r["status"] for r in pet["recipients"]] == ["BEKLIYOR"]

    full = client.get(f"/petitions/{pet['id']}").json()
    assert full["text"] == "Semt pazarlarının saatleri mahalleye göre ayarlansın."
    assert full["signature"].startswith("Sessiz onay: itiraz süresi 0 itirazla doldu")
    assert full["scope"] == "İstanbul" and full["proposer"] == "ayse"
    rec = ledger.of_type("DILEKCE_ILETILDI")[0]["payload"]
    assert rec["evrak"] == "MŞV-2026-0001"
    assert rec["alicilar"] == ["İstanbul Büyükşehir Belediyesi"]
    assert len(full["ledger_hash"]) == 64

    note = ctx.db.execute(select(Notification).where(Notification.kind == "DILEKCE")).scalar_one()
    assert note.user_id == a.id and note.title == "Dilekçeniz iletildi"
    assert client.get(f"/proposals/{p.id}").json()["addressee"]["kind"] == "KURUM"


def test_calendar_topic_sends_no_petition(ctx, client):
    a = make_user(ctx, "ayse")
    _, topic = _accepted_topic(ctx, a, addressee="takvim", title="Film günleri", area="sinema",
                               body="Ayda bir film.")
    assert client.get(f"/topics/{topic.id}").json()["petitions"] == []
    assert client.get("/petitions").json() == []


def test_all_municipalities_expand_to_each_city(ctx, client):
    a = make_user(ctx, "ayse")
    _, topic = _accepted_topic(ctx, a, addressee="belediyeler")
    [pet] = client.get(f"/topics/{topic.id}").json()["petitions"]
    assert [r["name"] for r in pet["recipients"]] == [
        "Ankara Büyükşehir Belediyesi", "İstanbul Büyükşehir Belediyesi",
        "İzmir Büyükşehir Belediyesi"]


def test_r9_rejects_out_of_jurisdiction_addressee_at_opening(ctx, client):
    a = make_user(ctx, "ayse")
    r = client.post("/proposals", headers=headers_for(ctx, a), json={
        "type": "KONU", "title": "Metro", "body": "Gece seferi.", "area_id": "ulasim",
        "scope_id": "sehir:istanbul", "addressee": "bakanlik:ulastirma",
    })
    assert r.status_code == 422
    assert [v["rule"] for v in r.json()["violations"]] == ["R9"]
    r = client.post("/proposals", headers=headers_for(ctx, a), json={
        "type": "KONU", "title": "Metro", "body": "Gece seferi.", "area_id": "ulasim",
        "scope_id": "genel",
    })
    assert r.json()["violations"][0]["message"].startswith("Muhatap seçilmeli")
    listing = {x["id"]: x for x in client.get("/addressees?scope_id=sehir:istanbul").json()}
    assert listing["belediye:istanbul"]["allowed"] and listing["takvim"]["allowed"]
    assert not listing["belediye:ankara"]["allowed"]
    assert not listing["bakanlik:kultur"]["allowed"]


def test_subtopic_inherits_parent_addressee(ctx):
    a = make_user(ctx, "ayse")
    _, parent = _accepted_topic(ctx, a, addressee="bakanlik:ulastirma", title="Metro saatleri")
    p = proposals.open_proposal(ctx, a, ProposalInput(
        type="ALT_KONU", title="Gece seferi", body="Hafta sonu gece seferi.", area_id="ulasim",
        scope_id="genel", parent_topic_id=parent.id))
    assert p.payload["addressee"] == "bakanlik:ulastirma"


def test_reply_by_participant_with_scan_and_rules(ctx, client, ledger):
    a, b, c = make_user(ctx, "ayse"), make_user(ctx, "bora"), make_user(ctx, "cem")
    _, topic = _accepted_topic(ctx, a, addressee="bakanlik:ulastirma", title="Gece metrosu")
    post(ctx, b, topic, "Ben de destekliyorum.")
    pet_id = client.get(f"/topics/{topic.id}").json()["petitions"][0]["id"]
    body = {"recipient_id": "bakanlik:ulastirma", "replied_on": "2026-10-05",
            "text": "Talebiniz ilgili genel müdürlüğe iletilmiştir.", "reference": "E-123"}
    later = ctx.at(ctx.now + timedelta(days=7))
    from mesveret import clock

    clock.set_now(ctx.db, later.now)
    ctx.db.commit()

    r = client.post(f"/petitions/{pet_id}/replies", headers=headers_for(ctx, c), json=body)
    assert r.status_code == 403  # konuya katılmamış
    r = client.post(f"/petitions/{pet_id}/replies", headers=headers_for(ctx, b),
                    json={**body, "replied_on": "2026-12-01"})
    assert r.status_code == 422 and "bugünden sonra" in r.json()["detail"]
    r = client.post(f"/petitions/{pet_id}/replies", headers=headers_for(ctx, b),
                    json={**body, "replied_on": "2026-09-01"})
    assert "önce olamaz" in r.json()["detail"]
    r = client.post(f"/petitions/{pet_id}/replies", headers=headers_for(ctx, b), json=body)
    assert r.status_code == 201, r.text
    assert client.post(f"/petitions/{pet_id}/replies", headers=headers_for(ctx, b),
                       json=body).status_code == 409

    full = client.get(f"/petitions/{pet_id}").json()
    [rec] = full["recipients"]
    assert rec["status"] == "YANITLANDI"
    assert rec["reply"]["entered_by"] == "bora" and rec["reply"]["reference"] == "E-123"
    assert ledger.of_type("DILEKCE_YANITI")[0]["payload"]["isleyen"] == "bora"
    notes = ctx.db.execute(select(Notification).where(
        Notification.title == "T.C. Ulaştırma ve Altyapı Bakanlığı yanıt verdi")).scalars().all()
    assert [n.user_id for n in notes] == [a.id]  # yanıtı işleyen bildirim almaz


def test_unanswered_petition_is_overdue_after_thirty_days(ctx, client):
    a = make_user(ctx, "ayse")
    _, topic = _accepted_topic(ctx, a, addressee="bakanlik:cevre", title="Kıyı temizliği",
                               area="kent", body="Kıyılar düzenli temizlensin.")
    from mesveret import clock

    pet = client.get(f"/topics/{topic.id}").json()["petitions"][0]
    clock.set_now(ctx.db, ctx.now + timedelta(days=29))
    ctx.db.commit()
    assert client.get(f"/petitions/{pet['id']}").json()["recipients"][0]["status"] == "BEKLIYOR"
    clock.set_now(ctx.db, ctx.now + timedelta(days=31))
    ctx.db.commit()
    assert client.get(f"/petitions/{pet['id']}").json()["recipients"][0]["status"] == "SURE_DOLDU"


def test_decision_of_institution_topic_is_sent_as_decision_notice(ctx, client):
    a = make_user(ctx, "ayse")
    _, topic = _accepted_topic(ctx, a, addressee="belediye:ankara", scope="genel",
                               title="Ankara parkları", area="kent", body="Parklar 22:00'de.")
    k = proposals.open_proposal(ctx, a, ProposalInput(
        type="KAPANIS", target_topic_id=topic.id, body="Parklar her gün 22:00'de kapansın."))
    assert k.payload["addressee"] == "belediye:ankara"
    text_id = proposals.closure_texts(ctx, k)[0].id
    proposals.accept(ctx, k, winner_text_id=text_id)
    ctx.commit()
    pets = client.get(f"/topics/{topic.id}").json()["petitions"]
    assert [p["kind"] for p in pets] == ["TALEP", "KARAR"]
    full = client.get(f"/petitions/{pets[1]['id']}").json()
    assert full["subject"] == "Ankara parkları: karar bildirimi"
    assert full["text"] == "Parklar her gün 22:00'de kapansın."
