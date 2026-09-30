"""Tohum veriyi kurar ve sekiz demo senaryosunun README'de anlatılan sonuçlarını doğrular."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from mesveret.context import Ctx
from mesveret.db.models import DelegationRequest, Message, Proposal, SessionItem, User
from mesveret.errors import Conflict, DomainError, Forbidden
from mesveret.services import cellar, decision_hour, delegation, proposals, scheduler, seed
from mesveret.services.proposals import ProposalInput


@pytest.fixture
def seeded(db, graph, ledger, settings):
    ctx = Ctx(db=db, graph=graph, now=seed.SEED_NOW, settings=settings, ledger=ledger)
    lines = list(seed.run(ctx))
    assert any("şifresi" in line for line in lines)
    return ctx.at(seed.SEED_NOW)


def user(ctx, nick) -> User:
    return ctx.db.execute(select(User).where(User.nickname == nick)).scalar_one()


def result(ctx, session, pid, scope=None):
    """Önerinin ana oylamasının (scope verilirse o alt kapsam oylamasının) sonucu."""
    q = select(SessionItem).where(SessionItem.session_id == session.id,
                                  SessionItem.proposal_id == pid)
    q = q.where(SessionItem.vote_scope_id == scope) if scope else q.where(
        SessionItem.concurrent.is_(False))
    return ctx.db.execute(q).scalar_one().result


def test_seed_builds_about_forty_accounts_and_three_level_tree(seeded):
    ctx = seeded
    assert 40 <= ctx.db.query(User).count() <= 45
    depths = {a.id: len(ctx.graph.area_ancestors(a.id)) for a in ctx.graph.all_areas()}
    assert max(depths.values()) == 3
    cities = {s.name for s in ctx.graph.city_scopes()}
    assert cities >= {"İstanbul", "Ankara", "İzmir", "Bursa"}


def test_scenario_1_istanbul(seeded):
    ctx = seeded
    ids = seed.scenario_ids(ctx)
    p = ctx.db.get(Proposal, ids["istanbul"])
    assert p.narrowings[0]["message"] == "Bu karar yalnızca İstanbul payını etkiler (4.000 puan)."
    assert (p.narrowings[0]["share"], p.narrowings[0]["total"]) == (4000, 20000)
    assert proposals.effective_title(p) == "Etkinlik bütçesinin İstanbul payı"
    with pytest.raises(DomainError) as err:
        proposals.open_proposal(ctx, user(ctx, "ayse"), ProposalInput(
            type="KONU", title="Toplantı salonu yalnızca İstanbul'a",
            body="Salon İstanbul'un olsun.", area_id="kent", scope_id="sehir:istanbul",
            resource_ids=["salon"],
        ))
    assert err.value.violations[0]["message"].startswith("Bu kapsam bu kaynak hakkında karar veremez")


def test_scenario_2_cycle_is_rejected_before_the_session(seeded):
    ctx = seeded
    with pytest.raises(DomainError) as err:
        delegation.request_delegation(ctx, user(ctx, "ceren"), "aylin", "ulasim")
    assert "döngü" in err.value.message


def test_seed_delegations_start_accepted_with_one_pending_and_one_rejected(seeded):
    ctx = seeded
    statuses = {r.status for r in ctx.db.execute(select(DelegationRequest)).scalars()}
    assert statuses == {"ACCEPTED", "PENDING", "REJECTED"}
    accepted = ctx.db.execute(select(DelegationRequest).where(
        DelegationRequest.status == "ACCEPTED")).scalars().all()
    assert len(accepted) == len(ctx.graph.delegation_edges(active_at=ctx.now)) == 9
    aylin = delegation.my_delegations(ctx, user(ctx, "aylin"))
    assert [(r["from"], r["area_name"]) for r in aylin["pending_received"]] == [("elif", "Kent")]
    assert [(o["target"], o["area_name"], o["label"]) for o in aylin["outcomes"]] == [
        ("mert", "Ulaşım", "reddedildi")]
    assert [g["target"] for g in aylin["given"]] == ["baris"]  # reddedilen havale grafa girmedi


def test_decision_hour_runs_all_voting_scenarios(seeded):
    ctx = seeded
    ids = seed.scenario_ids(ctx)
    session = decision_hour.open_session(ctx)
    decision_hour.apply_vote_plan(ctx, session)
    ctx.commit()

    # 2. Havale zinciri: aylin geri alamaz ve oy veremez; ceren'in ağırlığı 3.
    with pytest.raises(Conflict):
        delegation.revoke_delegation(ctx, user(ctx, "aylin"), None)
    with pytest.raises(Forbidden):
        decision_hour.cast_vote(ctx, user(ctx, "aylin"), ids["metro"], True)
    ballot = decision_hour.ballot(ctx, user(ctx, "ceren"))
    metro = next(i for i in ballot["items"] if i["proposal"]["id"] == ids["metro"])
    assert metro["weight"] == 3
    decision_hour.cast_vote(ctx, user(ctx, "ceren"), ids["metro"], True)

    later = ctx.at(session.closes_at)
    decision_hour.close_session(later, session)
    later.commit()

    r = result(later, session, ids["metro"])
    assert (r["yes"], r["no"], r["passed"]) == (8, 5, True)
    assert "8/13 ağırlıklı EVET (%61,5)" in r["note"]

    # 3. Yönetmelik: %60 geçemez, 2/3 geçer.
    r60, r67 = result(later, session, ids["yonetmelik_60"]), result(later, session, ids["yonetmelik_67"])
    assert (r60["yes"], r60["cast"], r60["passed"]) == (18, 30, False)
    assert (r67["yes"], r67["cast"], r67["passed"]) == (20, 30, True)

    # 4. Silme: gerekçeli silme 2/3 ister (%60 geçemez, %67 geçer); kendi mesajı basit çoğunluk.
    s60, s67, own = (result(later, session, ids[k]) for k in ("silme_60", "silme_67", "silme_kendi"))
    assert (s60["yes"], s60["cast"], s60["threshold"]["key"], s60["passed"]) == (18, 30, "silme_esigi", False)
    assert (s67["yes"], s67["cast"], s67["passed"]) == (20, 30, True)
    assert (own["yes"], own["cast"], own["threshold"]["key"], own["passed"]) == (7, 12, "basit_cogunluk", True)
    msgs = {p.id: later.db.get(Message, p.payload["message_id"])
            for p in (later.db.get(Proposal, ids[k]) for k in ("silme_60", "silme_67", "silme_kendi"))}
    assert msgs[ids["silme_60"]].deleted_by_proposal_id is None  # hakaret görünür kaldı
    assert msgs[ids["silme_67"]].deleted_by_proposal_id == ids["silme_67"]
    assert msgs[ids["silme_kendi"]].deleted_by_proposal_id == ids["silme_kendi"]

    # 5. Kapanış: 22:00 metni kazanır; ilker (kaybeden) şerh ekleyebilir.
    rk = result(later, session, ids["kapanis"])
    winner = next(s for s in rk["scores"] if s["text_id"] == rk["winner"])
    assert "22:00'de" in winner["text"]
    decision_id = proposals.proposal_view(later, later.db.get(Proposal, ids["kapanis"]), None)["decision_id"]
    decision_hour.add_dissent(later, user(later, "ilker"), decision_id, "Yaz geceleri parklar kent yaşamının parçası.")

    # 7. Baskın: beş hesap işaretlenip dışlanır; öneri reddedilir.
    rb = result(later, session, ids["baskin"])
    assert rb["flagged_count"] == 5 and "flagged" not in rb
    assert rb["passed"] is False

    # 10. Eşzamanlı çoğunluk: Genel'de geçer, İstanbul'da reddedilir → öneri reddedilir.
    main, ist = result(later, session, ids["pay_yarisi"]), result(
        later, session, ids["pay_yarisi"], "sehir:istanbul")
    assert (main["yes"], main["cast"], main["passed"]) == (16, 25, True)
    assert (ist["yes"], ist["cast"], ist["passed"]) == (2, 9, False)
    assert main["overall"]["summary"] == "Genel'de geçti (%64) · İstanbul'da geçemedi (%22) → Reddedildi"
    assert later.db.get(Proposal, ids["pay_yarisi"]).status == "REJECTED"
    cut = result(later, session, ids["kesinti"])
    assert (cut["yes"], cut["cast"], cut["passed"], cut["overall"]["summary"]) == (13, 21, True, None)
    assert dict(later.graph.resource("butce").shares) == {
        "sehir:istanbul": 3600, "sehir:ankara": 5400, "sehir:izmir": 4500, "sehir:bursa": 4500}
    # 14. Pay çakışması: artış kabul oyu alır ama kesinti önce uygulandı → uygulanmaz, ret değil.
    assert ids["artis"] == ids["kesinti"] + 1
    raise_ = result(later, session, ids["artis"])
    assert (raise_["yes"], raise_["cast"], raise_["passed"]) == (13, 21, True)
    assert raise_["overall"]["conflict"]["by"] == [ids["kesinti"]]
    p = later.db.get(Proposal, ids["artis"])
    assert p.status == "CONFLICT" and "çakışma nedeniyle uygulanamadı" in p.outcome_note

    # 8. Hâtif: yanlış alan etiketi yüzünden HAYIR, ağırlığı 3.
    rh = result(later, session, ids["hatif"])
    oracle_vote = next(v for v in rh["votes"] if v["voter"] == "Hâtif")
    assert oracle_vote["choice"] == "HAYIR" and oracle_vote["weight"] == 3
    assert rh["passed"] is False


def test_scenario_6_cellar_reveal(seeded):
    ctx = seeded
    ayse = user(ctx, "ayse")
    assert ayse.cellar_warned_at is None
    tid = next(t["id"] for t in cellar.list_threads(ctx, ayse)["threads"]
               if t["title"] == "Çoğunluk haklı olabilir mi?")
    cellar.acknowledge_entry(ctx, ayse)
    assert cellar.cast_reveal_vote(ctx, ayse, tid, True)["revealed"] is True
    view = cellar.thread_view(ctx, tid, ayse)
    assert view["posts"][0]["nickname"] == "ayse"
    draft = ctx.db.get(Proposal, view["revealed"]["draft_proposal_id"])
    assert draft.status == "DRAFT" and draft.proposer_id == ayse.id


def test_cellar_has_decaying_threads(seeded):
    listing = cellar.list_threads(seeded, None)
    assert len(listing["threads"]) == 92
    assert listing["threads"][-1]["lifetime"] < 0.2
    titles = [t["title"] for t in listing["threads"]]
    assert len(set(titles)) == len(titles)  # tekrar eden başlık yok
    # Alt sıralarda çürümenin farklı aşamaları: yarı ömürden silinmek üzereye.
    tail = [t["lifetime"] for t in listing["threads"][-40:]]
    assert max(tail) > 0.4 and min(tail) < 0.15


def test_cellar_poem_thread_second_after_demo(seeded):
    """Şiir başlığı: metin olduğu gibi, demo başlığının hemen altında, demo başlığı No.91 kalır."""
    listing = cellar.list_threads(seeded, None)["threads"]
    assert [t["title"] for t in listing[:2]] == ["Çoğunluk haklı olabilir mi?", seed.KOYLULER_BASLIK]
    assert listing[0]["id"] == 91
    assert listing[1]["op_preview"].startswith("Köylüleri niçin öldürmeliyiz? Çünkü onlar ağır")
    posts = cellar.thread_view(seeded, listing[1]["id"], None)["posts"]
    assert posts[0]["text"] == seed.KOYLULER_SIIR
    assert len(posts) == 1 + len(seed.KOYLULER_YANITLAR)
    # "{n}" n. mesajın numarasına dönüşür: ikinci yanıt açılışa, üçüncüsü ikinci yanıta bağlanır.
    assert posts[2]["text"].startswith(f">>{posts[0]['no']} ")
    assert posts[3]["text"].startswith(f">>{posts[2]['no']} ")


def test_cellar_discussions_replace_filler_replies(seeded):
    listing = cellar.list_threads(seeded, None)["threads"]
    for i, replies in seed.MAHZEN_DISCUSSIONS.items():
        t = next(t for t in listing if t["title"] == seed.MAHZEN_PROMPTS[i])
        posts = cellar.thread_view(seeded, t["id"], None)["posts"]
        assert len(posts) == 1 + len(replies)
        assert not any("{" in p["text"] for p in posts)
    # Yanıtlar bir sonraki dolgu başlıktan önce biter: liste sırası açılış sırasıdır.
    fillers = [t["id"] for t in listing if t["title"] in seed.MAHZEN_PROMPTS]
    assert fillers == sorted(fillers, reverse=True)


def test_owner_account_logs_in_with_nickname_or_email(seeded, client):
    """Projenin sahibinin hesabı: takma ad büyük/küçük harf duyarsız, e-posta da kabul edilir."""
    owner = user(seeded, "MostlyHarmless")
    assert (owner.full_name, owner.city, owner.email) == (
        "Alparslan Tuğra Şahin", "Tokat", seed.OWNER_EMAIL)
    for ident in ("mostlyharmless", seed.OWNER_EMAIL):
        r = client.post("/auth/login", json={"identifier": ident, "password": seed.DEMO_PASSWORD})
        assert r.status_code == 200 and r.json()["token"]
        me = client.get("/auth/me", headers={"Authorization": f"Bearer {r.json()['token']}"}).json()
        assert me["nickname"] == "MostlyHarmless"


def test_counselor_label_in_seed(seeded, client):
    body = client.get("/users/selin").json()
    assert "Müşavir" in body["roles"]


def test_advancing_time_accepts_istanbul_proposal(seeded):
    from mesveret.services import scheduler

    ctx = seeded
    ids = seed.scenario_ids(ctx)
    target = ctx.now + timedelta(hours=25)
    scheduler.tick(ctx.at(target), target)
    ctx.db.expire_all()
    assert ctx.db.get(Proposal, ids["istanbul"]).status == "ACCEPTED"


def test_scenario_9_late_general_proposal_waits_for_maturity(seeded):
    ctx = seeded
    ids = seed.scenario_ids(ctx)
    late = ctx.db.get(Proposal, ids["olgunlasma"])
    assert late.created_at == seed.SEED_NOW - timedelta(minutes=10)
    maturity = proposals.proposal_view(ctx, late, None)["maturity"]
    assert maturity["klass"] == "genel" and maturity["mature"] is False
    assert maturity["first_session_at"] == datetime(2026, 10, 11, 17, 0, tzinfo=UTC)

    session = decision_hour.open_session(ctx)
    included = {i.proposal_id for i in decision_hour.items_of(ctx, session)}
    voting = {ids[k] for k in ("metro", "yonetmelik_60", "yonetmelik_67", "silme_60", "silme_67",
                               "silme_kendi", "kapanis", "baskin", "hatif", "pay_yarisi",
                               "kesinti")}
    assert voting <= included  # tohumdaki senaryo önerileri olgunlaşmış
    assert ids["olgunlasma"] not in included
    later = ctx.at(session.closes_at)
    decision_hour.close_session(later, session)
    later.commit()

    # Haftalık oturumlar: 4 Ekim'de hâlâ olgunlaşıyor, 11 Ekim'de oylanıyor.
    target = datetime(2026, 10, 11, 18, 30, tzinfo=UTC)
    scheduler.tick(later.at(target), target)
    later.db.expire_all()
    late = later.db.get(Proposal, ids["olgunlasma"])
    s = decision_hour.get_session(later, late.session_id)
    assert s.scheduled_for == datetime(2026, 10, 11, 17, 0, tzinfo=UTC)


def test_scenario_4_unjustified_deletion_is_rejected(seeded):
    ctx = seeded
    hale_msg = ctx.db.execute(select(Message).where(
        Message.author_id == user(ctx, "hale").id, Message.is_opening.is_(False)
    )).scalar_one()
    with pytest.raises(DomainError) as err:
        proposals.open_proposal(ctx, user(ctx, "emre"), ProposalInput(
            type="SILME", target_message_id=hale_msg.id, body="Bu mesajı beğenmedim.",
        ))
    assert err.value.violations[0]["rule"] == "R7"
    silme_60 = ctx.db.get(Proposal, seed.scenario_ids(ctx)["silme_60"])
    assert "IK-2 (Hakaret ve tehdit): belirtilen kısımda karşılığı var" in silme_60.oracle_comment


def test_scenario_11_floor_of_the_regulation(seeded):
    ctx = seeded
    kerem = user(ctx, "kerem")
    attempts = [
        ProposalInput(type="YONETMELIK", article_key="yonetmelik_esigi",
                      new_value={"oran": "1/2", "karsilastirma": ">="},
                      body="Yönetmelik basit çoğunlukla değişsin."),
        ProposalInput(type="YONETMELIK", article_key="D3", article_action="kaldir",
                      body="Şerh hakkı kaldırılsın."),
    ]
    for inp in attempts:
        with pytest.raises(DomainError) as err:
            proposals.open_proposal(ctx, kerem, inp)
        assert err.value.violations[0]["rule"] == "R8"
    assert ctx.reg.raw("yonetmelik_esigi")["oran"] == "2/3"


def test_scenario_13_delegations_expire_after_181_days(seeded, client, ledger):
    ctx = seeded
    aylin, baris, ceren = (user(ctx, n) for n in ("aylin", "baris", "ceren"))
    [given] = delegation.my_delegations(ctx, aylin)["given"]
    assert (given["target"], given["days_left"]) == ("baris", 150)  # Ulaşım'da zincir ceren'e akar
    assert delegation.my_delegations(ctx, ceren)["received"] == [
        {"area_id": "ulasim", "area_name": "Ulaşım", "count": 1}]

    target = ctx.now + timedelta(days=140)  # 10 gün kala uyarı
    scheduler.tick(ctx.at(target), target)
    mid = ctx.at(target)
    assert delegation.my_delegations(mid, aylin)["expiring_given"][0]["days_left"] == 10

    target = ctx.now + timedelta(days=181)
    scheduler.tick(ctx.at(target), target)
    later = ctx.at(target)
    assert delegation.my_delegations(later, aylin)["given"] == []  # aylin oyunu geri aldı
    assert delegation.my_delegations(later, baris)["given"] == []  # baris de
    assert delegation.my_delegations(later, ceren)["received"] == []  # ceren'in ağırlığı 1
    assert "Müşavir" not in client.get("/users/selin").json()["roles"]
    expired = {(r["payload"]["veren"], r["payload"]["alan"])
               for r in ledger.of_type("HAVALE_SURESI_DOLDU")}
    assert {("aylin", "baris"), ("baris", "ceren")} <= expired
    assert len(expired) == 9
