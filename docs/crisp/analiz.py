"""Baskın tespitinin CRISP-DM analizi için ölçüm betiği (yalnızca okur, yığını değiştirmez).

    docker compose exec -T api python - < docs/crisp/analiz.py > docs/crisp/sonuclar.json

1. Karar Saati #1'in açılış anındaki Genel seçmenlerini, katılım anlarını ve ETKILESIM
   ağırlıklarını okur (veri anlayışı).
2. Tespiti oturumun yönetmelik anlık görüntüsüyle çalıştırır ve tohumdaki gerçek baskıncılarla
   (seed.RAIDERS) karşılaştırır (değerlendirme).
3. Beş eşiği tarar: her birleşimde doğru/yanlış işaret sayıları.
4. Gerçek veride olmayan durumlar için yapay senaryolar kurar (sınıf, sabırlı baskın, sessiz
   baskın, büyük topluluk).
"""

import itertools
import json
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from mesveret.cli import _ctx
from mesveret.db.models import DecisionSession, User
from mesveret.domain.raid import detect_raids
from mesveret.domain.regulation import Regulation
from mesveret.services import ontology
from mesveret.services.seed import RAIDERS


def with_params(base: dict, *, kume=None, yogunluk=None, agirlik=None, gun=None, saat=None):
    v = {k: dict(x) for k, x in base.items()}
    if kume is not None:
        v["baskin_min_kume"] = {"deger": kume}
    if yogunluk is not None:
        v["baskin_yogunluk_esigi"] = {"karsilastirma": ">=", "oran": yogunluk}
    if agirlik is not None:
        v["baskin_min_agirlik"] = {"deger": agirlik}
    if gun is not None:
        v["baskin_yeni_uye_suresi"] = {"gun": gun}
    if saat is not None:
        v["baskin_katilim_araligi"] = {"saat": saat}
    return Regulation(v)


def flagged(joined, inter, at, reg):
    return {u for c in detect_raids(joined, inter, at, reg) for u in c.members}


def score(found, truth, population):
    tp = len(found & truth)
    return {"dogru_isaret": tp, "yanlis_isaret": len(found - truth),
            "kacan": len(truth - found), "dogru_temiz": len(population - found - truth)}


out = {}
with _ctx() as ctx:
    session = ctx.db.execute(select(DecisionSession).order_by(DecisionSession.id)).scalars().first()
    at = session.opened_at
    c = ctx.at(at)
    members = ontology.eligible_voters(c, "genel")
    nick = {u.id: u.nickname for u in ctx.db.execute(select(User)).scalars()}
    joined = {uid: m.since for uid, m in members.items()}
    inter = ctx.graph.interactions_among(members)
    reg = Regulation(session.regulation)
    truth = {uid for uid in members if nick.get(uid) in RAIDERS}
    population = set(members)

    # --- veri anlayışı ---
    window = reg.duration("baskin_yeni_uye_suresi")
    candidates = {u for u, t in joined.items() if at - window <= t <= at}
    und = Counter()
    for (a, b), w in inter.items():
        if a != b:
            und[frozenset((a, b))] += w
    cand_edges = {p: w for p, w in und.items() if p <= candidates}
    age_days = sorted(round((at - t).total_seconds() / 86400, 1) for t in joined.values())
    out["veri"] = {
        "an": at.isoformat(),
        "secmen": len(members),
        "yonlu_kenar": len(inter),
        "yonsuz_cift": len(und),
        "agirlik_dagilimi": dict(sorted(Counter(round(w, 1) for w in und.values()).items())),
        "aday_7_gun": len(candidates),
        "adaylar": sorted([{"takma_ad": nick.get(u), "katilim_saat_once":
                            round((at - joined[u]).total_seconds() / 3600, 1),
                            "baskinci": u in truth} for u in candidates],
                          key=lambda r: r["katilim_saat_once"]),
        "aday_kenar": len(cand_edges),
        "aday_kenar_agirliklari": sorted(round(w, 1) for w in cand_edges.values()),
        "uyelik_yasi_gun": {"en_kucuk": age_days[0], "medyan": age_days[len(age_days) // 2],
                            "en_buyuk": age_days[-1]},
        "gercek_baskinci": sorted(nick[u] for u in truth),
    }

    # --- temel sonuç ---
    clusters = detect_raids(joined, inter, at, reg)
    found = {u for cl in clusters for u in cl.members}
    out["temel"] = {
        "esikler": {k: reg.raw(k) for k in ("baskin_yeni_uye_suresi", "baskin_katilim_araligi",
                                             "baskin_min_kume", "baskin_yogunluk_esigi",
                                             "baskin_min_agirlik")},
        "kumeler": [{"uyeler": sorted(nick[u] for u in cl.members),
                     "yogunluk": str(cl.density), "yayilim_dk": round(cl.span.total_seconds() / 60),
                     "gerekce": cl.reason} for cl in clusters],
        "skor": score(found, truth, population),
    }

    # --- eşik taraması ---
    grid = []
    for kume, yog, agr, gun, saat in itertools.product(
            [3, 4, 5, 6], ["1/3", "1/2", "2/3", "1"], [0.5, 1, 2, 3], [1, 7, 30], [1, 24, 168]):
        r = with_params(session.regulation, kume=kume, yogunluk=yog, agirlik=agr, gun=gun, saat=saat)
        s = score(flagged(joined, inter, at, r), truth, population)
        grid.append({"kume": kume, "yogunluk": yog, "agirlik": agr, "gun": gun, "saat": saat, **s})
    perfect = [g for g in grid if g["kacan"] == 0 and g["yanlis_isaret"] == 0]
    out["tarama"] = {
        "birlesim": len(grid),
        "kusursuz": len(perfect),
        "kacan_var": sum(1 for g in grid if g["kacan"]),
        "yanlis_isaret_var": sum(1 for g in grid if g["yanlis_isaret"]),
        "kacanlarin_kume_esigi": dict(Counter(g["kume"] for g in grid if g["kacan"])),
        "kacanlarin_agirlik_esigi": dict(Counter(g["agirlik"] for g in grid if g["kacan"])),
        "en_cok_yanlis_isaret": max(g["yanlis_isaret"] for g in grid),
        "tek_degisken": {
            "kume": {k: score(flagged(joined, inter, at, with_params(session.regulation, kume=k)),
                              truth, population) for k in (3, 4, 5, 6)},
            "agirlik": {str(a): score(flagged(joined, inter, at,
                                              with_params(session.regulation, agirlik=a)),
                                      truth, population) for a in (0.5, 1, 2, 3)},
        },
    }

# --- yapay senaryolar (varsayılan eşikler) ---
reg = Regulation.defaults()
T = datetime(2026, 10, 4, 17, 0, tzinfo=UTC)  # Pazar 20:00 İstanbul


def scenario(name, joined, edges, truth):
    inter = {}
    for a, b, w in edges:
        inter[(a, b)] = inter.get((a, b), 0) + w
        inter[(b, a)] = inter.get((b, a), 0) + w
    found = flagged(joined, inter, T, reg)
    return {"senaryo": name, "isaretlenen": sorted(found),
            "skor": score(found, truth, set(joined))}


old = {f"eski{i}": T - timedelta(days=200 + i) for i in range(30)}
old_edges = [(f"eski{i}", f"eski{(i + 1) % 30}", 1) for i in range(30)]
sc = []
# A. Gerçek bir sınıf: 6 öğrenci aynı öğleden sonra kaydolur, birbirine yanıt verir.
cls = {f"ogr{i}": T - timedelta(days=2, minutes=20 * i) for i in range(6)}
cls_edges = [(a, b, 1) for a, b in itertools.combinations(cls, 2)]
sc.append(scenario("Sınıf (gerçek kullanıcılar, aynı gün)", {**old, **cls}, old_edges + cls_edges,
                   set()))
# B. Sabırlı baskın: 5 hesap iki günde bir açılır, birbirine yanıt verir.
pat = {f"sab{i}": T - timedelta(days=2 * i + 1) for i in range(5)}
pat_edges = [(a, b, 1) for a, b in itertools.combinations(pat, 2)]
sc.append(scenario("Sabırlı baskın (10 güne yayılmış)", {**old, **pat}, old_edges + pat_edges,
                   set(pat)))
# C. Sessiz baskın: 5 hesap 2 saat arayla açılır, hiç etkileşmez, yalnızca oy verir.
quiet = {f"ses{i}": T - timedelta(hours=10 + 2 * i) for i in range(5)}
sc.append(scenario("Sessiz baskın (etkileşimsiz)", {**old, **quiet}, old_edges, set(quiet)))
# D. Tohumdaki biçim: 5 hesap 8 dakika arayla açılır, ilk mesaja yanıt verir.
raid = {f"bas{i}": T - timedelta(hours=5, minutes=-8 * i) for i in range(5)}
raid_edges = [(a, b, 2) for a, b in itertools.combinations(raid, 2)]  # yakın kayıt (iki yön)
raid_edges += [(f"bas{i}", "bas0", 1) for i in range(1, 5)]
sc.append(scenario("Tohumdaki biçim (art arda kayıt + yanıt)", {**old, **raid},
                   old_edges + raid_edges, set(raid)))
# E. Dağınık baskın: 4 hesap, ikişerli iki kümeye bölünür.
split = {f"dag{i}": T - timedelta(hours=6, minutes=10 * i) for i in range(4)}
split_edges = [("dag0", "dag1", 2), ("dag2", "dag3", 2)]
sc.append(scenario("Bölünmüş baskın (2+2)", {**old, **split}, old_edges + split_edges, set(split)))
out["senaryolar"] = sc

print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
