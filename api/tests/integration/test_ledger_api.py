from tests.integration.helpers import open_topic, post
from tests.integration.world import make_user


def test_content_hash_can_be_looked_up_and_verified(ctx, client):
    a = make_user(ctx, "ayse")
    topic = open_topic(ctx, a)
    msg = post(ctx, a, topic, "Defterde durmalı.")
    view = client.get(f"/topics/{topic.id}").json()
    h = next(m for m in view["messages"] if m["id"] == msg.id)["ledger_hash"]
    assert h and len(h) == 64
    rec = client.get(f"/ledger/records/{h[:10]}").json()
    assert rec["payload"]["metin"] == "Defterde durmalı."
    verify = client.get("/ledger/verify").json()
    assert verify["ok"] is True
    assert verify["nodes"][0]["status"] == "tutarli"


def test_short_or_unknown_hash(client, ctx):
    assert client.get("/ledger/records/abc").status_code == 422
    assert client.get("/ledger/records/abcdef0123").status_code == 404


def test_pending_records_are_sent_when_leader_returns(ctx, ledger, client):
    a = make_user(ctx, "ayse")
    ledger.fail = True
    topic = open_topic(ctx, a)
    post(ctx, a, topic, "Lider yokken yazıldı.")
    assert ledger.records == []
    ledger.fail = False
    client.get("/ledger/verify")
    assert any(r["payload"].get("metin") == "Lider yokken yazıldı." for r in ledger.records)
    seqs = [r["seq"] for r in ledger.records]
    assert seqs == sorted(seqs)
