"""Yönetmeliğin defterdeki hash'i: sessiz değişiklik engellenmez ama tespit edilir."""

from dataclasses import replace
from datetime import timedelta
from fractions import Fraction

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


# --- kapanışta tespit ve geri alma ---------------------------------------------------------------


def _session_round(ctx, *, change: tuple[str, dict] | None = None, tag: str = "a", during=None):
    """Bir Karar Saati oturumu açar ve kapatır; ``change`` verilirse o yönetmelik önerisi kabul edilir,
    ``during`` verilirse pencere açıkken çalıştırılır."""
    voters = [make_user(ctx, f"secmen_{tag}{i}") for i in range(3)]
    p = None
    if change:
        p = mature(ctx, proposals.open_proposal(ctx, voters[0], ProposalInput(
            type="YONETMELIK", article_key=change[0], new_value=change[1],
        )))
    session = decision_hour.open_session(ctx)
    if p is not None:
        for v in voters:
            decision_hour.cast_vote(ctx, v, p.id, True)
    if during is not None:
        during(ctx)
        ctx.commit()
    later = ctx.at(session.closes_at)
    decision_hour.close_session(later, session)
    later.commit()
    return later, session


def _tamper(key, value):
    def run(c):
        devtools.tamper_regulation(c, key, value)
        assert c.graph.articles()[key] == value
    return run


def test_close_detects_the_silent_change_reverts_it_and_history_stays(ctx, client, ledger):
    ctx.commit()
    # Pencere açıkken yapılan değişiklik: açılış görmez, kapanış yakalar.
    later, session = _session_round(ctx, during=_tamper("sessiz_onay_suresi", {"saat": 2}))
    assert later.graph.articles()["sessiz_onay_suresi"] == {"saat": 24}  # geri alındı
    [found] = ledger.of_type("OYLAMASIZ_DEGISIKLIK")
    p = found["payload"]
    assert (p["madde"], p["kayittaki"]["deger"], p["bulunan"]["deger"], p["oturum"], p["asama"]) == (
        "sessiz_onay_suresi", {"saat": 24}, {"saat": 2}, session.id, "kapanis")
    assert p["tespit_zamani"] == later.now.isoformat()
    [revert] = ledger.of_type("OYLAMASIZ_DEGISIKLIK_GERI_ALINDI")
    assert revert["payload"]["geri_alinan"] == ["deger"]
    assert revert["seq"] > found["seq"]
    # Sıra: tespit → geri alma → oturum kapanışı → yeni durum kaydı.
    types = [r["type"] for r in ledger.records[found["seq"] - 1:]]
    assert types[:2] == ["OYLAMASIZ_DEGISIKLIK", "OYLAMASIZ_DEGISIKLIK_GERI_ALINDI"]
    assert types[-2:] == ["OTURUM_KAPANDI", "YONETMELIK_DURUMU"]

    body = _verify(client)
    assert body["status"] == "tutarli"
    [item] = body["history"]
    assert (item["madde"], item["kayittaki"], item["bulunan"], item["alanlar"]) == (
        "sessiz_onay_suresi", {"saat": 24}, {"saat": 2}, ["deger"])
    assert (item["oturum"], item["asama"], item["geri_alinan"], item["tur"]) == (
        session.id, "kapanis", ["deger"], "sure")

    # Geçmiş hiç boşalmaz: ikinci oturumda başka bir değişiklik, ikisi de listede.
    _session_round(later, tag="b", during=_tamper("adres_bekleme", {"gun": 1000}))
    history = _verify(client)["history"]
    assert [h["madde"] for h in history] == ["adres_bekleme", "sessiz_onay_suresi"]


def test_silent_change_on_an_article_the_session_changes_by_vote(ctx, ledger):
    ctx.commit()
    devtools.tamper_regulation(ctx, "red_bekleme", {"gun": 8})
    later, _ = _session_round(ctx, change=("red_bekleme", {"gun": 45}))
    assert later.graph.articles()["red_bekleme"] == {"gun": 45}  # önce geri alındı, sonra oylanan
    [found] = ledger.of_type("OYLAMASIZ_DEGISIKLIK")
    assert found["payload"]["bulunan"]["deger"] == {"gun": 8}
    [change] = later.db.execute(select(RegulationChange)).scalars().all()
    assert (change.old_value, change.new_value) == ({"gun": 30}, {"gun": 45})


def test_silent_flag_removal_and_content_rule_changes_are_reverted(ctx, client, ledger):
    ctx.commit()
    ik2 = ctx.graph.articles()["IK-2"]
    ctx.graph.clear_unchangeable("D3")  # Şerh güvencesi sessizce değiştirilebilir yapıldı
    ctx.graph.delete_article("IK-2")  # kural sessizce kaldırıldı
    ctx.graph.set_article("IK-9", {**ik2, "baslik": "Sessiz kural"})  # kural sessizce eklendi
    assert set(_verify(client)["differences"]) == {"D3", "IK-2", "IK-9"}
    later, _ = _session_round(ctx)
    assert "D3" in later.graph.unchangeable_articles()
    assert later.graph.articles()["IK-2"] == ik2
    assert "IK-9" not in later.graph.articles()
    reverts = {r["payload"]["madde"]: r["payload"]["geri_alinan"]
               for r in ledger.of_type("OYLAMASIZ_DEGISIKLIK_GERI_ALINDI")}
    assert reverts == {"D3": ["degistirilemez"], "IK-2": ["deger"], "IK-9": ["deger"]}
    assert _verify(client)["status"] == "tutarli"


def test_code_level_range_change_is_recorded_but_cannot_be_reverted(ctx, client, ledger, monkeypatch):
    ctx.commit()
    article = reg_domain.DEFAULT_ARTICLES["orantisizlik_esigi"]
    monkeypatch.setitem(reg_domain.DEFAULT_ARTICLES, "orantisizlik_esigi",
                        replace(article, allowed=reg_domain._num(5, 100, "5 – 100 yüzde puanı")))
    _session_round(ctx)
    # Açılışta tespit edilir; geri alınamadığı için açılışta yeni durum kaydı yazılır ve kapanış
    # aynı farkı ikinci kez yakalamaz.
    [revert] = ledger.of_type("OYLAMASIZ_DEGISIKLIK_GERI_ALINDI")
    assert (revert["payload"]["geri_alinan"], revert["payload"]["geri_alinamayan"],
            revert["payload"]["asama"]) == ([], ["izinli_aralik"], "acilis")
    assert [r["payload"].get("asama") for r in ledger.of_type("YONETMELIK_DURUMU")] == [
        None, "acilis", None]
    body = _verify(client)
    [item] = body["history"]
    assert item["alanlar"] == ["izinli_aralik"]
    assert (item["kayittaki_aralik"], item["bulunan_aralik"]) == (
        "5 – 30 yüzde puanı", "5 – 100 yüzde puanı")
    # Kod düzeyindeki fark yeni kayda girer; tespit veri düzeyindedir (açık 30).
    assert body["status"] == "tutarli"


def test_a_pending_state_record_is_the_reference_not_an_older_ledger_record(ctx, ledger):
    ctx.commit()
    ledger.fail = True  # defter kapalı: oturum kaydı outbox'ta bekler
    later, _ = _session_round(ctx, change=("red_bekleme", {"gun": 45}))
    assert later.graph.articles()["red_bekleme"] == {"gun": 45}
    _session_round(later, tag="b")  # defterdeki son kayıt hâlâ kurulumdaki (30 gün)
    ledger.fail = False
    later.commit()
    assert later.graph.articles()["red_bekleme"] == {"gun": 45}  # oylanan değer geri alınmadı
    assert ledger.of_type("OYLAMASIZ_DEGISIKLIK") == []



def test_opening_detects_and_reverts_before_the_snapshots(ctx, client, ledger):
    ctx.commit()
    devtools.tamper_regulation(ctx, "yonetmelik_esigi", {"oran": "1/2", "karsilastirma": ">"})
    devtools.tamper_regulation(ctx, "karar_saati", {**ctx.graph.articles()["karar_saati"],
                                                    "pencere_dakika": 5})
    ctx.commit()
    assert set(_verify(client)["differences"]) == {"karar_saati", "yonetmelik_esigi"}
    out = devtools.open_decision_hour(ctx, scripted=False)
    assert set(out["silent"]) == {"karar_saati", "yonetmelik_esigi"}
    session = decision_hour.open_session_row(ctx)
    # Anlık görüntüler son oylanmış değerlerle alındı: eşik 2/3, pencere 60 dakika.
    assert session.regulation["yonetmelik_esigi"] == {"oran": "2/3", "karsilastirma": ">="}
    assert session.closes_at - session.opened_at == timedelta(minutes=60)
    found = ledger.of_type("OYLAMASIZ_DEGISIKLIK")
    assert {(r["payload"]["madde"], r["payload"]["asama"], r["payload"]["oturum"]) for r in found} == {
        ("karar_saati", "acilis", session.id), ("yonetmelik_esigi", "acilis", session.id)}
    # Tespit ve geri alma, oturumun açılış kaydından önce deftere girer.
    types = [r["type"] for r in ledger.records]
    assert types.index("OTURUM_ACILDI") > max(i for i, t in enumerate(types)
                                              if t == "OYLAMASIZ_DEGISIKLIK_GERI_ALINDI")
    body = _verify(client)
    assert body["status"] == "tutarli"
    assert {(h["madde"], h["asama"]) for h in body["history"]} == {
        ("karar_saati", "acilis"), ("yonetmelik_esigi", "acilis")}
    # Kapanış aynı farkları ikinci kez yakalamaz.
    later = ctx.at(session.closes_at)
    decision_hour.close_session(later, session)
    later.commit()
    assert len(ledger.of_type("OYLAMASIZ_DEGISIKLIK")) == 2


def test_a_tampered_threshold_never_counts(ctx, ledger):
    """Açılıştan önce 1/2'ye çekilen eşik geri alınır: yarıdan fazla ama 2/3'ten az EVET alan
    yönetmelik önerisi reddedilir (değiştirilmiş eşikle geçerdi)."""
    ctx.commit()
    voters = [make_user(ctx, f"oy{i}") for i in range(6)]
    p = mature(ctx, proposals.open_proposal(ctx, voters[0], ProposalInput(
        type="YONETMELIK", article_key="red_bekleme", new_value={"gun": 45},
    )))
    devtools.tamper_regulation(ctx, "yonetmelik_esigi", {"oran": "1/2", "karsilastirma": ">"})
    ctx.commit()
    session = decision_hour.open_session(ctx)
    ballot_ids = {i["proposal"]["id"] for i in decision_hour.ballot(ctx, voters[0])["items"]}
    assert p.id in ballot_ids
    for i, v in enumerate(voters):
        decision_hour.cast_vote(ctx, v, p.id, i < 3)
    later = ctx.at(session.closes_at)
    decision_hour.close_session(later, session)
    later.commit()
    item = next(i for i in decision_hour.session_view(later, session.id)["items"]
                if i["proposal"]["id"] == p.id)
    r = item["result"]
    assert r["threshold"]["oran"] == "2/3"
    assert Fraction(1, 2) < Fraction(r["yes"], r["cast"]) < Fraction(2, 3)  # Hâtif dahil 4/7
    assert r["passed"] is False
    assert later.graph.articles()["red_bekleme"] == {"gun": 30}
