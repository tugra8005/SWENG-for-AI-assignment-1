from datetime import timedelta

import pytest
from sqlalchemy import select

from mesveret.db.models import CellarPost, CellarThread, Proposal
from mesveret.errors import Conflict, DomainError, Forbidden
from mesveret.services import cellar, proposals
from mesveret.services.proposals import ProposalInput
from tests.integration.helpers import headers_for
from tests.integration.world import make_user


def warned(ctx, nickname, **kw):
    u = make_user(ctx, nickname, **kw)
    cellar.acknowledge_entry(ctx, u)
    return u


def thread_with_posters(ctx, n=5, title="Özgür irade bir yanılsama mı?"):
    users = [warned(ctx, f"golge{i}") for i in range(n)]
    t = cellar.create_thread(ctx, users[0], title, "Determinizm doğruysa sorumluluk nerede?",
                             acknowledge=True)
    for i, u in enumerate(users[1:], start=1):
        cellar.reply(ctx.at(ctx.now + timedelta(minutes=i)), u, t.id, f"Yanıt {i}.",
                     acknowledge=True)
    return t, users


# --- giriş ve uyarılar ----------------------------------------------------------------------------


def test_first_entry_warning_must_be_acknowledged(ctx, client):
    u = make_user(ctx, "ayse")
    h = headers_for(ctx, u)
    assert client.get("/cellar/entry", headers=h).json()["needs_warning"] is True
    r = client.post("/cellar/threads", headers=h,
                    json={"title": "Zaman", "text": "Zaman akar mı?", "acknowledge": True})
    assert r.status_code == 409
    assert client.post("/cellar/entry/ack", headers=h).status_code == 200
    assert client.get("/cellar/entry", headers=h).json()["needs_warning"] is False
    r = client.post("/cellar/threads", headers=h,
                    json={"title": "Zaman", "text": "Zaman akar mı?", "acknowledge": True})
    assert r.status_code == 201


def test_first_post_in_each_thread_needs_the_warning(ctx):
    a, b = warned(ctx, "ayse"), warned(ctx, "bora")
    t = cellar.create_thread(ctx, a, "Bilgi", "Bilgi gerekçelendirilmiş doğru inanç mı?",
                             acknowledge=True)
    with pytest.raises(Conflict) as err:
        cellar.reply(ctx, b, t.id, "Gettier örnekleri?", acknowledge=False)
    assert "takma adı açığa çıkar" in err.value.message
    cellar.reply(ctx, b, t.id, "Gettier örnekleri?", acknowledge=True)
    cellar.reply(ctx, b, t.id, "İkinci yanıtım.", acknowledge=False)


# --- Gölge kimliği ---------------------------------------------------------------------------------


def test_shade_ids_are_stable_within_and_unlinkable_across_threads(ctx):
    a, b = warned(ctx, "ayse"), warned(ctx, "bora")
    t1 = cellar.create_thread(ctx, a, "Birinci", "Metin bir.", acknowledge=True)
    cellar.reply(ctx, a, t1.id, "Yine ben.", acknowledge=False)
    cellar.reply(ctx, b, t1.id, "Ben de.", acknowledge=True)
    t2 = cellar.create_thread(ctx, a, "İkinci", "Metin iki.", acknowledge=True)
    v1 = cellar.thread_view(ctx, t1.id, None)
    v2 = cellar.thread_view(ctx, t2.id, None)
    shades1 = [p["shade"] for p in v1["posts"]]
    assert shades1[0] == shades1[1] != shades1[2]
    assert v2["posts"][0]["shade"] != shades1[0]
    assert all(p["nickname"] is None for p in v1["posts"])
    assert all(len(p["shade"]) == 8 for p in v1["posts"])


# --- yükselme, üst sınır, kapasite -------------------------------------------------------------------


def test_reply_bumps_until_bump_limit(ctx):
    ctx.graph.set_article("mahzen_ust_sinir", {"deger": 2})
    ctx.invalidate_regulation()
    a = warned(ctx, "ayse")
    t1 = cellar.create_thread(ctx, a, "Eski", "eski", acknowledge=True)
    t2 = cellar.create_thread(ctx.at(ctx.now + timedelta(minutes=1)), a, "Yeni", "yeni",
                              acknowledge=True)
    order = lambda c: [t["id"] for t in cellar.list_threads(c, None)["threads"]]
    assert order(ctx) == [t2.id, t1.id]
    c2 = ctx.at(ctx.now + timedelta(minutes=2))
    cellar.reply(c2, a, t1.id, "bir", acknowledge=False)
    assert order(c2) == [t1.id, t2.id]
    c3 = ctx.at(ctx.now + timedelta(minutes=3))
    cellar.reply(c3, a, t2.id, "iki", acknowledge=False)
    c4 = ctx.at(ctx.now + timedelta(minutes=4))
    cellar.reply(c4, a, t1.id, "iki", acknowledge=False)  # 2. yanıt: sınıra ulaşıyor, yükseltir
    assert order(c4)[0] == t1.id
    c5 = ctx.at(ctx.now + timedelta(minutes=5))
    cellar.reply(c5, a, t2.id, "üç", acknowledge=False)
    c6 = ctx.at(ctx.now + timedelta(minutes=6))
    cellar.reply(c6, a, t1.id, "üç", acknowledge=False)  # sınırda: yükselemez
    assert order(c6)[0] == t2.id


def test_capacity_prunes_oldest_thread_permanently(ctx, graph):
    ctx.graph.set_article("mahzen_kapasite", {"deger": 3})
    ctx.invalidate_regulation()
    a = warned(ctx, "ayse")
    threads = [cellar.create_thread(ctx.at(ctx.now + timedelta(minutes=i)), a, f"Başlık {i}",
                                    f"Metin {i}", acknowledge=True) for i in range(4)]
    ctx.db.expire_all()
    assert ctx.db.get(CellarThread, threads[0].id) is None
    assert ctx.db.execute(
        select(CellarPost).where(CellarPost.thread_id == threads[0].id)
    ).first() is None
    assert graph.discourse_authors(threads[0].id) == {}
    listing = cellar.list_threads(ctx, None)
    assert [t["id"] for t in listing["threads"]] == [threads[3].id, threads[2].id, threads[1].id]
    assert listing["threads"][-1]["lifetime"] < listing["threads"][0]["lifetime"]


# --- referanslar -----------------------------------------------------------------------------------


def test_references_outside_the_thread_are_rejected(ctx):
    a = warned(ctx, "ayse")
    t1 = cellar.create_thread(ctx, a, "Bir", "ilk", acknowledge=True)
    t2 = cellar.create_thread(ctx, a, "İki", "ikinci", acknowledge=True)
    other_post = cellar.thread_view(ctx, t1.id, None)["posts"][0]["no"]
    own_post = cellar.thread_view(ctx, t2.id, None)["posts"][0]["no"]
    with pytest.raises(DomainError):
        cellar.reply(ctx, a, t2.id, f">>{other_post} buna bakın", acknowledge=False)
    with pytest.raises(DomainError):
        cellar.reply(ctx, a, t2.id, f"bkz. /mahzen/{t1.id}", acknowledge=False)
    cellar.reply(ctx, a, t2.id, f">>{own_post} katılıyorum", acknowledge=False)


# --- ifşa oylaması -----------------------------------------------------------------------------------


def test_only_posters_can_open_and_vote(ctx):
    t, users = thread_with_posters(ctx, n=3)
    outsider = warned(ctx, "yabanci")
    with pytest.raises(Forbidden):
        cellar.open_reveal_vote(ctx, outsider, t.id)
    cellar.open_reveal_vote(ctx, users[0], t.id)
    with pytest.raises(Conflict):
        cellar.open_reveal_vote(ctx, users[1], t.id)
    with pytest.raises(Forbidden):
        cellar.cast_reveal_vote(ctx, outsider, t.id, True)


def test_electorate_is_snapshot_of_posters_before_vote_opened(ctx):
    t, users = thread_with_posters(ctx, n=3)
    cellar.open_reveal_vote(ctx, users[0], t.id)
    late = warned(ctx, "gec")
    cellar.reply(ctx, late, t.id, "Ben de buradayım.", acknowledge=True)
    with pytest.raises(Forbidden):
        cellar.cast_reveal_vote(ctx, late, t.id, True)
    view = cellar.thread_view(ctx, t.id, users[0])
    assert view["vote"]["electorate_size"] == 3


def test_votes_are_secret_changeable_and_reveal_passes_above_half(ctx, ledger):
    t, users = thread_with_posters(ctx, n=5)
    cellar.open_reveal_vote(ctx, users[0], t.id)
    cellar.cast_reveal_vote(ctx, users[0], t.id, True)
    cellar.cast_reveal_vote(ctx, users[1], t.id, False)
    cellar.cast_reveal_vote(ctx, users[1], t.id, True)  # fikrini değiştirdi: 2 EVET
    view = cellar.thread_view(ctx, t.id, users[1])
    assert view["vote"]["my_vote"] is True
    assert "yes" not in view["vote"] and "yes_count" not in view["vote"]
    assert view["revealed"] is None
    assert not [r for r in ledger.records if r["type"].startswith("MAHZEN")]
    result = cellar.cast_reveal_vote(ctx, users[3], t.id, True)  # 3/5 > yarı
    assert result["revealed"] is True
    view = cellar.thread_view(ctx, t.id, None)
    assert [p["nickname"] for p in view["posts"]] == [u.nickname for u in users]
    [rec] = ledger.of_type("MAHZEN_IFSA")
    posts = rec["payload"]["mesajlar"]
    assert {p["takma_ad"] for p in posts} == {u.nickname for u in users}
    assert all(len(p["golge"]) == 8 for p in posts)
    draft = ctx.db.get(Proposal, view["revealed"]["draft_proposal_id"])
    assert draft.status == "DRAFT" and draft.proposer_id == users[0].id
    with pytest.raises(Conflict):
        cellar.reply(ctx, users[4], t.id, "Artık donduruldu.", acknowledge=False)


def test_exactly_half_is_not_enough(ctx):
    t, users = thread_with_posters(ctx, n=4)
    cellar.open_reveal_vote(ctx, users[0], t.id)
    cellar.cast_reveal_vote(ctx, users[0], t.id, True)
    result = cellar.cast_reveal_vote(ctx, users[1], t.id, True)
    assert result["revealed"] is False


def test_revealed_draft_enters_normal_flow_when_submitted(ctx):
    t, users = thread_with_posters(ctx, n=3)
    cellar.open_reveal_vote(ctx, users[0], t.id)
    cellar.cast_reveal_vote(ctx, users[0], t.id, True)
    cellar.cast_reveal_vote(ctx, users[1], t.id, True)
    draft_id = cellar.thread_view(ctx, t.id, None)["revealed"]["draft_proposal_id"]
    with pytest.raises(Forbidden):
        proposals.submit_draft(ctx, users[1], draft_id, ProposalInput(type="KONU"))
    p = proposals.submit_draft(ctx, users[0], draft_id, ProposalInput(
        type="KONU", addressee="takvim", area_id="kultur", scope_id="genel",
    ))
    assert p.status == "SILENT"
    assert p.payload["cellar_thread_id"] == t.id


def test_signing_reveals_only_that_post(ctx):
    a, b = warned(ctx, "ayse"), warned(ctx, "bora")
    t = cellar.create_thread(ctx, a, "İmza", "Bunu ben yazdım.", acknowledge=True)
    cellar.reply(ctx, a, t.id, "Bunu imzalamıyorum.", acknowledge=False)
    posts = cellar.thread_view(ctx, t.id, None)["posts"]
    with pytest.raises(Forbidden):
        cellar.sign_post(ctx, b, posts[0]["no"])
    cellar.sign_post(ctx, a, posts[0]["no"])
    posts = cellar.thread_view(ctx, t.id, None)["posts"]
    assert posts[0]["nickname"] == "ayse" and posts[1]["nickname"] is None


def test_raid_cluster_in_thread_is_excluded_from_electorate(ctx):
    t, users = thread_with_posters(ctx, n=2)
    raiders = [warned(ctx, f"akin{i}", created_days_ago=0) for i in range(4)]
    for i, r in enumerate(raiders):
        cellar.reply(ctx.at(ctx.now + timedelta(minutes=10 + i)), r, t.id, "Evet ifşa!",
                     acknowledge=True)
    cellar.open_reveal_vote(ctx.at(ctx.now + timedelta(minutes=20)), users[0], t.id)
    view = cellar.thread_view(ctx, t.id, raiders[0])
    assert view["vote"]["electorate_size"] == 2
    assert view["vote"]["flagged_self"] is not None
    with pytest.raises(Forbidden):
        cellar.cast_reveal_vote(ctx, raiders[0], t.id, True)


def test_cellar_content_never_appears_in_square_listings(ctx, client):
    a = warned(ctx, "ayse")
    cellar.create_thread(ctx, a, "Gizli", "Mahzen metni.", acknowledge=True)
    assert client.get("/topics").json() == []
    assert client.get("/proposals").json() == []
