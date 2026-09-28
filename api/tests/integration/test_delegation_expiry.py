"""Havale süresi: bitiş, yenileme, madde değişikliği, zincirin kopması, anlık görüntü, uyarı."""

from datetime import timedelta

import pytest

from mesveret.domain.counselor import counselor_areas
from mesveret.errors import Conflict, NotFound
from mesveret.services import decision_hour, delegation
from tests.integration.helpers import advance, headers_for
from tests.integration.test_decision_hour import close, queued_konu
from tests.integration.world import make_user

DAY = timedelta(days=1)


def edge(ctx, user, area=None):
    return next((e for e in ctx.graph.outgoing_delegations(user.id) if e.area_id == area), None)


def test_delegation_expires_after_havale_suresi_and_the_vote_returns(ctx, ledger):
    a, b = make_user(ctx, "aylin"), make_user(ctx, "baris")
    delegation.set_delegation(ctx, a, "baris", None)
    ctx.commit()
    e = edge(ctx, a)
    assert (e.since, e.expires_at) == (ctx.now, ctx.now + 180 * DAY)
    assert ledger.of_type("HAVALE_VERILDI")[-1]["payload"]["bitis"] == e.expires_at.isoformat()

    later = advance(ctx, 179 * DAY)
    assert edge(later, a) is not None
    later = advance(later, 2 * DAY)
    assert edge(later, a) is None  # oy sahibine döndü
    assert delegation.my_delegations(later, a)["given"] == []
    assert later.graph.incoming_delegations(b.id) == {}
    [rec] = ledger.of_type("HAVALE_SURESI_DOLDU")
    assert rec["payload"] | {"verildi": None} == {
        "veren": "aylin", "alan": "baris", "alan_id": None, "verildi": None,
        "bitis": e.expires_at.isoformat(), "not": "Oy sahibine döndü.",
    }
    assert rec["ts"].startswith(e.expires_at.strftime("%Y-%m-%dT%H:%M"))  # vade anında işlendi


def test_changing_havale_suresi_affects_only_new_and_renewed_delegations(ctx):
    a, c = make_user(ctx, "aylin"), make_user(ctx, "ceren")
    make_user(ctx, "baris")
    delegation.set_delegation(ctx, a, "baris", None)
    ctx.graph.set_article("havale_suresi", {"gun": 30})  # oylamayla değişmiş gibi
    ctx.invalidate_regulation()
    before = edge(ctx, a).expires_at
    delegation.set_delegation(ctx, c, "baris", None)
    assert edge(ctx, a).expires_at == before == ctx.now + 180 * DAY  # mevcut havale değişmez
    assert edge(ctx, c).expires_at == ctx.now + 30 * DAY  # yeni havale yeni süreyle
    later = ctx.at(ctx.now + 5 * DAY)
    delegation.renew_delegation(later, a, None)
    assert edge(later, a).expires_at == later.now + 30 * DAY  # yenileme de yeni süreyle


def test_renewal_restarts_the_period_is_logged_and_locked_in_the_window(ctx, ledger):
    a = make_user(ctx, "aylin")
    make_user(ctx, "baris")
    delegation.set_delegation(ctx, a, "baris", None)
    ctx.commit()
    first = edge(ctx, a)
    later = advance(ctx, 100 * DAY)
    new_end = delegation.renew_delegation(later, a, None)
    later.commit()
    e = edge(later, a)
    assert new_end == e.expires_at == later.now + 180 * DAY
    assert (e.target_id, e.since) == (first.target_id, first.since)  # hedef ve veriliş aynı
    payload = ledger.of_type("HAVALE_YENILENDI")[-1]["payload"]
    assert (payload["onceki_bitis"], payload["bitis"]) == (
        first.expires_at.isoformat(), new_end.isoformat())
    later = advance(later, 90 * DAY)  # ilk bitişi (gün 180) geçti; yenilenen havale yaşıyor
    assert edge(later, a) is not None
    with pytest.raises(NotFound):
        delegation.renew_delegation(later, a, "sinema")
    decision_hour.open_session(later)
    with pytest.raises(Conflict):
        delegation.renew_delegation(later, a, None)


def test_expired_middle_link_breaks_the_chain_at_that_point(ctx):
    a, b, c = (make_user(ctx, n) for n in ("aylin", "baris", "ceren"))
    delegation.set_delegation(ctx, b, "ceren", "ulasim")  # gün 0: b → c (Ulaşım)
    ctx.commit()
    later = advance(ctx, 10 * DAY)
    delegation.set_delegation(later, a, "baris", None)  # gün 10: a → b (genel)
    later.commit()
    later = advance(later, 171 * DAY)  # gün 181: b → c doldu, a → b gün 190'a kadar geçerli
    assert edge(later, b, "ulasim") is None and edge(later, a) is not None
    queued_konu(later, a)
    decision_hour.open_session(later)
    weights = {u.nickname: decision_hour.ballot(later, u)["items"][0] for u in (a, b, c)}
    assert weights["ceren"]["weight"] == 1  # zincir b'de koptu
    assert weights["baris"]["weight"] == 2  # a'nın havalesi b'de biter
    assert weights["aylin"]["can_vote"] is False


def test_delegation_valid_at_window_opening_counts_even_if_it_expires_during_the_window(ctx, ledger):
    a, b = make_user(ctx, "aylin"), make_user(ctx, "baris")
    delegation.set_delegation(ctx, a, "baris", None)
    ctx.graph.renew_delegation(a.id, None, ctx.now + timedelta(minutes=30))  # pencere içinde biter
    ctx.commit()
    p = queued_konu(ctx, a)
    session = decision_hour.open_session(ctx)
    later = advance(ctx, timedelta(minutes=45))
    assert edge(later, a) is None  # zamanlayıcı pencere içinde süreyi işledi
    assert len(ledger.of_type("HAVALE_SURESI_DOLDU")) == 1
    decision_hour.cast_vote(later, b, p.id, True)
    after = close(later, session)
    result = decision_hour.session_view(after, session.id)["items"][0]["result"]
    assert next(v for v in result["votes"] if v["voter"] == "baris")["weight"] == 2


def test_snapshot_skips_a_delegation_whose_end_passed_before_the_scheduler_ran(ctx):
    a, b = make_user(ctx, "aylin"), make_user(ctx, "baris")
    ctx.graph.set_delegation(a.id, b.id, None, ctx.now - 200 * DAY, ctx.now - timedelta(minutes=1))
    ctx.commit()
    queued_konu(ctx, a)
    decision_hour.open_session(ctx)
    assert decision_hour.ballot(ctx, b)["items"][0]["weight"] == 1
    assert decision_hour.ballot(ctx, a)["items"][0]["can_vote"] is True


def test_warning_for_delegations_ending_within_14_days(ctx, client):
    a, b = make_user(ctx, "aylin"), make_user(ctx, "baris")
    delegation.set_delegation(ctx, a, "baris", None)
    ctx.commit()
    mid = advance(ctx, 100 * DAY)
    assert delegation.my_delegations(mid, a)["expiring_given"] == []
    late = advance(mid, 170 * DAY - 100 * DAY)
    mine = delegation.my_delegations(late, a)
    [g] = mine["expiring_given"]
    assert (g["target"], g["days_left"], mine["warning_days"]) == ("baris", 10, 14)
    [r] = delegation.my_delegations(late, b)["expiring_received"]
    assert (r["from"], r["days_left"]) == ("aylin", 10)
    body = client.get("/me/profile", headers=headers_for(late, a)).json()
    assert body["expiring_given"][0]["target"] == "baris"
    assert body["delegations_given"][0]["days_left"] == 10
    body = client.get("/me/profile", headers=headers_for(late, b)).json()
    assert body["delegations_received_list"][0]["from"] == "aylin"
    # Tek tıklamayla yenileme: uyarı kalkar.
    r = client.post("/delegations/renew", json={"area_id": None}, headers=headers_for(late, a))
    assert r.status_code == 200
    assert client.get("/delegations", headers=headers_for(late, a)).json()["expiring_given"] == []


def test_counselor_label_fades_as_delegations_expire_but_renewed_trust_stays(ctx, client):
    musavir = make_user(ctx, "musavir")
    givers = [make_user(ctx, f"yurttas{i}") for i in range(5)]
    for u in givers:
        delegation.set_delegation(ctx, u, "musavir", "sinema")
    ctx.commit()
    assert "Müşavir" in client.get("/users/musavir").json()["roles"]
    later = advance(ctx, 100 * DAY)
    delegation.renew_delegation(later, givers[0], "sinema")
    later.commit()
    later = advance(later, 81 * DAY)
    incoming = later.graph.incoming_delegations(musavir.id)
    assert incoming == {"sinema": 1}  # yalnızca yenilenen kaldı
    assert counselor_areas(incoming, later.reg) == []
    assert "Müşavir" not in client.get("/users/musavir").json()["roles"]
