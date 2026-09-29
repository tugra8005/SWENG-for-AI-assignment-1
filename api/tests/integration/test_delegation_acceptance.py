"""Havale kabulü: bekleyen havale ağırlığa sayılmaz, kabul, ret, iade, "havale kabul etmiyorum",
kabul süresi ve zincir akışı. Pencereden hemen önce verilen kabulsüz havale hedefin gizli oyunu
açığa çıkaramaz."""

from datetime import timedelta

import pytest

from mesveret.db.models import DelegationRequest
from mesveret.errors import Conflict, DomainError, NotFound
from mesveret.services import decision_hour, delegation, profile
from mesveret.services.oracle import ORACLE_ID
from tests.integration.helpers import advance, delegate, headers_for
from tests.integration.test_decision_hour import close, item_of, queued_konu
from tests.integration.world import make_user

DAY = timedelta(days=1)


def edge(ctx, user, area=None):
    return next((e for e in ctx.graph.outgoing_delegations(user.id) if e.area_id == area), None)


def weight(ctx, user):
    return decision_hour.ballot(ctx, user)["items"][0]["weight"]


def test_pending_delegation_is_not_counted_and_the_vote_stays_with_the_giver(ctx, ledger):
    a, b, c = (make_user(ctx, n) for n in ("aylin", "baris", "ceren"))
    row = delegation.request_delegation(ctx, a, "baris", None)
    ctx.commit()
    assert row.status == "PENDING" and edge(ctx, a) is None
    assert row.decide_by == ctx.now + 7 * DAY  # havale_kabul_suresi
    assert ledger.of_type("HAVALE_BEKLIYOR")[-1]["payload"] == {
        "veren": "aylin", "alan": "baris", "alan_id": None, "son_kabul": row.decide_by.isoformat()}
    p = queued_konu(ctx, c)
    session = decision_hour.open_session(ctx)
    assert weight(ctx, b) == 1
    decision_hour.cast_vote(ctx, a, p.id, True)  # oy verende kaldı
    later = close(ctx, session)
    assert item_of(later, session, p).result["yes"] == 2  # aylin + Hâtif


def test_acceptance_starts_the_period_and_counts_the_weight(ctx, ledger):
    a, b = make_user(ctx, "aylin"), make_user(ctx, "baris")
    row = delegation.request_delegation(ctx, a, "baris", None)
    later = ctx.at(ctx.now + 3 * DAY)
    expires_at = delegation.accept_request(later, b, row.id)
    later.commit()
    e = edge(later, a)
    assert (e.since, e.expires_at) == (later.now, later.now + 180 * DAY) == (later.now, expires_at)
    assert ledger.of_type("HAVALE_KABUL")[-1]["payload"] == {
        "veren": "aylin", "alan": "baris", "alan_id": None, "bitis": expires_at.isoformat()}
    queued_konu(later, a)
    decision_hour.open_session(later)
    assert weight(later, b) == 2


def test_last_minute_delegation_does_not_reveal_a_secret_vote(ctx, ledger):
    """Saldırı: gizli oyu açığa çıkarmak için pencereden hemen önce havale vermek."""
    attacker, victim, c = (make_user(ctx, n) for n in ("saldirgan", "hedef", "ceren"))
    p = queued_konu(ctx, c)
    delegation.request_delegation(ctx, attacker, "hedef", None)
    ctx.commit()
    session = decision_hour.open_session(ctx.at(ctx.now + timedelta(minutes=1)))
    item = item_of(ctx, session, p)
    assert victim.id not in item.open_voters
    assert decision_hour.ballot(ctx, victim)["items"][0]["secrecy_note"].startswith("Oyunuz gizli")
    decision_hour.cast_vote(ctx, victim, p.id, False)
    later = close(ctx, session)
    votes = item_of(later, session, p).result["votes"]
    assert "hedef" not in {v.get("voter") for v in votes}
    assert "hedef" not in str([r["payload"] for r in ledger.of_type("OY_ACILDI")])


def test_accepted_delegation_makes_the_vote_open(ctx):
    a, b, c = (make_user(ctx, n) for n in ("aylin", "baris", "ceren"))
    delegate(ctx, a, "baris", None)
    p = queued_konu(ctx, c)
    session = decision_hour.open_session(ctx)
    assert b.id in item_of(ctx, session, p).open_voters


def test_rejection_drops_the_request_and_the_giver_sees_it(ctx, ledger, client):
    a, b = make_user(ctx, "aylin"), make_user(ctx, "baris")
    row = delegation.request_delegation(ctx, a, "baris", "ulasim")
    ctx.commit()
    mine = client.get("/delegations", headers=headers_for(ctx, b)).json()
    assert [(r["id"], r["from"], r["area_name"]) for r in mine["pending_received"]] == [
        (row.id, "aylin", "Ulaşım")]
    assert client.post(f"/delegations/requests/{row.id}/reject",
                       headers=headers_for(ctx, a)).status_code == 404  # yalnızca alan kişi
    r = client.post(f"/delegations/requests/{row.id}/reject", headers=headers_for(ctx, b))
    assert r.status_code == 200
    assert edge(ctx, a, "ulasim") is None
    assert ledger.of_type("HAVALE_RED")[-1]["payload"] == {
        "veren": "aylin", "alan": "baris", "alan_id": "ulasim", "neden": "reddedildi"}
    given = client.get("/delegations", headers=headers_for(ctx, a)).json()
    assert given["pending_given"] == []
    assert [(o["target"], o["label"]) for o in given["outcomes"]] == [("baris", "reddedildi")]


def test_unaccepted_request_expires_after_havale_kabul_suresi(ctx, ledger):
    a, _b = make_user(ctx, "aylin"), make_user(ctx, "baris")
    row = delegation.request_delegation(ctx, a, "baris", None)
    ctx.commit()
    later = advance(ctx, 8 * DAY)
    later.db.refresh(row)
    assert row.status == "EXPIRED" and row.decided_at == row.decide_by
    rec = ledger.of_type("HAVALE_RED")[-1]
    assert rec["payload"]["neden"] == "kabul_suresi_doldu"
    assert rec["ts"].startswith(row.decide_by.strftime("%Y-%m-%dT%H:%M"))  # vade anında
    assert [o["label"] for o in delegation.my_delegations(later, a)["outcomes"]] == [
        "kabul süresi doldu"]


def test_recipient_can_return_an_accepted_delegation_except_in_the_window(ctx, ledger, client):
    a, b, c = (make_user(ctx, n) for n in ("aylin", "baris", "ceren"))
    delegate(ctx, a, "baris", None)
    queued_konu(ctx, c)
    session = decision_hour.open_session(ctx)
    r = client.post("/delegations/return", json={"giver": "aylin", "area_id": None},
                    headers=headers_for(ctx, b))
    assert r.status_code == 409 and "kilitli" in r.json()["detail"]
    later = close(ctx, session)
    with pytest.raises(NotFound):
        delegation.return_delegation(later, c, "aylin", None)  # ceren'e verilmemiş
    delegation.return_delegation(later, b, "aylin", None)
    later.commit()
    assert edge(later, a) is None  # oy sahibine döndü
    assert ledger.of_type("HAVALE_IADE")[-1]["payload"] == {
        "veren": "aylin", "alan": "baris", "alan_id": None, "not": "Oy sahibine döndü."}
    assert [o["label"] for o in delegation.my_delegations(later, a)["outcomes"]] == ["iade edildi"]


def test_refusing_delegations_blocks_new_ones(ctx, client):
    a, b = make_user(ctx, "aylin"), make_user(ctx, "baris")
    r = client.put("/delegations/preference", json={"refuses": True}, headers=headers_for(ctx, b))
    assert r.status_code == 200
    ctx.db.refresh(b)
    with pytest.raises(DomainError) as err:
        delegation.request_delegation(ctx, a, "baris", None)
    assert err.value.message == "baris havale kabul etmiyor."
    assert profile.public_profile(ctx, b)["refuses_delegations"] is True
    delegation.set_refusal(ctx, b, False)
    assert delegation.request_delegation(ctx, a, "baris", None).status == "PENDING"


def test_chain_flows_through_an_accepted_delegation_without_further_consent(ctx):
    """c, b'nin havalesini kabul etti: a'nın b'ye verdiği havale c'ye c'nin onayı olmadan ulaşır."""
    a, b, c, d = (make_user(ctx, n) for n in ("aylin", "baris", "ceren", "deniz"))
    delegate(ctx, b, "ceren", None)
    row = delegation.request_delegation(ctx, a, "baris", None)
    delegation.accept_request(ctx, b, row.id)  # yalnızca b kabul eder
    assert delegation.my_delegations(ctx, c)["pending_received"] == []
    queued_konu(ctx, d)
    decision_hour.open_session(ctx)
    assert weight(ctx, c) == 3


def test_existing_delegation_stays_until_the_new_one_is_accepted(ctx):
    a = make_user(ctx, "aylin")
    b, c = make_user(ctx, "baris"), make_user(ctx, "ceren")
    delegate(ctx, a, "baris", None)
    first = ctx.db.query(DelegationRequest).filter_by(giver_id=a.id, status="ACCEPTED").one()
    row = delegation.request_delegation(ctx, a, "ceren", None)
    assert edge(ctx, a).target_id == b.id  # bekleyen yeni havale eskisini düşürmez
    delegation.accept_request(ctx, c, row.id)
    assert edge(ctx, a).target_id == c.id
    ctx.db.refresh(first)
    assert first.status == "ENDED"


def test_renewal_needs_no_new_acceptance(ctx):
    a, b = make_user(ctx, "aylin"), make_user(ctx, "baris")
    delegate(ctx, a, "baris", None)
    later = ctx.at(ctx.now + 30 * DAY)
    delegation.renew_delegation(later, a, None)
    assert edge(later, a).expires_at == later.now + 180 * DAY
    assert delegation.my_delegations(later, b)["pending_received"] == []


def test_cycle_is_checked_again_when_accepting(ctx):
    a, b = make_user(ctx, "aylin"), make_user(ctx, "baris")
    row = delegation.request_delegation(ctx, a, "baris", None)  # beklerken döngü yok
    delegate(ctx, b, "aylin", None)  # b → a kabul edildi
    with pytest.raises(DomainError) as err:
        delegation.accept_request(ctx, b, row.id)
    assert err.value.message.startswith("R4: Bu havaleyi kabul etmek döngü oluşturur")
    assert edge(ctx, a) is None


def test_pending_request_can_be_cancelled_and_a_new_one_replaces_it(ctx):
    a = make_user(ctx, "aylin")
    make_user(ctx, "baris")
    make_user(ctx, "ceren")
    first = delegation.request_delegation(ctx, a, "baris", "ulasim")
    second = delegation.request_delegation(ctx, a, "ceren", "ulasim")
    assert first.status == "CANCELLED" and second.status == "PENDING"
    delegation.cancel_request(ctx, a, second.id)
    assert second.status == "CANCELLED"
    with pytest.raises(Conflict):
        delegation.accept_request(ctx, ctx.db.get(type(a), second.target_id), second.id)


def test_oracle_accepts_by_rule(ctx):
    a = make_user(ctx, "aylin")
    row = delegation.request_delegation(ctx, a, "Hâtif", "kultur")
    assert row.status == "ACCEPTED" and edge(ctx, a, "kultur").target_id == ORACLE_ID
