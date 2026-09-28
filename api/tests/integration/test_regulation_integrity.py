"""Yönetmeliğin defterdeki hash'i: sessiz değişiklik engellenmez ama tespit edilir."""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from mesveret.db.models import RegulationChange
from mesveret.domain import regulation as reg_domain
from mesveret.errors import DomainError
from mesveret.main import create_app
from mesveret.routers import devtools as dev_router
from mesveret.services import decision_hour, devtools, proposals, regulation
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


def test_tamper_tool_writes_silently_and_verify_lists_the_article(ctx, client, ledger):
    ctx.commit()
    before = len(ledger.records)
    out = devtools.tamper_regulation(ctx, "sessiz_onay_suresi", {"saat": 2})
    assert out["old"] == {"saat": 24} and out["new"] == {"saat": 2}
    assert out["outside"] == ["12 saat – 72 saat"]  # R8 atlandı
    assert ctx.graph.articles()["sessiz_onay_suresi"] == {"saat": 2}
    assert len(ledger.records) == before  # defter kaydı yok
    assert not ctx.db.execute(select(RegulationChange)).scalars().all()  # geçmiş kaydı yok
    body = _verify(client)
    assert body["status"] == "farkli" and body["differences"] == ["sessiz_onay_suresi"]
    assert "sessiz_onay_suresi" in body["message"]


def test_tamper_tool_still_rejects_values_the_app_cannot_read(ctx):
    with pytest.raises(DomainError):
        devtools.tamper_regulation(ctx, "sessiz_onay_suresi", {"saat": "iki"})
    with pytest.raises(DomainError):
        devtools.tamper_regulation(ctx, "yok_boyle_madde", {"deger": 1})


def test_tamper_endpoint_on_the_local_dev_server(ctx, Session, graph, ledger, settings):
    app = create_app(settings=settings, graph=graph, ledger=ledger, sessionmaker=Session,
                     with_lifespan=False)
    app.include_router(dev_router.router)
    c = TestClient(app)
    r = c.post("/_dev/tamper-regulation", json={"key": "adres_bekleme", "value": {"gun": 1000}})
    assert r.status_code == 200 and r.json()["outside"] == ["0 – 180 gün"]
    assert _verify(c)["differences"] == ["adres_bekleme"]


def test_tamper_cli_command(ctx, client, monkeypatch):
    from contextlib import contextmanager

    from typer.testing import CliRunner

    from mesveret import cli

    ctx.commit()

    @contextmanager
    def fake_ctx():
        yield ctx

    monkeypatch.setattr(cli, "_ctx", fake_ctx)
    runner = CliRunner()
    out = runner.invoke(cli.app, ["tamper-regulation", "sessiz_onay_suresi", '{"saat": 2}'])
    assert out.exit_code == 0, out.output
    assert 'sessiz_onay_suresi: {"saat": 24} → {"saat": 2}' in out.output
    assert "izinli aralığın dışında: 12 saat – 72 saat (R8 atlandı)" in out.output
    assert "Yönetmelik bütünlüğü: FARKLI." in out.output
    assert _verify(client)["differences"] == ["sessiz_onay_suresi"]
    bad = runner.invoke(cli.app, ["tamper-regulation", "sessiz_onay_suresi", "saat=2"])
    assert bad.exit_code == 1 and "JSON" in bad.output
    back = runner.invoke(cli.app, ["tamper-regulation", "sessiz_onay_suresi", '{"saat": 24}'])
    assert back.exit_code == 0 and _verify(client)["status"] == "tutarli"
    assert "Yönetmelik bütünlüğü: TUTARLI." in back.output
