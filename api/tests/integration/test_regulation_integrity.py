"""Yönetmeliğin defterdeki hash'i: sessiz değişiklik engellenmez ama tespit edilir."""

from dataclasses import replace

from mesveret.domain import regulation as reg_domain
from mesveret.services import decision_hour, proposals, regulation
from mesveret.services.proposals import ProposalInput
from tests.integration.helpers import mature
from tests.integration.world import make_user


def _verify(client) -> dict:
    return client.get("/ledger/verify").json()["yonetmelik"]


def test_installation_records_a_baseline_and_verify_agrees(ctx, client, ledger):
    body = _verify(client)
    assert body["status"] == "tutarli" and body["differences"] == []
    [rec] = ledger.of_type("YONETMELIK_DURUMU")
    assert rec["payload"]["oturum"] is None
    assert rec["payload"]["hash"] == regulation.state_hash(regulation.state(ctx))
    durum = rec["payload"]["durum"]
    assert durum["D3"]["degistirilemez"] is True
    assert durum["sessiz_onay_suresi"] == {
        "deger": {"saat": 24}, "degistirilemez": False, "izinli_aralik": "12 saat – 72 saat",
        "izinli_sinirlar": {"sure": ["12", "72"]}}
    assert durum["basit_cogunluk"]["izinli_sinirlar"] == {"oran": ["> 1/2", ">= 2/3"]}


def test_every_session_close_records_the_regulation(ctx, client, ledger):
    voters = [make_user(ctx, f"secmen{i}") for i in range(3)]
    p = mature(ctx, proposals.open_proposal(ctx, voters[0], ProposalInput(
        type="YONETMELIK", article_key="red_bekleme", new_value={"gun": 45},
    )))
    session = decision_hour.open_session(ctx)
    for v in voters:
        decision_hour.cast_vote(ctx, v, p.id, True)
    later = ctx.at(session.closes_at)
    decision_hour.close_session(later, session)
    later.commit()
    last = ledger.of_type("YONETMELIK_DURUMU")[-1]["payload"]
    assert last["oturum"] == session.id
    assert last["durum"]["red_bekleme"]["deger"] == {"gun": 45}  # oylanan değişiklik kayıtta
    assert _verify(client)["status"] == "tutarli"


def test_silent_operator_change_is_detected(ctx, client, monkeypatch):
    ctx.commit()
    # Oylamasız doğrudan yazım (ör. veritabanına elle müdahale) ve kodda aralığın genişletilmesi.
    ctx.graph.set_article("sessiz_onay_suresi", {"saat": 2})
    wide = replace(reg_domain.DEFAULT_ARTICLES["adres_bekleme"],
                   allowed=reg_domain._days(0, 3650))
    monkeypatch.setitem(reg_domain.DEFAULT_ARTICLES, "adres_bekleme", wide)
    body = _verify(client)
    assert body["status"] == "farkli"
    assert body["differences"] == ["adres_bekleme", "sessiz_onay_suresi"]
    assert body["recorded_hash"] != body["current_hash"]
    assert "oylamasız" in body["message"]


def test_widening_a_bound_without_touching_its_text_is_detected(ctx, client, monkeypatch):
    ctx.commit()
    article = reg_domain.DEFAULT_ARTICLES["orantisizlik_esigi"]
    wide = replace(article, allowed=reg_domain._num(5, 100, article.allowed["deger"].text))
    monkeypatch.setitem(reg_domain.DEFAULT_ARTICLES, "orantisizlik_esigi", wide)
    assert reg_domain.describe_range("orantisizlik_esigi") == "5 – 30 yüzde puanı"  # metin aynı
    body = _verify(client)
    assert body["status"] == "farkli" and body["differences"] == ["orantisizlik_esigi"]
