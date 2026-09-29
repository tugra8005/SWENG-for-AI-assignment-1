"""Aynı bölünebilir kaynağa dokunan öneriler: kapanışta numara sırasıyla uygulanır; önce uygulanan
öneri payları değiştirdiyse sonrakinin hedefleri geçersizdir ve öneri uygulanmaz (ret sayılmaz)."""

from sqlalchemy import select

from mesveret.db.models import Proposal
from mesveret.services import decision_hour, proposals
from mesveret.services.proposals import ProposalInput
from tests.integration.helpers import mature, reload
from tests.integration.test_decision_hour import close, item_of
from tests.integration.world import make_user

CUT = {"sehir:istanbul": 3600, "sehir:ankara": 2700, "sehir:izmir": 1800}  # herkese %10 kesinti
RAISE = {"sehir:istanbul": 4200, "sehir:ankara": 3150, "sehir:izmir": 2100}  # herkese %5 artış


def _budget(ctx, user, title, effect, *, queued=True):
    p = proposals.open_proposal(ctx, user, ProposalInput(
        type="KONU", title=title, body="Etkinlik bütçesinin payları değişsin.", area_id="kent",
        scope_id="genel", resource_ids=["butce"], share_effect={"butce": effect},
    ))
    if queued:
        p.status, p.lane, p.queued_at = "QUEUED", "SLOW", ctx.now
        ctx.db.commit()
    return mature(ctx, p)


def _voters(ctx, n=3):
    return [make_user(ctx, f"secmen{i}") for i in range(n)]


def test_base_shares_are_recorded_at_opening(ctx):
    a = make_user(ctx, "aylin")
    p = _budget(ctx, a, "Herkese kesinti", CUT)
    assert p.payload["share_base"] == {"butce": {"sehir:istanbul": 4000, "sehir:ankara": 3000,
                                                 "sehir:izmir": 2000}}


def test_later_proposal_on_the_same_resource_is_not_applied_and_not_rejected(ctx, ledger):
    voters = _voters(ctx)
    cut = _budget(ctx, voters[0], "Herkese kesinti", CUT)
    raise_ = _budget(ctx, voters[1], "Herkese artış", RAISE)
    session = decision_hour.open_session(ctx)
    for v in voters:
        decision_hour.cast_vote(ctx, v, cut.id, True)
        decision_hour.cast_vote(ctx, v, raise_.id, True)
    later = close(ctx, session)

    assert reload(later, cut).status == "ACCEPTED"
    assert dict(later.graph.resource("butce").shares) == CUT  # yalnızca önce uygulanan
    p = reload(later, raise_)
    assert p.status == "CONFLICT"
    assert p.outcome_note.startswith(
        f"Kabul oyu aldı ama çakışma nedeniyle uygulanamadı: №{cut.id} Etkinlik bütçesi")
    assert "reddedilmiş sayılmaz" in p.outcome_note
    result = item_of(later, session, raise_).result
    assert result["passed"] is True
    assert result["overall"]["conflict"]["by"] == [cut.id]
    outcome = [r["payload"] for r in ledger.of_type("ONERI_SONUCU") if r["payload"]["oneri"] == p.id]
    assert outcome == [{"oneri": p.id, "sonuc": "UYGULANAMADI", "not": p.outcome_note,
                        "cakisma": [{"kaynak": "butce", "oneri": cut.id}]}]


def test_conflicted_proposal_can_be_reopened_at_once_with_the_same_content(ctx):
    voters = _voters(ctx)
    cut = _budget(ctx, voters[0], "Herkese kesinti", CUT)
    raise_ = _budget(ctx, voters[1], "Herkese artış", RAISE)
    session = decision_hour.open_session(ctx)
    for v in voters:
        decision_hour.cast_vote(ctx, v, cut.id, True)
        decision_hour.cast_vote(ctx, v, raise_.id, True)
    later = close(ctx, session)
    assert reload(later, raise_).status == "CONFLICT"
    # red_bekleme yalnızca reddedilen hedefe uygulanır; aynı başlık ve içerik hemen açılabilir.
    again = _budget(later, voters[1], "Herkese artış", RAISE, queued=False)
    assert again.status in ("SILENT", "QUEUED")
    assert again.payload["share_base"]["butce"] == CUT


def test_rejected_earlier_proposal_leaves_the_later_one_applicable(ctx):
    voters = _voters(ctx)
    cut = _budget(ctx, voters[0], "Herkese kesinti", CUT)
    raise_ = _budget(ctx, voters[1], "Herkese artış", RAISE)
    session = decision_hour.open_session(ctx)
    for v in voters:
        decision_hour.cast_vote(ctx, v, cut.id, False)
        decision_hour.cast_vote(ctx, v, raise_.id, True)
    later = close(ctx, session)
    assert reload(later, cut).status == "REJECTED"
    assert reload(later, raise_).status == "ACCEPTED"
    assert dict(later.graph.resource("butce").shares) == RAISE


def test_silent_approval_also_checks_the_base(ctx):
    voters = _voters(ctx)
    cut = _budget(ctx, voters[0], "Herkese kesinti", CUT)
    raise_ = _budget(ctx, voters[1], "Herkese artış", RAISE, queued=False)
    assert raise_.status == "SILENT"
    session = decision_hour.open_session(ctx)
    for v in voters:
        decision_hour.cast_vote(ctx, v, cut.id, True)
    later = close(ctx, session)
    proposals.end_silent_period(later, reload(later, raise_))
    assert reload(later, raise_).status == "CONFLICT"


def test_ballot_warns_about_proposals_on_the_same_resource(ctx):
    voters = _voters(ctx)
    cut = _budget(ctx, voters[0], "Herkese kesinti", CUT)
    raise_ = _budget(ctx, voters[1], "Herkese artış", RAISE)
    decision_hour.open_session(ctx)
    notes = {e["proposal"]["id"]: e["shared_resource_notes"]
             for e in decision_hour.ballot(ctx, voters[2])["items"]}
    assert notes[raise_.id] == [f"№{cut.id} ile aynı kaynağı etkiliyor; önce №{cut.id} uygulanır."]
    assert notes[cut.id] == [(f"№{raise_.id} ile aynı kaynağı etkiliyor; önce bu öneri uygulanır, "
                              f"kabul edilirse №{raise_.id} uygulanamaz.")]
    assert ctx.db.execute(select(Proposal).where(Proposal.status == "CONFLICT")).first() is None


def test_oracle_share_comment_is_regenerated_when_the_share_table_changes(ctx, client):
    voters = _voters(ctx)
    cut = _budget(ctx, voters[0], "Herkese kesinti", CUT)
    raise_ = _budget(ctx, voters[1], "Herkese artış", RAISE, queued=False)
    body = client.get(f"/proposals/{raise_.id}").json()
    assert "oracle_current" not in body  # paylar değişmedi
    session = decision_hour.open_session(ctx)
    for v in voters:
        decision_hour.cast_vote(ctx, v, cut.id, True)
    close(ctx, session)
    body = client.get(f"/proposals/{raise_.id}").json()
    assert body["oracle_current"]["cause"] == [cut.id]
    at_open = [line for line in body["oracle_comment"].split("\n") if line.startswith("Pay etkisi")]
    assert at_open and at_open[0] != body["oracle_current"]["lines"][-1]
    # Güncel yorum güncel tablodan: kesintiden sonra artış herkese eşit değil.
    assert body["share_effect"][0]["rows"][0]["old"] == 3600
