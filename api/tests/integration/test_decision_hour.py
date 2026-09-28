from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from mesveret.db.models import DecisionSession, Message, SessionItem
from mesveret.domain.commit import verify_commit
from mesveret.errors import Conflict, DomainError, Forbidden
from mesveret.services import decision_hour, delegation, ontology, proposals, topics
from mesveret.services.proposals import ProposalInput
from tests.integration.helpers import advance, headers_for, mature, open_topic, post, reload
from tests.integration.world import make_user


def queued_regulation(ctx, user, key="red_bekleme", value=None):
    return mature(ctx, proposals.open_proposal(ctx, user, ProposalInput(
        type="YONETMELIK", article_key=key, new_value=value or {"gun": 45},
    )))


def queued_konu(ctx, user, title="Metro gece de çalışsın", area="ulasim", scope="genel",
                body="Metro gece seferleri.", matured=True):
    p = proposals.open_proposal(ctx, user, ProposalInput(
        type="KONU", title=title, body=body, area_id=area, scope_id=scope,
    ))
    p.status, p.lane, p.queued_at = "QUEUED", "SLOW", ctx.now
    ctx.db.commit()
    return mature(ctx, p) if matured else p


def item_of(ctx, session, p) -> SessionItem:
    return ctx.db.execute(select(SessionItem).where(
        SessionItem.session_id == session.id, SessionItem.proposal_id == p.id
    )).scalar_one()


def close(ctx, session):
    later = ctx.at(session.closes_at)
    decision_hour.close_session(later, session)
    later.commit()
    return later


# --- havale zinciri ve ağırlık ---------------------------------------------------------------------


def test_chain_a_b_c_gives_c_weight_three(ctx):
    a, b, c = (make_user(ctx, n) for n in ("aylin", "baris", "ceren"))
    delegation.set_delegation(ctx, a, "baris", None)
    delegation.set_delegation(ctx, b, "ceren", "ulasim")
    ctx.commit()
    p = queued_konu(ctx, a)
    session = decision_hour.open_session(ctx)
    ballot = decision_hour.ballot(ctx, c)
    assert ballot["items"][0]["weight"] == 3
    with pytest.raises(Forbidden) as err:
        decision_hour.cast_vote(ctx, a, p.id, True)
    assert "havale" in err.value.message
    decision_hour.cast_vote(ctx, c, p.id, True)
    close(ctx, session)
    result = item_of(ctx, session, p).result
    assert result["yes"] == 4  # ceren (3) + Hâtif (1)
    assert next(v for v in result["votes"] if v["voter"] == "ceren")["weight"] == 3


def test_cycle_is_rejected_via_api(client, ctx):
    a, b = make_user(ctx, "aylin"), make_user(ctx, "baris")
    delegation.set_delegation(ctx, a, "baris", "sinema")
    ctx.commit()
    r = client.post("/delegations", headers=headers_for(ctx, b),
                    json={"target": "aylin", "area_id": "kultur"})
    assert r.status_code == 422
    assert "Sinema alanında" in r.json()["detail"]


def test_delegations_are_locked_while_window_is_open(ctx, client):
    a, b = make_user(ctx, "aylin"), make_user(ctx, "baris")
    delegation.set_delegation(ctx, a, "baris", None)
    ctx.commit()
    session = decision_hour.open_session(ctx)
    r = client.delete("/delegations", params={"area_id": ""}, headers=headers_for(ctx, a))
    assert r.status_code == 409
    assert "kilitli" in r.json()["detail"]
    with pytest.raises(Conflict):
        delegation.set_delegation(ctx, b, "aylin", "sinema")
    later = close(ctx, session)
    delegation.revoke_delegation(later, a, None)


def test_abstaining_chain_end_does_not_count(ctx):
    a, _b, c = (make_user(ctx, n) for n in ("aylin", "baris", "ceren"))
    delegation.set_delegation(ctx, a, "baris", None)
    ctx.commit()
    p = queued_konu(ctx, c)
    session = decision_hour.open_session(ctx)
    decision_hour.cast_vote(ctx, c, p.id, True)
    close(ctx, session)
    result = item_of(ctx, session, p).result
    assert (result["yes"], result["no"], result["cast"]) == (2, 0, 2)  # ceren + Hâtif
    assert result["passed"] is True
    assert result["abstained"] >= 2  # aylin (baris'e havale) ve baris oy vermedi


# --- anlık görüntü ---------------------------------------------------------------------------------


def test_electorate_is_snapshotted_when_window_opens(ctx):
    owner = make_user(ctx, "sahip", interests=("sinema",))
    late = make_user(ctx, "gec")
    ontology.join_interest(ctx.at(ctx.now - timedelta(days=14) + timedelta(minutes=30)), late, "sinema")
    ctx.commit()
    p = queued_konu(ctx, owner, title="Sinema kulübü", area="sinema", scope="ilgi:sinema")
    session = decision_hour.open_session(ctx)
    during = ctx.at(ctx.now + timedelta(minutes=45))
    assert ontology.vote_right(during, late.id, "ilgi:sinema").has_right
    with pytest.raises(Forbidden):
        decision_hour.cast_vote(during, late, p.id, True)
    assert late.id not in item_of(ctx, session, p).eligible


# --- mühürlü oy ------------------------------------------------------------------------------------


def test_votes_are_sealed_during_window_and_revealed_after(ctx, ledger):
    a = make_user(ctx, "aylin")
    p = queued_konu(ctx, a)
    session = decision_hour.open_session(ctx)
    decision_hour.cast_vote(ctx, a, p.id, False)
    ctx.commit()
    [commit_rec] = [r for r in ledger.of_type("OY_MUHUR") if r["payload"]["secmen"] == "aylin"]
    assert "secim" not in commit_rec["payload"]
    with pytest.raises(Conflict):
        decision_hour.cast_vote(ctx, a, p.id, True)
    close(ctx, session)
    [reveal] = [r for r in ledger.of_type("OY_ACILDI") if r["payload"]["secmen"] == "aylin"]
    doc = reveal["payload"]["oy"]
    assert doc["secim"] == "HAYIR"
    assert verify_commit(commit_rec["payload"]["commit"], doc, reveal["payload"]["tuz"])


def test_no_open_window_means_no_voting(ctx):
    a = make_user(ctx, "aylin")
    p = queued_konu(ctx, a)
    with pytest.raises(Conflict):
        decision_hour.cast_vote(ctx, a, p.id, True)


# --- yönetmelik eşiği ve kendini koruma --------------------------------------------------------------


def test_regulation_change_needs_two_thirds(ctx):
    voters = [make_user(ctx, f"secmen{i}") for i in range(29)]  # + Hâtif = 30 oy
    p60 = queued_regulation(ctx, voters[0], "red_bekleme", {"gun": 45})
    p67 = queued_regulation(ctx, voters[0], "musavir_esigi", {"deger": 7})
    session = decision_hour.open_session(ctx)
    for i, v in enumerate(voters):
        decision_hour.cast_vote(ctx, v, p60.id, i < 17)  # 17 + Hâtif = 18/30 = %60
        decision_hour.cast_vote(ctx, v, p67.id, i < 19)  # 19 + Hâtif = 20/30 = 2/3
    close(ctx, session)
    r60, r67 = item_of(ctx, session, p60).result, item_of(ctx, session, p67).result
    assert (r60["yes"], r60["cast"], r60["passed"]) == (18, 30, False)
    assert (r67["yes"], r67["cast"], r67["passed"]) == (20, 30, True)
    assert reload(ctx, p60).status == "REJECTED"
    assert reload(ctx, p67).status == "ACCEPTED"
    ctx.invalidate_regulation()
    assert ctx.reg.integer("musavir_esigi") == 7


def test_threshold_article_protects_itself(ctx):
    voters = [make_user(ctx, f"secmen{i}") for i in range(10)]
    p = queued_regulation(ctx, voters[0], "yonetmelik_esigi", {"oran": "1/2", "karsilastirma": ">"})
    session = decision_hour.open_session(ctx)
    for i, v in enumerate(voters):
        decision_hour.cast_vote(ctx, v, p.id, i < 6)  # 6 + Hâtif = 7/11 < 2/3
    close(ctx, session)
    result = item_of(ctx, session, p).result
    assert result["threshold"]["key"] == "yonetmelik_esigi"
    assert result["passed"] is False
    ctx.invalidate_regulation()
    assert ctx.reg.raw("yonetmelik_esigi")["oran"] == "2/3"


# --- silme -------------------------------------------------------------------------------------------


def test_deletion_by_vote_hides_message(ctx, client):
    a, b = make_user(ctx, "aylin"), make_user(ctx, "baris")
    topic = open_topic(ctx, a, title="Bisiklet yolları", area="ulasim")
    msg = post(ctx, a, topic, "Bunu yazanlar cahil.")
    p = mature(ctx, proposals.open_proposal(ctx, b, ProposalInput(
        type="SILME", target_message_id=msg.id, content_rules=["IK-2"], excerpt="yazanlar cahil",
    )))
    session = decision_hour.open_session(ctx)
    decision_hour.cast_vote(ctx, b, p.id, True)
    close(ctx, session)
    ctx.db.expire_all()
    assert ctx.db.get(Message, msg.id).deleted_by_proposal_id == p.id


def _silme(ctx, user, msg, excerpt=None, rules=("IK-2",)):
    return mature(ctx, proposals.open_proposal(ctx, user, ProposalInput(
        type="SILME", target_message_id=msg.id, content_rules=list(rules) if excerpt else [],
        excerpt=excerpt or "",
    )))


def test_deletion_needs_two_thirds_but_own_message_needs_simple_majority(ctx):
    a, b, c, d, e, f = (make_user(ctx, n) for n in ("aylin", "baris", "ceren", "deniz", "emre",
                                                    "ferhat"))
    topic = open_topic(ctx, a, title="Bisiklet yolları", area="ulasim")
    m60 = post(ctx, a, topic, "Bu konuyu açanların hepsi cahil.")
    m67 = post(ctx, a, topic, "Karşı çıkanlar aptal.")
    own = post(ctx, a, topic, "Telefonum 0532 000 00 00, arayın.")
    p60, p67 = _silme(ctx, b, m60, "hepsi cahil"), _silme(ctx, b, m67, "çıkanlar aptal")
    p_own = _silme(ctx, a, own)
    session = decision_hour.open_session(ctx)
    for voter, choice in ((b, True), (c, True), (d, False), (e, False)):  # + Hâtif EVET
        decision_hour.cast_vote(ctx, voter, p60.id, choice)
    for voter, choice in ((b, True), (c, True), (f, True), (d, False), (e, False)):
        decision_hour.cast_vote(ctx, voter, p67.id, choice)
    for voter, choice in ((a, True), (b, True), (c, False), (d, False)):
        decision_hour.cast_vote(ctx, voter, p_own.id, choice)
    later = close(ctx, session)
    r60, r67, r_own = (item_of(later, session, p).result for p in (p60, p67, p_own))
    assert (r60["yes"], r60["cast"], r60["threshold"]["key"], r60["passed"]) == (3, 5, "silme_esigi", False)
    assert (r67["yes"], r67["cast"], r67["passed"]) == (4, 6, True)
    assert (r_own["yes"], r_own["cast"], r_own["threshold"]["key"], r_own["passed"]) == (
        3, 5, "basit_cogunluk", True)
    later.db.expire_all()
    assert later.db.get(Message, m60.id).deleted_by_proposal_id is None
    assert later.db.get(Message, m67.id).deleted_by_proposal_id == p67.id
    assert later.db.get(Message, own.id).deleted_by_proposal_id == p_own.id


def test_oracle_votes_no_when_cited_rule_has_no_keyword_match(ctx):
    a, b = make_user(ctx, "aylin"), make_user(ctx, "baris")
    topic = open_topic(ctx, a, title="Bisiklet yolları", area="ulasim")
    msg = post(ctx, a, topic, "Bu görüşe katılmıyorum, bence yanlış.")
    p = _silme(ctx, b, msg, "bence yanlış")
    assert "Oylamada verilecek oy: HAYIR" in p.oracle_comment
    session = decision_hour.open_session(ctx)
    note = item_of(ctx, session, p).oracle_note
    assert note["choice"] == "HAYIR" and "karşılığı yok" in note["reason"]


def test_oracle_rechecks_the_excerpt_when_the_window_opens(ctx):
    a, b = make_user(ctx, "aylin"), make_user(ctx, "baris")
    topic = open_topic(ctx, a, title="Bisiklet yolları", area="ulasim")
    msg = post(ctx, a, topic, "Bunu yazanlar cahil.")
    p = _silme(ctx, b, msg, "yazanlar cahil")
    topics.edit_own_message(ctx, a, msg.id, "Özür dilerim, sert yazdım.")  # yazar düzeltti
    session = decision_hour.open_session(ctx)
    note = item_of(ctx, session, p).oracle_note
    assert note["choice"] == "HAYIR" and "R7" in note["reason"]


# --- kapanış, onay oylaması, şerh ------------------------------------------------------------------


def _closure_with_three_texts(ctx):
    a, b, c = make_user(ctx, "aylin"), make_user(ctx, "baris"), make_user(ctx, "ceren")
    topic = open_topic(ctx, a, title="Park saatleri", area="kent")
    post(ctx, b, topic, "Bence 22:00.")
    post(ctx, c, topic, "Bence 24:00.")
    p = proposals.open_proposal(ctx, a, ProposalInput(
        type="KAPANIS", target_topic_id=topic.id, body="Parklar 20:00'de kapansın.",
    ))
    proposals.add_rival(ctx, b, p.id, "Parklar 22:00'de kapansın.")
    proposals.add_rival(ctx, c, p.id, "Parklar 24:00'te kapansın.")
    later = advance(ctx, timedelta(hours=49))
    texts = [t.id for t in proposals.closure_texts(later, reload(later, p))]
    return later, (a, b, c), topic, mature(later, reload(later, p)), texts


def test_closure_approval_vote_and_dissent(ctx, client):
    ctx, (a, b, c), topic, p, texts = _closure_with_three_texts(ctx)
    d = make_user(ctx, "deniz")
    session = decision_hour.open_session(ctx)
    decision_hour.cast_vote(ctx, a, p.id, [texts[0], texts[1]])
    decision_hour.cast_vote(ctx, b, p.id, [texts[1]])
    decision_hour.cast_vote(ctx, c, p.id, [texts[2]])
    decision_hour.cast_vote(ctx, d, p.id, [texts[1], texts[2]])
    later = close(ctx, session)
    result = item_of(later, session, p).result
    assert result["winner"] == texts[1]
    view = client.get(f"/topics/{topic.id}").json()
    assert view["status"] == "CLOSED"
    assert view["decision"]["text"] == "Parklar 22:00'de kapansın."
    decision_id = view["decision"]["id"]

    def can_dissent(user):
        body = client.get(f"/topics/{topic.id}", headers=headers_for(later, user)).json()
        return body["decision"]["viewer_can_dissent"]

    assert view["decision"]["viewer_can_dissent"] is False  # giriş yapmamış
    assert (can_dissent(a), can_dissent(b), can_dissent(c)) == (True, False, True)
    # c kaybeden metnin sahibi; a kaybeden bir metni (20:00) onayladı; b yalnızca kazananı onayladı.
    decision_hour.add_dissent(later, c, decision_id, "Gece yarısı daha adil olurdu.")
    assert can_dissent(c) is False  # kişi başına karar başına bir şerh
    decision_hour.add_dissent(later, a, decision_id, "Erken kapanış güvenlik için gerekliydi.")
    with pytest.raises(Forbidden):
        decision_hour.add_dissent(later, b, decision_id, "Ben de yazayım.")
    with pytest.raises(Conflict):
        decision_hour.add_dissent(later, c, decision_id, "İkinci şerh.")
    view = client.get(f"/topics/{topic.id}").json()
    assert [x["author"] for x in view["decision"]["dissents"]] == ["ceren", "aylin"]


def test_closure_tie_gives_no_decision(ctx):
    ctx, (a, b, _c), _topic, p, texts = _closure_with_three_texts(ctx)
    session = decision_hour.open_session(ctx)
    decision_hour.cast_vote(ctx, a, p.id, [texts[0]])
    decision_hour.cast_vote(ctx, b, p.id, [texts[1]])
    later = close(ctx, session)
    result = item_of(later, session, p).result
    assert result["tie"] is True and result["winner"] is None
    assert reload(later, p).status == "REJECTED"


# --- baskın ------------------------------------------------------------------------------------------


def test_raid_cluster_is_flagged_and_excluded(ctx):
    owner = make_user(ctx, "sahip")
    p = queued_konu(ctx, owner)
    raiders = [make_user(ctx, f"akin{i}", created_days_ago=0) for i in range(5)]  # aynı anda
    session = decision_hour.open_session(ctx)
    item = item_of(ctx, session, p)
    flagged = {f["user_id"] for f in item.flagged}
    assert flagged == {r.id for r in raiders}
    with pytest.raises(Forbidden) as err:
        decision_hour.cast_vote(ctx, raiders[0], p.id, True)
    assert "baskın" in err.value.message
    decision_hour.cast_vote(ctx, owner, p.id, False)
    close(ctx, session)
    result = item_of(ctx, session, p).result
    assert len(result["flagged"]) == 5
    assert result["passed"] is False


# --- Hâtif -------------------------------------------------------------------------------------------


def test_oracle_votes_deterministically(ctx):
    a = make_user(ctx, "aylin")
    clean = queued_konu(ctx, a)
    mislabeled = queued_konu(ctx, a, title="Belgesel gösterimleri",
                             body="Her ay bir belgesel ve bir belgesel söyleşisi.", area="ulasim")
    follower = make_user(ctx, "takipci")
    delegation.set_delegation(ctx, follower, "Hâtif", None)
    ctx.commit()
    session = decision_hour.open_session(ctx)
    close(ctx, session)
    r_clean, r_bad = item_of(ctx, session, clean).result, item_of(ctx, session, mislabeled).result
    oracle_clean = next(v for v in r_clean["votes"] if v["voter"] == "Hâtif")
    oracle_bad = next(v for v in r_bad["votes"] if v["voter"] == "Hâtif")
    assert oracle_clean["choice"] == "EVET" and oracle_clean["weight"] == 2
    assert oracle_bad["choice"] == "HAYIR"
    assert "H1" in r_bad["oracle"]["reason"]


# --- takvim ------------------------------------------------------------------------------------------


def test_weekly_sessions_open_on_schedule_and_wait_for_maturity(ctx):
    a = make_user(ctx, "aylin")
    p = queued_konu(ctx, a, matured=False)  # Salı 10:00'da kuyruğa girdi; genel: 7 gün
    later = advance(ctx, timedelta(days=6))  # Salı 10:00 → Pazartesi 10:00
    sessions = later.db.execute(select(DecisionSession)).scalars().all()
    assert len(sessions) == 1
    s = sessions[0]
    assert s.status == "CLOSED"
    assert s.opened_at == datetime(2026, 10, 4, 17, 0, tzinfo=UTC)
    assert s.closes_at - s.opened_at == timedelta(hours=1)
    assert reload(later, p).status == "QUEUED"  # olgunlaşmadığı için 4 Ekim'e alınmadı
    later = advance(later, timedelta(days=7))  # 11 Ekim oturumu da geçti
    item = later.db.execute(select(SessionItem).where(SessionItem.proposal_id == p.id)).scalar_one()
    # Kimse oy vermedi; yalnızca Hâtif'in EVET oyu sayıldı ve öneri geçti (bkz. Bilinçli açıklar).
    assert (item.result["yes"], item.result["cast"]) == (1, 1)
    assert reload(later, p).status == "ACCEPTED"


def test_status_endpoint_reports_next_session(client, ctx):
    body = client.get("/decision-hour").json()
    assert body["next_scheduled_at"].startswith("2026-10-04T17:00:00")
    assert body["open_session"] is None


def test_results_endpoint_lists_votes_for_reveal(client, ctx):
    a, b = make_user(ctx, "aylin"), make_user(ctx, "baris")
    p = queued_konu(ctx, a)
    session = decision_hour.open_session(ctx)
    decision_hour.cast_vote(ctx, a, p.id, True)
    decision_hour.cast_vote(ctx, b, p.id, False)
    open_view = client.get(f"/decision-hour/sessions/{session.id}").json()
    assert open_view["items"][0]["result"] is None
    close(ctx, session)
    body = client.get(f"/decision-hour/sessions/{session.id}").json()
    votes = body["items"][0]["result"]["votes"]
    assert {v["voter"] for v in votes} >= {"aylin", "baris"}
    assert all("ledger_hash" in v for v in votes)


def test_dev_scripted_votes_are_cast_when_session_opens(ctx):
    from mesveret.db.models import DevVotePlan

    a, b = make_user(ctx, "aylin"), make_user(ctx, "baris")
    p = queued_konu(ctx, a)
    ctx.db.add_all([DevVotePlan(proposal_id=p.id, voter_id=a.id, choice="EVET"),
                    DevVotePlan(proposal_id=p.id, voter_id=b.id, choice="HAYIR")])
    ctx.commit()
    session = decision_hour.open_session(ctx, scripted=True)
    close(ctx, session)
    result = item_of(ctx, session, p).result
    assert (result["yes"], result["no"]) == (2, 1)  # aylin + Hâtif EVET, baris HAYIR


def test_invalid_choice_is_rejected(ctx):
    a = make_user(ctx, "aylin")
    p = queued_konu(ctx, a)
    decision_hour.open_session(ctx)
    with pytest.raises(DomainError):
        decision_hour.cast_vote(ctx, a, p.id, [1, 2])


def test_pending_deletion_citing_a_removed_rule_gets_oracle_no(ctx):
    from mesveret.services import regulation

    a, b = make_user(ctx, "aylin"), make_user(ctx, "baris")
    topic = open_topic(ctx, a, title="Bisiklet yolları", area="ulasim")
    msg = post(ctx, a, topic, "Bunu yazanlar cahil.")
    p = _silme(ctx, b, msg, "yazanlar cahil")
    regulation.apply_change(ctx, "IK-2", None, None, action="kaldir")
    ctx.commit()
    session = decision_hour.open_session(ctx)
    note = item_of(ctx, session, p).oracle_note
    assert note["choice"] == "HAYIR" and "Böyle bir içerik kuralı yok: IK-2" in note["reason"]
