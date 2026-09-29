"""Sınıf gösterimi modu (yalnızca geliştirme ortamı).

Her adım yığını deterministik bir duruma getirir ve o adımda hangi kullanıcıyla hangi sayfanın
açılacağını söyler. ``goto`` her zaman baştan kurar (tohum, saati dondurma, taban durumu, önceki
adımların geçişleri); canlıda bir adım bozulursa onunla kurtarılır. ``next`` yalnızca bir sonraki
adımın geçişini uygular ve hızlıdır.

Taban durum: tohum + Karar Saati #1 (tohumdaki oy planı ve senaryo 2'de canlı verilen ceren oyu)
açılıp kapanmış. Sonuçlar 4.–7.
adımlarda gösterilir; 1.–3. adımlar bu sonuçlardan etkilenmez.

Saat demo boyunca durur (``clock.freeze``): geri sayımlar, zaman damgaları ve defter hash'leri iki
çalıştırmada aynıdır; arka plan zamanlayıcısı kendiliğinden hiçbir iş işlemez. Zamanı yalnızca
adım geçişleri ilerletir. ``finish`` saati yeniden akıtır.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select

from mesveret import clock
from mesveret.context import Ctx
from mesveret.db.models import CellarThread, DemoState, MessageVersion, Topic, User
from mesveret.errors import Conflict, DomainError
from mesveret.services import decision_hour, devtools, scheduler
from mesveret.services import seed as seed_service


@dataclass(frozen=True)
class Screen:
    user: str
    path: str
    show: str


@dataclass(frozen=True)
class Step:
    key: str
    title: str
    answers: str  # konuşmanın cevap verdiği soru
    enter: Callable[[Ctx], list[str]] | None
    screens: Callable[[Ctx], list[Screen]]


def _ids(ctx: Ctx) -> dict[str, int]:
    ids = seed_service.scenario_ids(ctx)
    thread = ctx.db.execute(
        select(CellarThread.id).where(CellarThread.title == "Çoğunluk haklı olabilir mi?")
    ).scalar_one_or_none()
    ids["mahzen"] = thread or 0
    topic = ctx.db.execute(
        select(Topic.id).where(Topic.accepted_proposal_id == ids["istanbul"])
    ).scalar_one_or_none()
    ids["istanbul_konu"] = topic or 0
    for key, title in (("bisiklet", "Bisiklet yolları"), ("park", "Parkların kapanış saati")):
        ids[key] = ctx.db.execute(select(Topic.id).where(Topic.title == title)).scalar_one()
    ids["hale_mesaj"] = ctx.db.execute(
        select(MessageVersion.message_id).where(MessageVersion.text == "Eleştiri olur, hakaret olmaz.")
    ).scalars().first() or 0
    return ids


def _advance_one_day(ctx: Ctx) -> list[str]:
    target = seed_service.SEED_NOW + timedelta(days=1)
    clock.set_now(ctx.db, target)
    ctx.db.commit()
    return scheduler.tick(ctx.at(target), target)


def _tamper(ctx: Ctx) -> list[str]:
    out = devtools.tamper_regulation(ctx, "yonetmelik_esigi", {"oran": "1/2", "karsilastirma": ">"})
    ctx.db.commit()
    return [f"yonetmelik_esigi oylamasız değiştirildi: {out['old']['oran']} → 1/2"]


def _open_session(ctx: Ctx) -> list[str]:
    out = devtools._open_decision_hour(ctx, scripted=False)
    return [f"Karar Saati #{out['session']['id']} açıldı; açılışta geri alındı: {k}"
            for k in out["silent"]]


STEPS: list[Step] = [
    Step("1", "Kayıt ve profil", "kimlik: herkese görünen ne, gizli ne?", None, lambda c: [
        Screen("aylin", "/profil/aylin",
               "Yalnızca size görünür: ad, e-posta, adres, doğum tarihi. Kapsam üyelikleri: "
               "Ankara (adresten), 35–49 yaş (yaştan)."),
        Screen("ceren", "/profil/aylin", "Başkası yalnızca takma adı, rolleri ve havale sayısını görür."),
    ]),
    Step("2", "Öneri ve sessiz onay", "ölçek: her şey oylanırsa kimse oy vermez", None, lambda c: [
        Screen("aylin", f"/oneri/{_ids(c)['istanbul']}",
               "Hızlı şerit: 24 saat itiraza açık; itiraz eşiği aşılmazsa sessiz onayla kabul."),
    ]),
    Step("3", "İstanbul vakası: R2 daraltma", "bölme: parça bütün adına karar veremez",
         _advance_one_day, lambda c: [
             Screen("aylin", f"/konu/{_ids(c)['istanbul_konu']}",
                    "Bir gün geçti: itiraz yok, öneri konu oldu. R2 kutusu: İstanbul payı."),
             Screen("aylin", f"/oneri/{_ids(c)['istanbul']}",
                    "Başlık: talep (bütçenin tamamı) üstü çizili, etki (İstanbul payı); pay çubuğu."),
         ]),
    Step("4", "Eşzamanlı çoğunluk", "çoğunluk tiranlığı: bütün, parçayı ezemez", None, lambda c: [
        Screen("ayse", f"/oneri/{_ids(c)['pay_yarisi']}",
               "Pay etkisi: İstanbul -%50,0 orantısız. Sonuç: Genel'de geçti, İstanbul'da geçemedi → "
               "Reddedildi."),
    ]),
    Step("5", "Havale ve Karar Saati", "uzmanlar: oyu güvendiğine ver, o hesap versin", None,
         lambda c: [
             Screen("aylin", "/havale",
                    "Zincir aylin → baris → ceren. Üstte bekleyen havale (elif): kabul edilmedikçe "
                    "ağırlığa sayılmaz."),
             Screen("ceren", f"/karar-saati/1?izle={_ids(c)['metro']}",
                    "Mühürlü oylar açılıyor: ceren ×3 açık (temsilci), diğerleri gizli, yalnızca toplam."),
         ]),
    Step("6", "Kapanış ve Şerh", "uzlaşma: kaybeden taraf kayda geçer", None, lambda c: [
        Screen("zeynep", f"/konu/{_ids(c)['park']}",
               "KARAR kutusu (onay oylamasının kazananı). Şerhler → Şerh ekle → metin → Şerhi mühürle."),
    ]),
    Step("7", "Silme", "çoğunluk tiranlığı: silmek istisnadır", None, lambda c: [
        Screen("hale", f"/konu/{_ids(c)['bisiklet']}",
               "Sansür şeritleri: #11 IK-1 (2/3 geçti), #12 yazarın isteği. Hakaret mesajı duruyor: "
               "%60 yetmedi."),
        Screen("emre", f"/oneri/yeni?type=SILME&message={_ids(c)['hale_mesaj']}",
               "Kural seçmeden gerekçe yazıp Öneriyi aç → R7: açılışta reddedilir."),
    ]),
    Step("8", "Değiştirilemez maddeler", "çoğunluk tiranlığı: kuralı değiştirerek kazanmak",
         None, lambda c: [
             Screen("aylin", "/oneri/yeni?type=YONETMELIK&article=yonetmelik_esigi",
                    "Yeni oran 1/2, karşılaştırma > → Öneriyi aç → R8: açılışta reddedilir."),
             Screen("aylin", "/oneri/yeni?type=YONETMELIK&action=kaldir&article=D3",
                    "Şerh hakkını (D3) kaldırma → Öneriyi aç → reddedilir."),
         ]),
    Step("9", "Mahzen", "açıklar: anonimlik ve hesap verebilirlik", None, lambda c: [
        Screen("ayse", "/mahzen", "Kararma ve uyarı → anladım, devam. Alt sıralar çürüyor."),
        Screen("ayse", f"/mahzen/{_ids(c)['mahzen']}",
               "İfşa oylaması: [ evet ] → eşik aşılır, ışık yanar: Gölge kimliklerinin üstüne takma adlar."),
    ]),
    Step("10a", "Operatörün sessiz değişikliği", "açıklar: kurala güveni kim korur?", _tamper,
         lambda c: [
             Screen("aylin", "/defter", "Doğrula → Zincir: tutarlı, Yönetmelik: FARKLI (bordo)."),
         ]),
    Step("10b", "Karar Saati açılışında geri alınır", "açıklar: tespit ve kalıcı iz", _open_session,
         lambda c: [
             Screen("aylin", "/defter",
                    "Doğrula → Yönetmelik: tutarlı. Geçmiş: tespit edildi ve GERİ ALINDI; liste hiç boşalmaz."),
         ]),
]
KEYS = [s.key for s in STEPS]


def _step(key: str) -> Step:
    key = key.lower()
    if key == "10":
        key = "10a"
    for s in STEPS:
        if s.key == key:
            return s
    raise DomainError(f"Böyle bir demo adımı yok: {key}. Adımlar: {', '.join(KEYS)}.")


def _state(ctx: Ctx) -> DemoState | None:
    return ctx.db.get(DemoState, 1)


def _save(ctx: Ctx, key: str) -> None:
    row = _state(ctx) or DemoState(id=1, step=key, updated_at=ctx.now)
    row.step, row.updated_at = key, clock.now(ctx.db)
    ctx.db.merge(row)
    ctx.db.commit()


def view(ctx: Ctx, key: str | None = None) -> dict | None:
    """Adımın başlığı ve ekranları (terminal ve geliştirme menüsü için)."""
    st = _state(ctx)
    key = key or (st.step if st else None)
    if key is None:
        return None
    step = _step(key)
    return {
        "step": step.key, "index": KEYS.index(step.key) + 1, "total": len(KEYS),
        "title": step.title, "answers": step.answers,
        "screens": [{"user": s.user, "path": s.path, "show": s.show} for s in step.screens(ctx)],
        "now": clock.now(ctx.db), "frozen": clock.is_frozen(ctx.db),
        "next": KEYS[KEYS.index(step.key) + 1] if step.key != KEYS[-1] else None,
    }


def _view(ctx: Ctx, key: str) -> dict:
    out = view(ctx, key)
    assert out is not None
    return out


def goto(ctx: Ctx, key: str, *, rebuild: Callable[[], Ctx]) -> dict:
    """Adımı baştan kurar: tohum, saati dondurma, taban durum ve o adıma kadarki geçişler.

    ``rebuild`` yığını sıfırlayıp tohumlar ve taze bir bağlam döner (CLI: ``seed --reset``;
    testler: test veritabanı)."""
    target = _step(key)
    events: list[str] = []
    # Çağıranın oturumunda açık işlem kalırsa sıfırlama (DROP/TRUNCATE) onu bekler ve kilitlenir.
    ctx.db.rollback()
    with scheduler.exclusive(ctx.db):
        c = rebuild()
        clock.freeze(c.db, seed_service.SEED_NOW)
        c.db.commit()
        c = c.at(clock.now(c.db))
        devtools._open_decision_hour(c, scripted=True)
        # Senaryo 2'de sunucunun canlı verdiği oy: ceren (ağırlığı 3, oyu açık) №9'a EVET.
        ceren = c.db.execute(select(User).where(User.nickname == "ceren")).scalar_one()
        decision_hour.cast_vote(c, ceren, seed_service.scenario_ids(c)["metro"], True)
        devtools.close_decision_hour(c)
        for step in STEPS[: KEYS.index(target.key) + 1]:
            c = c.at(clock.now(c.db))
            if step.enter is not None:
                events += step.enter(c)
        _save(c, target.key)
        out = {**_view(c, target.key), "events": events}
        c.db.close()
        return out


def next_step(ctx: Ctx, *, rebuild: Callable[[], Ctx]) -> dict:
    """Yalnızca bir sonraki adımın geçişini uygular. Demo başlamadıysa ya da saat donmuş değilse
    (ör. ``finish`` sonrası) o adımı baştan kurar."""
    st = _state(ctx)
    if st is None:
        raise Conflict("Demo başlamadı: meşveret-dev demo goto 1")
    idx = KEYS.index(st.step)
    if idx + 1 >= len(KEYS):
        raise Conflict("Son adımdasınız. Baştan başlamak için: meşveret-dev demo goto 1")
    step = STEPS[idx + 1]
    if not clock.is_frozen(ctx.db):
        return goto(ctx, step.key, rebuild=rebuild)
    with scheduler.exclusive(ctx.db):
        c = ctx.at(clock.now(ctx.db))
        events = step.enter(c) if step.enter is not None else []
        _save(c, step.key)
        out = {**_view(c, step.key), "events": events}
        c.db.commit()
        return out


def prev_step(ctx: Ctx, *, rebuild: Callable[[], Ctx]) -> dict:
    st = _state(ctx)
    if st is None:
        raise Conflict("Demo başlamadı: meşveret-dev demo goto 1")
    idx = KEYS.index(st.step)
    if idx == 0:
        raise Conflict("İlk adımdasınız.")
    return goto(ctx, KEYS[idx - 1], rebuild=rebuild)


def finish(ctx: Ctx) -> None:
    """Demo modundan çık: saat donduğu andan itibaren yeniden akar."""
    clock.unfreeze(ctx.db)
    st = _state(ctx)
    if st is not None:
        ctx.db.delete(st)
    ctx.db.commit()
