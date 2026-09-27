"""Tohum veri ve demo senaryoları.

Sahte saat ``SEED_NOW`` anına (Salı 29 Eylül 2026, 10:00 İstanbul) kurulur. Geçmiş tarihli
içerik bir zaman çizelgesine yazılır ve zaman sırasıyla oluşturulur; böylece defter
kayıtlarının zaman damgaları içeriğin gerçek zamanıyla aynı olur. Tüm tohum hesaplarının
şifresi ``DEMO_PASSWORD``.

Senaryolar (README'de adım adım):
1. İstanbul vakası — R2 daraltma; bölünemeyen kaynakla red.
2. Havale zinciri — aylin → baris (genel), baris → ceren (Ulaşım); ceren'in ağırlığı 3.
3. Yönetmelik değişikliği — %60 geçemez, 2/3 geçer.
4. Silme — mesaj oylamayla silinir, sansür şeridi, defterde durur.
5. Kapanış — üç rakip metin, onay oylaması, kaybeden Şerh ekler.
6. Mahzen — ifşa oylaması, geçiş animasyonu, öneri taslağı.
7. Baskın — art arda açılmış bağlantılı hesaplar işaretlenip dışlanır.
8. Hâtif — etiket önerisi ve deterministik oy.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from mesveret import clock
from mesveret.context import Ctx
from mesveret.db.models import DevVotePlan, Proposal, SchedulerState, Topic, User
from mesveret.domain.ontology import ResourceInfo, ResourceKind
from mesveret.domain.scopes import ScopeSubtype
from mesveret.services import auth, cellar, delegation, ontology, oracle, proposals, topics
from mesveret.services.proposals import ProposalInput

SEED_NOW = datetime(2026, 9, 29, 7, 0, tzinfo=UTC)  # Salı 10:00 İstanbul
DEMO_PASSWORD = "mesveret-demo"

AREAS = [
    ("kultur", "Kültür", None, ("kültür", "sanat", "festival")),
    ("sinema", "Sinema", "kultur", ("sinema", "film", "yönetmen", "gösterim")),
    ("belgesel", "Belgesel", "sinema", ("belgesel",)),
    ("kisa-film", "Kısa film", "sinema", ("kısametraj",)),
    ("edebiyat", "Edebiyat", "kultur", ("edebiyat", "roman", "kitap", "yazar")),
    ("siir", "Şiir", "edebiyat", ("şiir", "şair", "dize")),
    ("kent", "Kent", None, ("kent", "şehir", "mahalle", "belediye")),
    ("ulasim", "Ulaşım", "kent", ("ulaşım", "otobüs", "metro", "tramvay", "sefer")),
    ("bisiklet", "Bisiklet", "ulasim", ("bisiklet", "pedal")),
    ("parklar", "Parklar ve yeşil alan", "kent", ("park", "yeşil", "bahçe")),
    ("bilim", "Bilim ve düşünce", None, ("bilim", "araştırma")),
    ("felsefe", "Felsefe", "bilim", ("felsefe", "filozof", "düşünce")),
    ("etik", "Etik", "felsefe", ("etik", "ahlak", "erdem")),
    ("teknoloji", "Teknoloji", "bilim", ("teknoloji", "yazılım", "internet")),
]

CITIES = ["İstanbul", "Ankara", "İzmir", "Bursa"]

RESOURCES = [
    ResourceInfo(
        "butce", ResourceKind.ORTAK, "Etkinlik bütçesi", "genel",
        divisible=True, division_type=ScopeSubtype.SEHIR,
        shares={"sehir:istanbul": 4000, "sehir:ankara": 3000, "sehir:izmir": 2000,
                "sehir:bursa": 1000},
        aliases=("bütçe", "etkinlik bütçe"),
    ),
    ResourceInfo("salon", ResourceKind.ORTAK, "Ortak toplantı salonu", "genel",
                 aliases=("salon", "toplantı salon")),
]

# (takma ad, ad soyad, il, doğum tarihi, ilgi alanları)
NAMED = [
    ("ayse", "Ayşe Yıldız", "İstanbul", date(1995, 3, 14), ("sinema", "felsefe")),
    ("aylin", "Aylin Kaya", "Ankara", date(1988, 7, 2), ("ulasim",)),
    ("baris", "Barış Demir", "İzmir", date(1979, 11, 23), ("ulasim",)),
    ("ceren", "Ceren Aksoy", "İstanbul", date(1991, 1, 9), ("ulasim", "bisiklet")),
    ("ilker", "İlker Şahin", "Bursa", date(1969, 5, 30), ("parklar",)),
    ("hale", "Hale Koç", "Ankara", date(1984, 9, 17), ("bisiklet",)),
    ("emre", "Emre Arslan", "İstanbul", date(2002, 2, 28), ("kent",)),
    ("kaba_kul", "Kadir Bal", "İzmir", date(1999, 12, 1), ()),
]

POOL_NAMES = [
    "deniz", "elif", "ferhat", "gizem", "hakan", "irem", "kaan", "leyla", "mert", "nazli",
    "okan", "pinar", "rana", "selin", "tolga", "umut", "vedat", "yasemin", "zeynep", "burak",
    "cansu", "dogan", "ece", "fatih", "gulsen", "harun", "ipek", "kerem", "melis", "nevzat",
]
POOL_SURNAMES = [
    "Aydın", "Çelik", "Öztürk", "Yılmaz", "Kılıç", "Doğan", "Aslan", "Çetin", "Kara", "Koç",
    "Kurt", "Özdemir", "Şimşek", "Polat", "Erdoğan", "Güneş", "Yıldırım", "Tekin", "Bulut", "Avcı",
]
# Öneri açan tohum hesaplarının seçmen kapsamına üyeliği (R5) rastgeleliğe bırakılmaz.
POOL_EXTRA_INTERESTS = {"leyla": ("sinema",), "nazli": ("sinema",), "selin": ("felsefe",)}
RAIDERS = ["mavi_kus", "sari_kedi", "yesil_at", "mor_balik", "turuncu_ari"]

MAHZEN_PROMPTS = [
    "Bir ağaç ormanda devrilirse ve kimse duymazsa ses çıkar mı?",
    "Tesla'nın gemisi: parçaları tek tek değişen şey hâlâ aynı mıdır?",
    "Özgür irade bir yanılsama ise ceza adil olabilir mi?",
    "Bilmediğimizi bilmek bir tür bilgi midir?",
    "Dil düşünceyi mi belirler, düşünce dili mi?",
    "Sonsuz yaşam anlamı çoğaltır mı, yok eder mi?",
    "Başkasının acısını gerçekten bilebilir miyiz?",
    "Doğruyu söylemek her zaman erdem midir?",
    "Kalabalığın bilgeliği ile kalabalığın deliliği arasındaki fark nedir?",
    "Zaman akar mı, yoksa biz mi akarız?",
    "Bir makine anlamı anlayabilir mi?",
    "Mutluluk bir amaç mı, bir yan ürün mü?",
    "Güzellik bakanın gözünde midir?",
    "Adalet eşitlik midir, hakkaniyet mi?",
    "Hatırlamadığımız şeyler bizi hâlâ biz yapar mı?",
]
MAHZEN_REPLIES = [
    "Soru yanlış sorulmuş olabilir.", "Tanımları netleştirmeden ilerleyemeyiz.",
    "Bence cevap bağlama bağlı.", "Kant burada itiraz ederdi.", "Hume'u hatırlayalım.",
    "Sezgim hayır diyor ama gerekçem yok.", "Bu bir kategori hatası.",
    "Karşı örnek: rüyalar.", "Pratikte fark etmez, teoride çok şey değişir.",
]


def _t(days: float = 0, hours: float = 0, minutes: float = 0) -> datetime:
    return SEED_NOW - timedelta(days=days, hours=hours, minutes=minutes)


@dataclass
class World:
    users: dict[str, User] = field(default_factory=dict)
    pool: list[str] = field(default_factory=list)
    ids: dict[str, int] = field(default_factory=dict)
    steps: list[tuple[datetime, int, Callable[[Ctx], None]]] = field(default_factory=list)

    def at(self, when: datetime, fn: Callable[[Ctx], None]) -> None:
        self.steps.append((when, len(self.steps), fn))

    def run(self, ctx: Ctx) -> None:
        for when, _, fn in sorted(self.steps, key=lambda s: (s[0], s[1])):
            fn(ctx.at(when))
        self.steps.clear()


# --- zaman çizelgesi yapı taşları ----------------------------------------------------------------


def _user(c: Ctx, w: World, nickname: str, full_name: str, city: str, birth: date,
          interests: tuple[str, ...] = (), last_login: datetime | None = None) -> None:
    user = auth.create_verified_user(
        c, nickname=nickname, full_name=full_name, email=f"{nickname}@mesveret.test",
        password=DEMO_PASSWORD, birth_date=birth, city=city, district="Merkez", address_line="",
    )
    for area in interests:
        ontology.join_interest(c, user, area)
    user.last_login_at = last_login or _t(days=1 + len(nickname) % 5)
    user.cellar_warned_at = c.now
    c.db.commit()
    w.users[nickname] = user


def _topic(w: World, key: str, author: str, title: str, body: str, area: str, scope: str,
           when: datetime, parent: str | None = None) -> None:
    def open_(c: Ctx) -> None:
        inp = ProposalInput(type="ALT_KONU" if parent else "KONU", title=title, body=body,
                            area_id=area, scope_id=scope,
                            parent_topic_id=w.ids[parent] if parent else None)
        w.ids[f"p:{key}"] = proposals.open_proposal(c, w.users[author], inp).id

    def accept(c: Ctx) -> None:
        p = c.db.get(Proposal, w.ids[f"p:{key}"])
        proposals.accept(c, p)
        c.commit()
        w.ids[key] = c.db.execute(
            select(Topic.id).where(Topic.accepted_proposal_id == p.id)
        ).scalar_one()

    w.at(when, open_)
    w.at(when + timedelta(hours=24), accept)


def _msg(w: World, key: str, who: str, topic_key: str, text: str, when: datetime,
         reply_to: str | None = None) -> None:
    def run(c: Ctx) -> None:
        msg = topics.post_message(c, w.users[who], w.ids[topic_key], text,
                                  w.ids[reply_to] if reply_to else None)
        w.ids[key] = msg.id

    w.at(when, run)


def _queued_by_objection(w: World, key: str, author: str, inp: ProposalInput, opened: datetime,
                         objectors: list[str]) -> None:
    def open_(c: Ctx) -> None:
        w.ids[key] = proposals.open_proposal(c, w.users[author], inp).id

    w.at(opened, open_)
    for i, nick in enumerate(objectors):
        w.at(opened + timedelta(hours=2 + i),
             lambda c, nick=nick: proposals.object_to(c, w.users[nick], w.ids[key]))

    def check(c: Ctx) -> None:
        status = c.db.get(Proposal, w.ids[key]).status
        if status != "QUEUED":
            raise RuntimeError(f"Tohum: '{key}' itirazla yavaş şeride geçmedi ({status}).")

    w.at(opened + timedelta(hours=2 + len(objectors)), check)


# --- bölümler -------------------------------------------------------------------------------------


def _people(w: World) -> None:
    for i, (nick, name, city, birth, interests) in enumerate(NAMED):
        w.at(_t(days=420 - i), lambda c, a=(nick, name, city, birth, interests):
             _user(c, w, *a))
    areas = [a[0] for a in AREAS]
    for i, nick in enumerate(POOL_NAMES):
        birth = date(1960 + (i * 7) % 45, 1 + i % 12, 1 + (i * 3) % 27)
        interests = tuple(sorted({areas[i % len(areas)], areas[(i * 5 + 3) % len(areas)],
                                  *POOL_EXTRA_INTERESTS.get(nick, ())}))
        name = f"{nick.title()} {POOL_SURNAMES[i % len(POOL_SURNAMES)]}"
        w.at(_t(days=400 - i * 3), lambda c, a=(nick, name, CITIES[i % len(CITIES)], birth,
                                                interests): _user(c, w, *a))
        w.pool.append(nick)


def _delegations(w: World) -> None:
    def run(c: Ctx) -> None:
        u = w.users
        delegation.set_delegation(c, u["aylin"], "baris", None)
        delegation.set_delegation(c, u["baris"], "ceren", "ulasim")
        for nick in ("gizem", "hakan"):
            delegation.set_delegation(c, u[nick], oracle.ORACLE_NICKNAME, "kultur")
        for nick in ("deniz", "elif", "ferhat", "irem", "kaan"):
            delegation.set_delegation(c, u[nick], "selin", "felsefe")
        c.commit()

    w.at(_t(days=30), run)


def _background(w: World) -> None:
    _topic(w, "felsefe", "selin", "Felsefe okuma grubu",
           "Her hafta bir diyalog okuyup tartışalım; ilk metin Menon.", "felsefe", "genel",
           _t(days=27))
    _topic(w, "film", "leyla", "Film günleri",
           "Her ayın ilk cuması bir film izleyip ardından konuşalım.", "sinema", "ilgi:sinema",
           _t(days=26))
    _topic(w, "siir", "okan", "Şiir akşamları",
           "Ayda bir kez herkes sevdiği bir şiiri okusun.", "siir", "genel", _t(days=25))
    _msg(w, "m_felsefe", "tolga", "felsefe", "Menon'daki köle çocuk sahnesi hâlâ tartışmalı.",
         _t(days=25, hours=2))
    _msg(w, "m_film1", "leyla", "film", "İlk film için Tarkovski'nin Solaris'ini öneriyorum.",
         _t(days=24))
    _msg(w, "m_film2", "mert", "film", "Solaris uzun; ilk buluşma için daha kısa bir film seçelim.",
         _t(days=24, hours=-2), reply_to="m_film1")
    _msg(w, "m_siir", "pinar", "siir", "Ben Nâzım'dan başlarım.", _t(days=23))
    _msg(w, "m_film3", "ayse", "film", "Salon için perşembe akşamı uygun.", _t(days=22))
    w.at(_t(days=21), lambda c: topics.edit_own_message(
        c, w.users["ayse"], w.ids["m_film3"], "Salon için cuma akşamı uygun; perşembe dolu."))
    _topic(w, "belgesel-ayi", "nazli", "Belgesel ayı",
           "Kasım ayını belgesellere ayıralım; her hafta bir belgesel.", "belgesel",
           "ilgi:sinema", _t(days=20), parent="film")
    _topic(w, "pazar", "emre", "İstanbul semt pazarları",
           "Semt pazarlarının saatleri mahalleye göre ayarlansın.", "kent", "sehir:istanbul",
           _t(days=19))
    _msg(w, "m_pazar", "ceren", "pazar", "Kadıköy pazarı akşam da açık olabilir.", _t(days=17))


def _scenario_deletion(w: World) -> None:
    """4. Silme."""
    _topic(w, "bisiklet", "hale", "Bisiklet yolları",
           "Ana caddelere korunaklı bisiklet yolu yapılsın.", "bisiklet", "genel", _t(days=16))
    _msg(w, "m_bis1", "ceren", "bisiklet", "Önce okul çevrelerinden başlayalım.", _t(days=14))
    _msg(w, "troll", "kaba_kul", "bisiklet",
         "Bu konuyu açanların hepsi cahil; bisikletliler trafiğin baş belası.", _t(days=13))
    _msg(w, "m_bis2", "hale", "bisiklet", "Eleştiri olur, hakaret olmaz.",
         _t(days=13, hours=-1))
    w.at(_t(days=3), lambda c: w.ids.__setitem__("silme", proposals.open_proposal(
        c, w.users["hale"], ProposalInput(
            type="SILME", target_message_id=w.ids["troll"],
            body="Mesaj tartışmaya katkı sunmuyor, katılımcılara hakaret ediyor.",
        )).id))


def _scenario_closure(w: World) -> None:
    """5. Kapanış."""
    _topic(w, "parklar", "zeynep", "Parkların kapanış saati",
           "Mahalle parkları gece kaçta kapanmalı?", "parklar", "genel", _t(days=12))
    _msg(w, "m_park1", "burak", "parklar", "22:00 hem güvenli hem yeterli.", _t(days=10))
    _msg(w, "m_park2", "ilker", "parklar", "Yazın gece yarısına kadar açık kalmalı.",
         _t(days=10, hours=-3))
    opened = _t(days=4)
    w.at(opened, lambda c: w.ids.__setitem__("kapanis", proposals.open_proposal(
        c, w.users["zeynep"], ProposalInput(
            type="KAPANIS", target_topic_id=w.ids["parklar"],
            body="Parklar her gün 20:00'de kapansın.",
        )).id))
    w.at(opened + timedelta(hours=4), lambda c: proposals.add_rival(
        c, w.users["burak"], w.ids["kapanis"], "Parklar her gün 22:00'de kapansın."))
    w.at(opened + timedelta(hours=12), lambda c: proposals.add_rival(
        c, w.users["ilker"], w.ids["kapanis"], "Parklar yazın 24:00'te, kışın 22:00'de kapansın."))

    def end(c: Ctx) -> None:
        proposals.end_rival_period(c, c.db.get(Proposal, w.ids["kapanis"]))
        c.commit()

    w.at(opened + timedelta(hours=48), end)


def _scenarios_voting(w: World) -> None:
    """2. Havale zinciri, 3. Yönetmelik, 7. Baskın, 8. Hâtif için Karar Saati kuyruğu."""
    _queued_by_objection(w, "metro", "umut", ProposalInput(
        type="KONU", title="Gece metro seferleri",
        body="Metro hafta sonları gece de çalışsın; sefer aralıkları 20 dakika olsun.",
        area_id="ulasim", scope_id="genel",
    ), _t(days=3, hours=6), ["vedat", "yasemin", "cansu"])
    w.at(_t(days=2, hours=20), lambda c: w.ids.__setitem__("yonetmelik_60", proposals.open_proposal(
        c, w.users["dogan"], ProposalInput(
            type="YONETMELIK", article_key="red_bekleme", new_value={"gun": 45},
            body="Reddedilen önerilerin hemen geri gelmesini önlemek için süre uzasın.",
        )).id))
    w.at(_t(days=2, hours=18), lambda c: w.ids.__setitem__("yonetmelik_67", proposals.open_proposal(
        c, w.users["ece"], ProposalInput(
            type="YONETMELIK", article_key="sessiz_onay_suresi", new_value={"saat": 36},
            body="Hafta sonu açılan önerileri kaçırmamak için sessiz onay 36 saat olsun.",
        )).id))
    _queued_by_objection(w, "baskin", "emre", ProposalInput(
        type="KONU", title="Etkinlik bütçesinin tamamı tek bir şehre",
        body="Bütçeyi bölmeyelim; tüm etkinlikler tek şehirde yapılsın.",
        area_id="kent", scope_id="genel", resource_ids=["butce"],
    ), _t(days=2, hours=10), ["fatih", "gulsen", "harun"])
    _queued_by_objection(w, "hatif", "ipek", ProposalInput(
        type="KONU", title="Belgesel film gösterimleri",
        body="Her ay bir belgesel izleyip ardından belgesel üzerine konuşalım.",
        area_id="edebiyat", scope_id="genel",
    ), _t(days=2, hours=4), ["kerem", "melis", "nevzat"])


def _cellar(w: World) -> None:
    """6. Mahzen: 90 dolgu başlık (çürüme görünsün) ve ifşa oylaması açık demo başlığı."""
    for i in range(90):
        when = _t(days=6, hours=-i * 1.5)
        author = w.pool[(i * 7) % len(w.pool)]
        prompt = MAHZEN_PROMPTS[i % len(MAHZEN_PROMPTS)]
        replies = [(w.pool[(i * 5 + j * 11 + 3) % len(w.pool)],
                    MAHZEN_REPLIES[(i + j) % len(MAHZEN_REPLIES)]) for j in range(i % 3)]

        def make(c: Ctx, author=author, prompt=prompt, i=i, replies=replies) -> None:
            t = cellar.create_thread(c, w.users[author], prompt[:110], f"{prompt} ({i + 1}. düşünce)",
                                     acknowledge=True)
            for j, (nick, text) in enumerate(replies):
                cellar.reply(c.at(c.now + timedelta(minutes=40 + j * 50)), w.users[nick], t.id,
                             text, acknowledge=True)

        w.at(when, make)

    at = _t(hours=8)

    def demo(c: Ctx) -> None:
        u = w.users
        t = cellar.create_thread(
            c, u["ayse"], "Çoğunluk haklı olabilir mi?",
            "Bir şeyin doğru olması için çoğunluğun onu kabul etmesi yeterli mi? "
            "Oylamayla doğruya ulaşılır mı, yoksa yalnızca karara mı?", acknowledge=True)
        replies = [
            ("pinar", "Oylama doğruyu değil, birlikte yaşama biçimini belirler."),
            ("rana", "Ama bilimsel doğrular oylanmaz; kapsam önemli."),
            ("selin", "Condorcet: bireyler yarıdan fazla doğruysa çoğunluk daha da doğrudur."),
            ("tolga", "Bu varsayım bağımsızlık ister; forumlarda herkes birbirini etkiler."),
        ]
        for i, (nick, text) in enumerate(replies):
            cellar.reply(c.at(c.now + timedelta(minutes=30 * (i + 1))), u[nick], t.id, text,
                         acknowledge=True)
        w.ids["mahzen"] = t.id

    w.at(at, demo)
    w.at(_t(hours=5), lambda c: cellar.open_reveal_vote(c, w.users["ayse"], w.ids["mahzen"]))
    for nick, yes in (("pinar", True), ("rana", True), ("selin", False)):
        w.at(_t(hours=4, minutes=30), lambda c, nick=nick, yes=yes: cellar.cast_reveal_vote(
            c, w.users[nick], w.ids["mahzen"], yes))


def _raiders(w: World) -> None:
    """7. Baskın: art arda açılmış, birbirine yanıt veren beş hesap."""
    for i, nick in enumerate(RAIDERS):
        w.at(_t(hours=5, minutes=-8 * i), lambda c, nick=nick, i=i: _user(
            c, w, nick, nick.replace("_", " ").title(), "İstanbul", date(2000, 1 + i, 10),
            last_login=_t(hours=4)))
    _msg(w, "raid0", RAIDERS[0], "parklar", "Tek şehir, tek bütçe!", _t(hours=4))
    for i, nick in enumerate(RAIDERS[1:], start=1):
        _msg(w, f"raid{i}", nick, "parklar", "Kesinlikle katılıyorum!",
             _t(hours=4, minutes=-5 * i), reply_to="raid0")


def _scenario_istanbul(w: World) -> None:
    """1. İstanbul vakası: seçmen İstanbul, kaynak bölünebilir bütçe → İstanbul payına daralır."""
    w.at(_t(hours=3), lambda c: w.ids.__setitem__("istanbul", proposals.open_proposal(
        c, w.users["emre"], ProposalInput(
            type="KONU", title="Etkinlik bütçesinin tamamı İstanbul'a",
            body="İstanbul'daki etkinlikler için tüm bütçe kullanılsın.",
            area_id="kent", scope_id="sehir:istanbul", resource_ids=["butce"],
        )).id))


def _vote_plan(ctx: Ctx, w: World) -> None:
    names = w.pool
    plan: list[tuple[str, str, object]] = []

    # 2. Havale zinciri: 4 EVET + Hâtif = 5, 5 HAYIR → eşitlik; ceren (ağırlık 3) sonucu belirler.
    plan += [("metro", n, "EVET") for n in names[20:24]]
    plan += [("metro", n, "HAYIR") for n in names[24:29]]

    # 3. Yönetmelik: 29 yurttaş + Hâtif (EVET) = 30 oy.
    #    red_bekleme: 17 + 1 = 18/30 = %60 → geçemez; sessiz_onay_suresi: 19 + 1 = 20/30 → geçer.
    for i, n in enumerate(names[:29]):
        plan.append(("yonetmelik_60", n, "EVET" if i < 17 else "HAYIR"))
        plan.append(("yonetmelik_67", n, "EVET" if i < 19 else "HAYIR"))

    # 4. Silme: açık çoğunluk.
    plan += [("silme", n, "EVET" if i < 9 else "HAYIR") for i, n in enumerate(names[:12])]

    # 5. Kapanış (onay oylaması): 22:00 metni kazanır; ilker kendi metnini onaylar.
    texts = proposals.closure_texts(ctx, ctx.db.get(Proposal, w.ids["kapanis"]))
    t20, t22, t24 = (ct.id for ct in texts)
    approvals: dict[str, list[int]] = {"zeynep": [t20, t22], "burak": [t22], "ilker": [t24]}
    approvals |= {n: [t22] for n in names[0:5]}
    approvals |= {n: [t20] for n in names[5:8]}
    approvals |= {n: [t22, t24] for n in names[8:11]}
    approvals |= {n: [t24] for n in names[11:13]}
    plan += [("kapanis", n, choice) for n, choice in approvals.items()]

    # 7. Baskın: beş yeni hesap EVET (dışlanacaklar); yurttaşlardan 1 EVET, 4 HAYIR.
    plan += [("baskin", n, "EVET") for n in RAIDERS]
    plan += [("baskin", n, "EVET" if i == 0 else "HAYIR") for i, n in enumerate(names[13:18])]

    # 8. Hâtif: yanlış alan etiketi; Hâtif (+2 havale) HAYIR. Yurttaşlar 4 EVET, 3 HAYIR.
    plan += [("hatif", n, "EVET" if i < 4 else "HAYIR") for i, n in enumerate(names[18:25])]

    for key, nick, choice in plan:
        ctx.db.add(DevVotePlan(proposal_id=w.ids[key], voter_id=w.users[nick].id, choice=choice))
    ctx.db.commit()


# --- giriş noktası --------------------------------------------------------------------------------


def _reset(ctx: Ctx) -> Iterator[str]:
    from mesveret.db.base import create_schema, drop_schema

    ctx.db.close()
    drop_schema()
    create_schema()
    ctx.graph.reset()
    if hasattr(ctx.graph, "ensure_constraints"):
        ctx.graph.ensure_constraints()
    yield "PostgreSQL ve Neo4j sıfırlandı."
    try:
        ctx.ledger.reset()
        yield "Defter sıfırlandı (üç düğüm)."
    except Exception as exc:  # noqa: BLE001
        yield f"UYARI: defter sıfırlanamadı ({type(exc).__name__}); eski kayıtlar kalabilir."


def run(ctx: Ctx, *, reset: bool = False) -> Iterator[str]:
    if reset:
        yield from _reset(ctx)
        from mesveret.db.base import get_sessionmaker

        ctx.db = get_sessionmaker()()
    elif ctx.db.execute(select(User.id).limit(1)).first():
        yield "Veritabanı boş değil; yeniden kurmak için: meşveret-dev seed --reset"
        return
    clock.reset_to(ctx.db, SEED_NOW)
    ctx.db.commit()
    ctx = ctx.at(SEED_NOW)
    base = ctx.at(_t(days=3650))
    ontology.install_base(base, AREAS, RESOURCES, cities=CITIES)
    oracle.ensure_oracle(base)
    ctx.db.merge(SchedulerState(id=1, last_tick_at=SEED_NOW))
    ctx.db.commit()

    w = World()
    _people(w)
    _delegations(w)
    _background(w)
    _scenario_deletion(w)
    _scenario_closure(w)
    _scenarios_voting(w)
    _cellar(w)
    _raiders(w)
    _scenario_istanbul(w)
    w.run(ctx)
    w.users["ayse"].cellar_warned_at = None  # sunumda Mahzen giriş uyarısı görünsün
    _vote_plan(ctx, w)
    ctx.commit()

    yield f"Sahte saat: {SEED_NOW.astimezone(clock.ISTANBUL):%d.%m.%Y %H:%M} (İstanbul)."
    yield (f"{len(w.users) + 1} hesap (Hâtif dahil). "
           f"Tüm tohum hesaplarının şifresi: {DEMO_PASSWORD}")
    yield "Senaryo önerileri: " + ", ".join(
        f"{k}=#{w.ids[k]}" for k in ("istanbul", "metro", "yonetmelik_60", "yonetmelik_67",
                                     "silme", "kapanis", "baskin", "hatif"))
    yield f"Mahzen demo başlığı: #{w.ids['mahzen']}"
    yield "Sonraki adım: README'deki senaryolar (meşveret-dev run-karar-saati)."


def scenario_ids(ctx: Ctx) -> dict[str, int]:
    """Testler ve CLI için: senaryo önerilerinin numaraları (başlıklarından)."""
    titles = {
        "istanbul": "Etkinlik bütçesinin tamamı İstanbul'a",
        "metro": "Gece metro seferleri",
        "yonetmelik_60": "Yönetmelik: red_bekleme",
        "yonetmelik_67": "Yönetmelik: sessiz_onay_suresi",
        "kapanis": "Kapanış: Parkların kapanış saati",
        "baskin": "Etkinlik bütçesinin tamamı tek bir şehre",
        "hatif": "Belgesel film gösterimleri",
    }
    out = {}
    for key, title in titles.items():
        pid = ctx.db.execute(select(Proposal.id).where(Proposal.title == title)).scalar()
        if pid is not None:
            out[key] = pid
    silme = ctx.db.execute(select(Proposal.id).where(Proposal.type == "SILME")).scalar()
    if silme is not None:
        out["silme"] = silme
    return out
