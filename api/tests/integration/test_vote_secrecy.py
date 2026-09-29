"""Oy gizliliği: temsilcinin (ağırlığı 1'den büyük) ve Hâtif'in oyu açık, seçmenin oyu gizli."""

from datetime import timedelta

from mesveret.domain.commit import verify_commit
from mesveret.domain.shade import shade_id, vote_pseudonym
from mesveret.services import decision_hour, proposals
from mesveret.services.oracle import ORACLE_ID
from mesveret.services.proposals import ProposalInput
from tests.integration.helpers import advance, delegate, headers_for, mature
from tests.integration.test_decision_hour import close, item_of, queued_konu
from tests.integration.world import make_user


def _chain_world(ctx):
    """a → b (genel havale): b'nin ağırlığı 2, açık; c'nin ağırlığı 1, gizli."""
    a, b, c = (make_user(ctx, n) for n in ("aylin", "baris", "ceren"))
    delegate(ctx, a, "baris", None)
    ctx.commit()
    return (a, b, c), queued_konu(ctx, c)


def test_weight_above_one_and_the_oracle_are_open_everyone_else_secret(ctx):
    (_a, b, c), p = _chain_world(ctx)
    session = decision_hour.open_session(ctx)
    item = item_of(ctx, session, p)
    assert set(item.open_voters) == {b.id, ORACLE_ID}  # Hâtif'in ağırlığı 1 olsa da açık
    notes = {u.nickname: decision_hour.ballot(ctx, u)["items"][0] for u in (b, c)}
    assert notes["baris"]["secrecy_note"] == "Oyunuz açık olacak: 1 yurttaşın oyunu taşıyorsunuz."
    assert notes["ceren"]["secrecy_note"].startswith("Oyunuz gizli")
    decision_hour.cast_vote(ctx, b, p.id, True)
    decision_hour.cast_vote(ctx, c, p.id, False)
    later = close(ctx, session)
    votes = item_of(later, session, p).result["votes"]
    open_votes = {v["voter"]: (v["choice"], v["weight"], v["delegators"]) for v in votes if v["open"]}
    assert open_votes == {"baris": ("EVET", 2, ["aylin"]), "Hâtif": ("EVET", 1, [])}
    [secret] = [v for v in votes if not v["open"]]
    assert secret == {"ballot_id": secret["ballot_id"], "open": False, "choice": "HAYIR", "weight": 1,
                      "pseudonym": decision_hour.pseudonym(later, c.id, session.id)}


def test_open_or_secret_is_fixed_at_the_snapshot(ctx):
    (_a, b, _c), p = _chain_world(ctx)
    session = decision_hour.open_session(ctx)
    during = ctx.at(ctx.now + timedelta(minutes=10))
    # Pencere sırasında havale kilitli; açık seçmen listesi açılıştaki anlık görüntüden.
    assert decision_hour.ballot(during, b)["items"][0]["open_vote"] is True
    assert item_of(during, session, p).open_voters == sorted([b.id, ORACLE_ID])


def test_concurrent_sub_vote_decides_openness_separately(ctx):
    ist1, ist2 = make_user(ctx, "ilker", city="İstanbul"), make_user(ctx, "irem", city="İstanbul")
    ank = make_user(ctx, "aylin", city="Ankara")
    delegate(ctx, ank, "ilker", None)  # İstanbul dışından gelen havale
    ctx.commit()
    p = mature(ctx, proposals.open_proposal(
        ctx, ank, ProposalInput(
            type="KONU", title="İstanbul payının yarısı Ankara'ya", body="Pay aktarılsın.",
            area_id="kent", scope_id="genel", resource_ids=["butce"],
            share_effect={"butce": {"sehir:istanbul": 2000, "sehir:ankara": 5000}},
        )))
    session = decision_hour.open_session(ctx)
    main = item_of(ctx, session, p)
    sub = next(i for i in decision_hour.items_of(ctx, session) if i.concurrent)
    assert ist1.id in main.open_voters  # Genel: aylin'in oyunu taşır
    assert ist1.id not in sub.open_voters  # İstanbul oylamasında havale dışarıdan geçmez: gizli
    assert ist2.id not in main.open_voters


def test_approval_vote_follows_the_same_rule(ctx):
    from tests.integration.test_decision_hour import _closure_with_three_texts

    ctx, (a, b, _c), _topic, p, texts = _closure_with_three_texts(ctx)
    d = make_user(ctx, "deniz")
    delegate(ctx, d, "baris", None)
    ctx.commit()
    session = decision_hour.open_session(ctx)
    decision_hour.cast_vote(ctx, a, p.id, [texts[0]])
    decision_hour.cast_vote(ctx, b, p.id, [texts[1]])
    later = close(ctx, session)
    votes = item_of(later, session, p).result["votes"]
    assert {v["voter"] for v in votes if v["open"]} == {"baris", "Hâtif"}
    assert [v["pseudonym"] for v in votes if not v["open"]] == [
        decision_hour.pseudonym(later, a.id, session.id)]


def test_ledger_carries_pseudonyms_for_secret_and_nicknames_for_open_votes(ctx, ledger):
    (_a, b, c), p = _chain_world(ctx)
    session = decision_hour.open_session(ctx)
    decision_hour.cast_vote(ctx, b, p.id, True)
    decision_hour.cast_vote(ctx, c, p.id, False)
    close(ctx, session)
    alias = decision_hour.pseudonym(ctx, c.id, session.id)
    for type_ in ("OY_MUHUR", "OY_ACILDI"):
        refs = {r["payload"]["secmen"]: r["payload"]["acik"] for r in ledger.of_type(type_)}
        assert refs == {"baris": True, "Hâtif": True, alias: False}
    votes = [r["payload"] for r in ledger.records
             if r["type"] in ("OY_MUHUR", "OY_ACILDI", "OYLAMA_SONUCU")]
    assert "ceren" not in str(votes) and c.id not in str(votes)  # öneren ceren açık bilgi
    reveal = next(r["payload"] for r in ledger.of_type("OY_ACILDI") if r["payload"]["secmen"] == alias)
    commit = next(r["payload"]["commit"] for r in ledger.of_type("OY_MUHUR")
                  if r["payload"]["secmen"] == alias)
    assert verify_commit(commit, reveal["oy"], reveal["tuz"])  # herkes doğrulayabilir


def test_pseudonyms_do_not_link_across_sessions_or_to_cellar_shades(ctx):
    key = ctx.settings.shade_key.encode()
    assert vote_pseudonym(key, "u1", 1) != vote_pseudonym(key, "u1", 2)
    assert vote_pseudonym(key, "u1", 1) != vote_pseudonym(key, "u2", 1)
    assert vote_pseudonym(key, "u1", 5) != shade_id(key, "u1", "5")  # alan ayracı
    (_a, _b, c), p = _chain_world(ctx)
    s1 = decision_hour.open_session(ctx)
    decision_hour.cast_vote(ctx, c, p.id, True)
    later = close(ctx, s1)
    p2 = queued_konu(later, c, title="İkinci öneri")
    after = advance(later, timedelta(days=1))
    s2 = decision_hour.open_session(after)
    decision_hour.cast_vote(after, c, p2.id, True)
    assert decision_hour.pseudonym(after, c.id, s1.id) != decision_hour.pseudonym(after, c.id, s2.id)


def test_verify_my_vote_is_only_for_the_voter(ctx, client):
    (_a, b, c), p = _chain_world(ctx)
    session = decision_hour.open_session(ctx)
    decision_hour.cast_vote(ctx, c, p.id, False)
    assert client.get("/decision-hour/my-votes").status_code == 401
    during = client.get(f"/decision-hour/my-votes?session_id={session.id}",
                        headers=headers_for(ctx, c)).json()
    [mine] = during["votes"]
    assert (mine["open"], mine["pseudonym"], mine["choice"], mine["verified"], mine["salt"]) == (
        False, decision_hour.pseudonym(ctx, c.id, session.id), "HAYIR", True, None)
    later = close(ctx, session)
    after = client.get("/decision-hour/my-votes", headers=headers_for(later, c)).json()
    assert after["votes"][0]["salt"] and after["votes"][0]["reveal_ledger_hash"]
    others = client.get("/decision-hour/my-votes", headers=headers_for(later, b)).json()
    assert others["votes"] == []  # baris oy vermedi; başkasının oyu görünmez


def test_raid_excluded_accounts_are_counted_not_named_but_told_privately(ctx, client, ledger):
    owner = make_user(ctx, "sahip")
    p = queued_konu(ctx, owner)
    raiders = [make_user(ctx, f"akin{i}", created_days_ago=0) for i in range(5)]  # aynı anda
    session = decision_hour.open_session(ctx)
    item = item_of(ctx, session, p)
    assert len(item.flagged) == 5
    ctx.commit()
    opening = ledger.of_type("OTURUM_ACILDI")[-1]["payload"]
    assert opening["baskin_isaretli_sayisi"] == {str(p.id): 5}
    assert not any(r.nickname in str(opening) for r in raiders)
    decision_hour.cast_vote(ctx, owner, p.id, True)
    later = close(ctx, session)
    result = client.get(f"/decision-hour/sessions/{session.id}").json()["items"][0]["result"]
    assert result["flagged_count"] == 5
    assert not any(r.nickname in str(result) for r in raiders)
    mine = client.get("/decision-hour/my-votes", headers=headers_for(later, raiders[0])).json()
    assert [e["proposal_id"] for e in mine["excluded"]] == [p.id]  # yalnızca kendisine
    theirs = client.get("/decision-hour/my-votes", headers=headers_for(later, owner)).json()
    assert theirs["excluded"] == []
