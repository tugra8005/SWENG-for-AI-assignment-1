"""Site içi bildirimler: Karar Saati sonucu, sessiz onay ve itirazla yavaş şerit."""

from datetime import timedelta

from sqlalchemy import func, select

from mesveret.db.models import Ballot, Notification
from mesveret.services import decision_hour, notifications, scheduler, seed
from mesveret.services.oracle import ORACLE_ID
from tests.integration.helpers import headers_for
from tests.integration.test_seed import seeded, user  # noqa: F401  (fikstür)


def _of(ctx, nick, kind):
    return list(ctx.db.execute(select(Notification).where(
        Notification.user_id == user(ctx, nick).id, Notification.kind == kind,
    ).order_by(Notification.id)).scalars())


def _close_first_session(ctx):
    session = decision_hour.open_session(ctx)
    decision_hour.apply_vote_plan(ctx, session)
    ctx.commit()
    decision_hour.cast_vote(ctx, user(ctx, "ceren"), seed.scenario_ids(ctx)["metro"], True)
    later = ctx.at(session.closes_at)
    decision_hour.close_session(later, session)
    later.commit()
    return later, session


def test_session_close_notifies_voters_delegators_and_proposers(seeded):  # noqa: F811
    ctx, session = _close_first_session(seeded)
    ids = seed.scenario_ids(ctx)
    metro = f"№{ids['metro']} Gece metro seferleri: kabul edildi"

    [ceren] = _of(ctx, "ceren", "KARAR_SAATI")
    assert ceren.title == f"Karar Saati #{session.id} sonuçlandı"
    assert ceren.link == f"/karar-saati/{session.id}"
    assert f"{metro} · oyunuz EVET" in ceren.lines

    # aylin → baris (genel), baris → ceren (Ulaşım): metroda aylin'in oyunu ceren kullandı.
    [aylin] = _of(ctx, "aylin", "KARAR_SAATI")
    assert f"{metro} · oyunuz havaleyle ceren üzerinden: EVET" in aylin.lines

    # Öneri sahibi oy vermese de sonucu alır.
    [umut] = _of(ctx, "umut", "KARAR_SAATI")
    assert any(line.startswith(metro) and "sizin öneriniz" in line for line in umut.lines)

    # Eşzamanlı oylama: iki kapsamda oy veren kişi iki oyunu da kapsam adıyla görür.
    both = ctx.db.execute(
        select(Ballot.voter_id).where(Ballot.session_id == session.id,
                                      Ballot.proposal_id == ids["pay_yarisi"])
        .group_by(Ballot.voter_id).having(func.count() == 2)
    ).scalars().first()
    [n] = ctx.db.execute(select(Notification).where(
        Notification.user_id == both, Notification.kind == "KARAR_SAATI")).scalars()
    [line] = [x for x in n.lines if x.startswith(f"№{ids['pay_yarisi']} ")]
    assert "(Genel)" in line and "(İstanbul)" in line

    # Hâtif giriş yapamaz, bildirim almaz; oy vermeyen ve öneri açmayan da almaz.
    assert ctx.db.execute(select(Notification).where(Notification.user_id == ORACLE_ID)).first() is None
    assert _of(ctx, "kaba_kul", "KARAR_SAATI") == []
    # Kişi başına oturum başına tek bildirim.
    per_user = ctx.db.execute(select(Notification.user_id, func.count()).where(
        Notification.kind == "KARAR_SAATI").group_by(Notification.user_id)).all()
    assert per_user and all(c == 1 for _, c in per_user)


def test_objection_and_silent_approval_notify_the_proposer(seeded):  # noqa: F811
    ctx = seeded
    ids = seed.scenario_ids(ctx)
    # Tohumda metro itirazla yavaş şeride geçti.
    [slow] = _of(ctx, "umut", "YAVAS_SERIT")
    assert slow.title == "Önerinize itiraz edildi"
    assert slow.lines[0].startswith(f"№{ids['metro']} Gece metro seferleri: itiraz eşiği aşıldı (3/3)")
    assert slow.link == f"/oneri/{ids['metro']}"

    # İstanbul önerisi sessiz onayla kabul edilir; başlık daraltılmış etkidir.
    assert _of(ctx, "emre", "SESSIZ_ONAY") == []
    target = ctx.now + timedelta(hours=25)
    scheduler.tick(ctx.at(target), target)
    [ok] = _of(ctx, "emre", "SESSIZ_ONAY")
    assert ok.title == "Öneriniz kabul edildi"
    assert ok.lines == [(f"№{ids['istanbul']} Etkinlik bütçesinin İstanbul payı: sessiz onay "
                         "süresi itiraz eşiği aşılmadan doldu; öneri kabul edildi.")]


def test_notifications_api_lists_and_marks_read(seeded, client):  # noqa: F811
    ctx, _ = _close_first_session(seeded)
    h = headers_for(ctx, user(ctx, "umut"))
    assert client.get("/notifications").status_code == 401
    body = client.get("/notifications", headers=h).json()
    assert body["unread"] == 3  # itiraz (tohum) + metro dilekçesi + Karar Saati
    # En yenisi önce; metro kabul edilince Ulaştırma Bakanlığı'na dilekçe gitti.
    assert [i["kind"] for i in body["items"]] == ["KARAR_SAATI", "DILEKCE", "YAVAS_SERIT"]
    sent = body["items"][1]
    assert sent["title"] == "Dilekçeniz iletildi"
    assert sent["lines"][1] == ("Alıcı: T.C. Ulaştırma ve Altyapı Bakanlığı. Yasal yanıt süresi "
                                "30 gün.")
    assert not any(i["read"] for i in body["items"])

    first = body["items"][2]["id"]
    assert client.post("/notifications/read", json={"ids": [first]}, headers=h).json() == {"marked": 1}
    assert client.get("/notifications/unread", headers=h).json() == {"unread": 2}
    assert client.post("/notifications/read", json={}, headers=h).json() == {"marked": 2}
    assert client.get("/notifications/unread", headers=h).json() == {"unread": 0}

    # Başkasının bildirimi işaretlenemez.
    other = headers_for(ctx, user(ctx, "ceren"))
    assert client.post("/notifications/read", json={"ids": [first]}, headers=other).json() == {"marked": 0}
    # ceren: Karar Saati + semt pazarı konusuna yazdığı için İBB'nin yanıtı (tohum)
    assert notifications.unread_count(ctx, user(ctx, "ceren")) == 2
