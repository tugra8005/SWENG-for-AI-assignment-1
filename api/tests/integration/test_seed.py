"""Tohum veriyi kurar ve sekiz demo senaryosunun README'de anlatılan sonuçlarını doğrular."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from mesveret.context import Ctx
from mesveret.db.models import Message, Proposal, SessionItem, User
from mesveret.errors import Conflict, DomainError, Forbidden
from mesveret.services import cellar, decision_hour, delegation, proposals, seed
from mesveret.services.proposals import ProposalInput


@pytest.fixture
def seeded(db, graph, ledger, settings):
    ctx = Ctx(db=db, graph=graph, now=seed.SEED_NOW, settings=settings, ledger=ledger)
    lines = list(seed.run(ctx))
    assert any("şifresi" in line for line in lines)
    return ctx.at(seed.SEED_NOW)


def user(ctx, nick) -> User:
    return ctx.db.execute(select(User).where(User.nickname == nick)).scalar_one()


def result(ctx, session, pid):
    return ctx.db.execute(select(SessionItem).where(
        SessionItem.session_id == session.id, SessionItem.proposal_id == pid
    )).scalar_one().result


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
        delegation.set_delegation(ctx, user(ctx, "ceren"), "aylin", "ulasim")
    assert "döngü" in err.value.message


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

    # 3. Yönetmelik: %60 geçemez, 2/3 geçer.
    r60, r67 = result(later, session, ids["yonetmelik_60"]), result(later, session, ids["yonetmelik_67"])
    assert (r60["yes"], r60["cast"], r60["passed"]) == (18, 30, False)
    assert (r67["yes"], r67["cast"], r67["passed"]) == (20, 30, True)

    # 4. Silme: mesaj gizlenir.
    assert result(later, session, ids["silme"])["passed"] is True
    troll = later.db.execute(select(Message).where(Message.author_id == user(later, "kaba_kul").id)).scalar_one()
    assert troll.deleted_by_proposal_id == ids["silme"]

    # 5. Kapanış: 22:00 metni kazanır; ilker (kaybeden) şerh ekleyebilir.
    rk = result(later, session, ids["kapanis"])
    winner = next(s for s in rk["scores"] if s["text_id"] == rk["winner"])
    assert "22:00'de" in winner["text"]
    decision_id = proposals.proposal_view(later, later.db.get(Proposal, ids["kapanis"]), None)["decision_id"]
    decision_hour.add_dissent(later, user(later, "ilker"), decision_id, "Yaz geceleri parklar kent yaşamının parçası.")

    # 7. Baskın: beş hesap işaretlenip dışlanır; öneri reddedilir.
    rb = result(later, session, ids["baskin"])
    assert len(rb["flagged"]) == 5
    assert rb["passed"] is False

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
    assert len(listing["threads"]) == 91
    assert listing["threads"][-1]["lifetime"] < 0.2


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
