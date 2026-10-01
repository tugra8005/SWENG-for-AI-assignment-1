import io

from PIL import Image, ImageDraw

from mesveret.db.models import Media
from mesveret.services import media, proposals
from mesveret.services.proposals import ProposalInput
from tests.integration.helpers import headers_for, open_topic
from tests.integration.world import make_user


def _jpeg(color=(30, 30, 30)) -> bytes:
    img = Image.new("RGB", (640, 480), (230, 220, 200))
    ImageDraw.Draw(img).ellipse((120, 80, 520, 400), fill=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _upload(client, ctx, user, alt="Salonda perde ve projeksiyon", data=None):
    return client.post("/media", headers=headers_for(ctx, user),
                       files={"file": ("foto.jpg", data or _jpeg(), "image/jpeg")},
                       data={"alt": alt})


def test_upload_attach_to_message_and_serve_both_versions(ctx, client, ledger):
    a = make_user(ctx, "ayse")
    topic = open_topic(ctx, a)
    r = _upload(client, ctx, a)
    assert r.status_code == 201, r.text
    pic = r.json()
    assert pic["id"].startswith("g") and (pic["width"], pic["height"]) == (640, 480)
    assert pic["ledger_hash"] is None  # eklenene kadar deftere yazılmaz
    assert ledger.of_type("GORSEL_EKLENDI") == []

    r = client.post(f"/topics/{topic.id}/messages", headers=headers_for(ctx, a),
                    json={"text": "Dün akşamki gösterimden.", "media_ids": [pic["id"]]})
    assert r.status_code == 201, r.text
    msg = next(m for m in client.get(f"/topics/{topic.id}").json()["messages"]
               if m["id"] == r.json()["id"])
    assert [m["id"] for m in msg["media"]] == [pic["id"]]
    assert msg["media"][0]["alt"] == "Salonda perde ve projeksiyon"
    assert len(msg["media"][0]["ledger_hash"]) == 64

    rec = ledger.of_type("GORSEL_EKLENDI")[0]["payload"]
    row = ctx.db.get(Media, pic["id"])
    assert rec == {"gorsel": pic["id"], "sha256": row.sha256, "alt": row.alt,
                   "ek": f"mesaj:{msg['id']}", "yukleyen": "ayse", "kaynak": None}

    baski = client.get(f"/media/{pic['id']}/baski")
    assert baski.status_code == 200 and baski.headers["content-type"] == "image/png"
    ozgun = client.get(f"/media/{pic['id']}/ozgun")
    assert ozgun.headers["content-type"] == "image/jpeg"
    import hashlib

    assert hashlib.sha256(ozgun.content).hexdigest() == rec["sha256"]  # defterdeki hash doğrulanır
    assert client.get(f"/media/{pic['id']}/kucuk").status_code == 404
    assert client.get("/media/gyok/baski").status_code == 404


def test_upload_requires_login_alt_text_and_an_image(ctx, client):
    a = make_user(ctx, "ayse")
    anon = client.post("/media", files={"file": ("a.jpg", _jpeg(), "image/jpeg")},
                       data={"alt": "bir şey"})
    assert anon.status_code == 401
    r = _upload(client, ctx, a, alt="")
    assert r.status_code == 422 and "alt metin zorunlu" in r.json()["detail"]
    r = _upload(client, ctx, a, data=b"%PDF-1.7 bir belge")
    assert r.status_code == 422 and r.json()["detail"] == "Dosya bir görsel değil ya da okunamadı."


def test_only_own_unattached_pictures_can_be_attached(ctx, client):
    a, b = make_user(ctx, "ayse"), make_user(ctx, "bora")
    topic = open_topic(ctx, a)
    pic = _upload(client, ctx, a).json()
    r = client.post(f"/topics/{topic.id}/messages", headers=headers_for(ctx, b),
                    json={"text": "Benim de fotoğrafım olsun.", "media_ids": [pic["id"]]})
    assert r.status_code == 403
    ok = client.post(f"/topics/{topic.id}/messages", headers=headers_for(ctx, a),
                     json={"text": "Gösterimden.", "media_ids": [pic["id"]]})
    assert ok.status_code == 201
    again = client.post(f"/topics/{topic.id}/messages", headers=headers_for(ctx, a),
                        json={"text": "Tekrar.", "media_ids": [pic["id"]]})
    assert again.status_code == 409
    five = [_upload(client, ctx, a).json()["id"] for _ in range(5)]
    r = client.post(f"/topics/{topic.id}/messages", headers=headers_for(ctx, a),
                    json={"text": "Beş fotoğraf.", "media_ids": five})
    assert r.status_code == 422 and r.json()["detail"] == "En fazla 4 görsel eklenebilir."


def test_unattached_upload_limit(ctx, client, monkeypatch):
    a = make_user(ctx, "ayse")
    monkeypatch.setattr(media, "MAX_UNATTACHED", 2)
    assert _upload(client, ctx, a).status_code == 201
    assert _upload(client, ctx, a).status_code == 201
    r = _upload(client, ctx, a)
    assert r.status_code == 409 and "kullanmadığınız 2 görsel" in r.json()["detail"]


def test_picture_of_deleted_message_is_gone(ctx, client):
    a, b = make_user(ctx, "ayse"), make_user(ctx, "bora")
    topic = open_topic(ctx, a)
    pic = _upload(client, ctx, a, alt="Kişisel bilgi içeren ekran görüntüsü").json()
    r = client.post(f"/topics/{topic.id}/messages", headers=headers_for(ctx, a),
                    json={"text": "Şuna bakın.", "media_ids": [pic["id"]]})
    msg_id = r.json()["id"]
    assert client.get(f"/media/{pic['id']}/baski").status_code == 200
    p = proposals.open_proposal(ctx, b, ProposalInput(
        type="SILME", target_message_id=msg_id, content_rules=["IK-3"], excerpt="Şuna bakın.",
    ))
    proposals.accept(ctx, p)
    ctx.commit()
    r = client.get(f"/media/{pic['id']}/ozgun")
    assert r.status_code == 410
    assert r.json()["detail"] == f"Bu görselin bulunduğu mesaj #{p.id} numaralı oylamayla silindi."
    deleted = next(m for m in client.get(f"/topics/{topic.id}").json()["messages"]
                   if m["id"] == msg_id)
    assert "media" not in deleted


def test_topic_proposal_cover_becomes_topic_cover_and_dies_with_topic(ctx, client):
    a, b = make_user(ctx, "ayse"), make_user(ctx, "bora")
    pic = _upload(client, ctx, a, alt="Eski bir sinema salonunun girişi").json()
    r = client.post("/proposals", headers=headers_for(ctx, a), json={
        "type": "KONU", "title": "Mahalle sineması", "body": "Ayda bir gösterim.",
        "area_id": "sinema", "scope_id": "genel", "cover_media_id": pic["id"],
    })
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert client.get(f"/proposals/{pid}").json()["cover"]["id"] == pic["id"]
    p = proposals.get_proposal(ctx, pid)
    proposals.accept(ctx.at(p.deadline_at), p)
    ctx.commit()
    view = client.get(f"/proposals/{pid}").json()
    topic = client.get(f"/topics/{view['topic_id']}").json()
    assert topic["cover"]["alt"] == "Eski bir sinema salonunun girişi"
    assert next(t for t in client.get("/topics").json() if t["id"] == topic["id"])["cover"]

    d = proposals.open_proposal(ctx, b, ProposalInput(
        type="SILME", target_topic_id=topic["id"], content_rules=["IK-1"], excerpt="Ayda bir",
    ))
    proposals.accept(ctx, d)
    ctx.commit()
    assert client.get(f"/media/{pic['id']}/baski").status_code == 410
    assert client.get(f"/proposals/{pid}").json()["cover"] is None


def test_cover_only_on_new_topic_proposals(ctx, client):
    a = make_user(ctx, "ayse")
    topic = open_topic(ctx, a)
    pic = _upload(client, ctx, a).json()
    r = client.post("/proposals", headers=headers_for(ctx, a), json={
        "type": "KAPANIS", "target_topic_id": topic.id, "body": "Ayda bir film izlenir.",
        "cover_media_id": pic["id"],
    })
    assert r.status_code == 422
    assert r.json()["detail"] == "Kapak görseli yalnızca yeni konu önerisine eklenir."
