"""Raporu bölüm parçalarından ve ölçüm dosyalarından üretir.

    python3 docs/rapor/olustur.py        # docs/rapor/rapor.html yazılır
    node docs/rapor/pdf.mjs              # A4 PDF (ayrıntı dosyanın başında)
    python3 docs/rapor/olustur.py --a5   # rapor-a5.html: iki sayfa bir yaprağa basılacak A5 sürümü
    node docs/rapor/pdf.mjs a5

A5 sürümünde yazılar A5'te gerçek boyutunda okunur; grafikler dar genişliğe göre yeniden çizilir,
ekran görüntüleri ``CROPS_A5``'teki bölgelere kırpılır. Açıklamadaki ``<span class="a4">`` ve
``<span class="a5">`` parçaları yalnızca kendi sürümünde kalır ("solda" / "üstte" gibi).

Diyagramlar ``diyagramlar.py``'den gelir (``uml.py`` çizer; yazı genişliği Pillow ile raporun
yazı tiplerinden ölçülür). Sınıflar, tablolar ve paket bağımlılıkları ``sema.json``'dadır; kod
değişince ``uv run --directory api python ../docs/rapor/sema.py`` ile yeniden üretilir. Gantt
şeması ``git log``'dan çizilir.

Sayılar elle yazılmaz: baskın tespitinin sonuçları ``docs/degerlendirme/sonuclar.json``'dan,
gecikme ``docs/degerlendirme/gecikme.json``'dan, test sayıları ``testler.json``'dan okunur.
Parçalardaki yer tutucular:

- ``{{t:ad}}``  tablo, ``{{svg:ad}}`` grafik, ``{{v:yol}}`` tek değer (ör. ``{{v:canli.secmen}}``),
- ``{{ref:bolum}}`` bölüm numarası (``<section id="bolum">``),
- ``<b>Şekil #.</b>`` ve ``{{fig:ad}}``: şekiller sırayla numaralanır (``data-fig="ad"``),
- ``<figure class="uml" data-fig="ad">{{uml:islev}}…</figure>``: ``diyagramlar.py``'deki diyagram.
  A4'te sütuna, A5'te yazı okunur kalsın diye sütuna ya da tam sayfaya (gerekirse yan çevrilmiş)
  yerleşir.
"""

from __future__ import annotations

import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EVAL = ROOT.parent / "degerlendirme"
PARTS = [
    ("I", "Problem ve analiz", ["ozet", "cerceve", "paydas", "kullanim", "modeller", "yz", "metrik",
                                "crisp", "baskin"]),
    ("II", "Tasarım ve kod", ["desen", "sistem", "teknik", "diyagram", "sinif", "etkilesim", "davranis",
                              "mimari", "veri"]),
    ("III", "Politikalar", ["azinlik", "kapsam", "sinirlama", "akis", "yonetmelik", "havale",
                            "silme", "mahzen", "sonuc", "gorsel", "butunluk", "kolaylik"]),
    ("IV", "Süreç", ["gelisim", "sorunlar", "aciklar", "test", "denetim", "beyan", "kaynak"]),
]
# Parçalar sırayla birleşir; ``{{include:ad.html}}`` bir parçanın içine başka bir parça koyar
# (kullanım durumları paydaşlardan sonra, CRISP-DM analizi baskın ölçümünden önce, geliştirme
# takvimi sorunlardan önce, tasarım denetimi testlerden sonra).
FRAGMENTS = ["analiz.html", "desenler.html", "sistem.html", "teknik.html", "uml.html", "politikalar.html",
             "kolaylik.html", "surec.html"]
NAMES = {"rastgele": "Rastgele", "hic_kimse": "Hiç kimse", "yeni_uye": "Yeni üye kuralı",
         "kume": "Küme kuralı (üretim)", "karar_agaci": "Karar ağacı (öğrenilen)"}
GROUPS = {"baskin_hizli": "hızlı baskın", "baskin_kamufle": "kamufle baskın",
          "baskin_bolunmus": "bölünmüş baskın", "baskin_sabirli": "sabırlı baskın",
          "baskin_sessiz": "sessiz baskın", "sinif": "gerçek grup (sınıf)",
          "duyuru": "duyuru dalgası", "tekil": "tek tük yeni üye"}

INK, SOFT, HAIR, SEAL, OK = "#1B1A17", "#4A463E", "#CFC6B3", "#7A1E2B", "#2F4A2A"
# Grafiklerin çizim genişliği (birim): A4'te 760, A5'te dar sütuna göre 560 (yazılar küçülmesin).
W = 760


def tr(x: float, d: int = 2) -> str:
    """Türkçe ondalık: 0,32."""
    return f"{x:.{d}f}".replace(".", ",")


def thousands(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def pct(x: float, d: int = 1) -> str:
    return "%" + tr(100 * x, d)


# --- veriler ----------------------------------------------------------------------------------------

ev = json.loads((EVAL / "sonuclar.json").read_text(encoding="utf-8"))
crisp = json.loads((ROOT.parent / "crisp" / "sonuclar.json").read_text(encoding="utf-8"))
API = ROOT.parent.parent / "api" / "src" / "mesveret"
lat = json.loads((EVAL / "gecikme.json").read_text(encoding="utf-8"))
tests = json.loads((ROOT / "testler.json").read_text(encoding="utf-8"))
res = {r["tespitci"]: r for r in ev["sonuclar"] if r["kume"] == "sinama"}
new = {r["tespitci"]: r for r in ev["sonuclar"] if r["kume"] == "yeni"}
extra = ev["ek"]
live = extra["canli"]


# --- koddan çıkarılanlar: uç noktalar ve tablolar -----------------------------------------------------


def _routes() -> dict[str, list[str]]:
    """Yönlendirici dosyası → "YÖNTEM /yol" listesi (APIRouter önekiyle)."""
    out: dict[str, list[str]] = {}
    for f in sorted((API / "routers").glob("*.py")):
        src = f.read_text(encoding="utf-8")
        m = re.search(r"APIRouter\(([^)]*)\)", src)
        pm = re.search(r'prefix="([^"]+)"', m.group(1)) if m else None
        pre = pm.group(1) if pm else ""
        eps = [f"{meth.upper()} {pre}{path}"
               for meth, path in re.findall(r'@router\.(get|post|put|delete|patch)\("([^"]*)"', src)]
        if eps:
            out[f.stem] = eps
    return out


ROUTES = _routes()
DB_TABLES = re.findall(r'__tablename__ = "([^"]+)"', (API / "db" / "models.py").read_text(encoding="utf-8"))

_scen = crisp["senaryolar"]
_cluster = crisp["temel"]["kumeler"][0]
crispx = {
    "baskinci": len(crisp["veri"]["gercek_baskinci"]),
    "senaryo": len(_scen),
    "zayif": sum(1 for x in _scen if x["skor"]["yanlis_isaret"] or x["skor"]["kacan"]),
    "gerekce": _cluster["gerekce"],
    "kume_boyu": len(_cluster["uyeler"]),
    "kume_yogunluk": _cluster["yogunluk"],
    "aday_cift": crisp["veri"]["aday_kenar"],
    "yayilim_dk": _cluster["yayilim_dk"],
}
teknik = {"tablo_sayisi": len(DB_TABLES), "uc_nokta": sum(len(v) for v in ROUTES.values())}


def _roots() -> dict[str, object]:
    return {"canli": live, "veri": extra["veri"], "test": tests, "sonuc": res, "yeni": new,
            "sinif": extra["sinif_payi"], "bicim": extra["bicime_gore"], "gecikme": lat["olcumler"],
            "crisp": crisp, "crispx": crispx, "teknik": teknik}


def raw(path: str) -> object:
    cur: object = _roots()
    for part in path.split("."):
        cur = cur[int(part)] if part.isdigit() else cur[part]  # type: ignore[index]
    return cur


def value(path: str) -> str:
    cur = raw(path)
    if isinstance(cur, int):
        return thousands(cur)
    if isinstance(cur, float):
        return tr(cur)
    return str(cur)


# --- tablolar ---------------------------------------------------------------------------------------


def t_merdiven() -> str:
    rows = []
    for key in ("rastgele", "hic_kimse", "yeni_uye", "kume", "karar_agaci"):
        r, n = res[key], new[key]
        best = " class=\"best\"" if key == min(res, key=lambda k: res[k]["maliyet"]) else ""
        rows.append(
            f"<tr{best}><td>{NAMES[key]}</td><td class=\"n\">{r['dp']}</td><td class=\"n\">{r['yn']}</td>"
            f"<td class=\"n\">{thousands(r['yp'])}</td><td class=\"n\">{pct(r['dogruluk'])}</td>"
            f"<td class=\"n\">{pct(n['dogruluk'])}</td><td class=\"n\">{tr(r['kesinlik'])}</td>"
            f"<td class=\"n\">{tr(r['duyarlilik'])}</td><td class=\"n\">{tr(r['f1'])}</td>"
            f"<td class=\"n\">{tr(r['f2'])}</td><td class=\"n\"><b>{thousands(int(r['maliyet']))}</b></td></tr>")
    return ("<table class=\"num\"><thead><tr><th>Tespitçi</th><th>DP</th><th>YN</th><th>YP</th>"
            "<th>Doğruluk</th><th>Doğruluk<br>(yeni üyeler)</th><th>Kesinlik</th><th>Duyarlılık</th>"
            "<th>F1</th><th>F2</th><th>Maliyet</th></tr></thead><tbody>" + "".join(rows)
            + "</tbody></table>")


def t_karisiklik() -> str:
    r = res["kume"]
    return (f"<table class=\"cm\"><thead><tr><th></th><th>İşaretlendi</th><th>İşaretlenmedi</th>"
            f"</tr></thead><tbody><tr><th>Baskıncı ({r['dp'] + r['yn']})</th><td><b>DP {r['dp']}</b></td>"
            f"<td>YN {r['yn']}</td></tr><tr><th>Gerçek üye ({thousands(r['yp'] + r['dn'])})</th>"
            f"<td>YP {r['yp']}</td><td>DN {thousands(r['dn'])}</td></tr></tbody></table>")


def t_bicim() -> str:
    by = extra["bicime_gore"]
    raid = [k for k in by if k.startswith("baskin_")]
    real = [k for k in by if not k.startswith("baskin_")]
    raid.sort(key=lambda k: -by[k]["oran"])
    real.sort(key=lambda k: -by[k]["oran"])

    def rows(keys: list[str], good_high: bool) -> str:
        out = []
        for k in keys:
            v = by[k]
            bar = int(round(v["oran"] * 100))
            color = OK if good_high else SEAL
            out.append(f"<tr><td>{GROUPS[k]}</td><td class=\"n\">{v['isaretlenen']}/{v['hesap']}</td>"
                       f"<td class=\"n\">{pct(v['oran'], 0)}</td><td><div class=\"bar\">"
                       f"<span style=\"width:{bar}%;background:{color}\"></span></div></td></tr>")
        return "".join(out)

    return ("<table class=\"num\"><thead><tr><th style=\"width:30%\">Grup</th><th>İşaretlenen</th>"
            "<th>Oran</th><th style=\"width:40%\"></th></tr></thead><tbody>"
            "<tr><td colspan=\"4\" class=\"sub\">Baskıncılar (yakalanması istenen)</td></tr>"
            + rows(raid, True)
            + "<tr><td colspan=\"4\" class=\"sub\">Gerçek yeni üyeler (işaretlenmemesi istenen)</td></tr>"
            + rows(real, False) + "</tbody></table>")


def t_esik() -> str:
    sweep = {(r["kume"], r["yogunluk"]): r for r in extra["esik_taramasi"]}
    ys = ["1/3", "1/2", "2/3", "1"]
    head = "".join(f"<th>yoğunluk ≥ {y}</th>" for y in ys)
    rows = []
    for k in (3, 4, 5, 6, 8):
        cells = []
        for y in ys:
            r = sweep[(k, y)]
            mark = " class=\"cur\"" if (k, y) == (4, "1/2") else ""
            cells.append(f"<td{mark}>{tr(r['kesinlik'])} / {tr(r['duyarlilik'])}</td>")
        rows.append(f"<tr><th>en az {k} hesap</th>{''.join(cells)}</tr>")
    return ("<table class=\"num grid\"><thead><tr><th>Küme eşiği</th>" + head + "</tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


def t_oran() -> str:
    rows = []
    for r in extra["maliyet_orani"]:
        rows.append(f"<tr><td class=\"n\">{tr(r['oran'], 1)}</td><td>en az {r['kume']} hesap, "
                    f"yoğunluk ≥ {r['yogunluk']}</td><td class=\"n\">{r['yn']}</td>"
                    f"<td class=\"n\">{r['yp']}</td><td class=\"n\">{tr(r['maliyet'], 1)}</td></tr>")
    nobody = res["hic_kimse"]["yn"]
    return ("<table class=\"num\"><thead><tr><th>Yanlış işaretin bedeli r<br>(kaçan baskıncı = 1)</th>"
            "<th>En ucuz eşik</th><th>YN</th><th>YP</th><th>Maliyet</th></tr></thead><tbody>"
            + "".join(rows) + f"</tbody></table><p class=\"note\">Karşılaştırma: hiç kimseyi işaretlememenin "
            f"maliyeti her oranda {nobody} birimdir (yalnızca kaçan baskıncılar).</p>")


def t_canli() -> str:
    rows = []
    for key in ("rastgele", "hic_kimse", "yeni_uye", "kume", "karar_agaci"):
        r = live["sonuclar"][key]
        rows.append(f"<tr><td>{NAMES[key]}</td><td class=\"n\">{r['dp']}/{r['dp'] + r['yn']}</td>"
                    f"<td class=\"n\">{r['yp']}</td><td class=\"n\">{pct(r['dogruluk'])}</td></tr>")
    return ("<table class=\"num\"><thead><tr><th>Tespitçi</th><th>Yakalanan baskıncı</th>"
            "<th>Yanlış işaret</th><th>Doğruluk</th></tr></thead><tbody>" + "".join(rows)
            + "</tbody></table>")


def t_gecikme() -> str:
    rows = []
    for label, m in lat["olcumler"].items():
        rows.append(f"<tr><td>{label}</td><td class=\"n\">{tr(m['ortalama'], 1)}</td>"
                    f"<td class=\"n\">{tr(m['p50'], 1)}</td><td class=\"n\">{tr(m['p95'], 1)}</td>"
                    f"<td class=\"n\">{tr(m['p99'], 1)}</td><td class=\"n\">{tr(m['en_buyuk'], 1)}</td></tr>")
    return ("<table class=\"num\"><thead><tr><th>Uç nokta</th><th>Ortalama</th><th>p50</th><th>p95</th>"
            "<th>p99</th><th>En büyük</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>")


def t_veri() -> str:
    v = extra["veri"]
    rows = []
    for key, label in (("egitim", "Eğitim"), ("sinama", "Sınama (sabit dosya)")):
        d = v[key]
        rows.append(f"<tr><td>{label}</td><td class=\"n\">{d['senaryo']}</td>"
                    f"<td class=\"n\">{thousands(d['hesap'])}</td><td class=\"n\">{thousands(d['yeni_uye'])}</td>"
                    f"<td class=\"n\">{d['baskinci']}</td><td class=\"n\">{d['baskinli_senaryo']}</td></tr>")
    return ("<table class=\"num\"><thead><tr><th>Küme</th><th>Senaryo</th><th>Hesap</th>"
            "<th>Son 7 günde katılan</th><th>Baskıncı</th><th>Baskınlı senaryo</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


def t_crisp_veri() -> str:
    v = crisp["veri"]
    dist = list(v["agirlik_dagilimi"].items())
    dist_txt = " · ".join(f"{tr(float(k), 1)}: {n}" + (" çift" if i == 0 else "")
                          for i, (k, n) in enumerate(dist))
    age = v["uyelik_yasi_gun"]

    def num(x: float) -> str:
        return thousands(int(x)) if float(x).is_integer() else tr(x, 1)

    cands = sorted(v["adaylar"], key=lambda a: -a["katilim_saat_once"])
    n = len(cands)
    possible = n * (n - 1) // 2
    weights = sorted({int(w) if float(w).is_integer() else w for w in v["aday_kenar_agirliklari"]})
    hours = [a["katilim_saat_once"] for a in cands]
    rows = [
        ("Genel kapsamda oy hakkı olan seçmen", thousands(v["secmen"])),
        ("Seçmenler arasındaki yönlü etkileşim kenarı", thousands(v["yonlu_kenar"])),
        ("Yönsüz çift (iki yön toplanınca)", thousands(v["yonsuz_cift"])),
        ("Çift ağırlıklarının dağılımı", dist_txt),
        ("Üyelik yaşı (gün)", f"en küçük {num(age['en_kucuk'])} · medyan {num(age['medyan'])} · "
                              f"en büyük {num(age['en_buyuk'])}"),
        ("Son 7 günde katılan (aday)", f"{n}: " + ", ".join(a["takma_ad"] for a in cands)),
        ("Adaylar arasındaki çift ve ağırlıkları",
         f"{v['aday_kenar']} çift" + (" (olası çiftlerin tamamı)" if v["aday_kenar"] == possible else "")
         + " · ağırlıklar " + " ya da ".join(str(w) for w in weights)),
        ("Adayların katılım yayılımı", f"{_cluster['yayilim_dk']} dakika ({tr(min(hours), 1)} ile "
                                      f"{tr(max(hours), 1)} saat önce)"),
    ]
    body = "".join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b in rows)
    return ("<table><thead><tr><th>Ölçüm (Karar Saati #1 açılışı)</th><th>Değer</th></tr></thead>"
            f"<tbody>{body}</tbody></table>")


def t_crisp_karisiklik() -> str:
    sk = crisp["temel"]["skor"]
    return ("<table><thead><tr><th></th><th>İşaretlendi</th><th>İşaretlenmedi</th></tr></thead><tbody>"
            f"<tr><td><b>Gerçek baskıncı</b></td><td class=\"yes\">{sk['dogru_isaret']} (doğru işaret)</td>"
            f"<td>{sk['kacan']} (kaçan)</td></tr>"
            f"<tr><td><b>Baskıncı değil</b></td><td>{sk['yanlis_isaret']} (yanlış işaret)</td>"
            f"<td class=\"yes\">{sk['dogru_temiz']} (doğru temiz)</td></tr></tbody></table>")


CRISP_SCENARIOS = [
    ("Tohumdaki biçim", "Tohumdaki biçim: 5 hesap 8 dakika arayla açılır, ilk mesaja yanıt verir",
     "Gerçek veri sonucuyla aynı"),
    ("Sınıf", "Gerçek bir sınıf: 6 öğrenci aynı öğleden sonra kaydolur, birbirine yanıt verir",
     "Yapı niyeti ayırmaz (bilinçli açık)"),
    ("Sabırlı baskın", "Sabırlı baskın: 5 hesap ikişer gün arayla, 10 güne yayılır",
     "Yayılım ve yenilik pencereleri aşılınca görünmez"),
    ("Sessiz baskın", "Sessiz baskın: 5 hesap 2 saat arayla açılır, hiç etkileşmez, yalnızca oy verir",
     "Etkileşim yoksa kenar yok"),
    ("Bölünmüş baskın", "Bölünmüş baskın: 4 hesap ikişerli iki kümeye ayrılır",
     "Küme eşiğinin altına bölünerek kaçılır"),
]


def t_crisp_senaryo() -> str:
    by_name = {x["senaryo"].split(" (")[0]: x for x in _scen}
    rows = []
    for key, desc, meaning in CRISP_SCENARIOS:
        sk = by_name[key]["skor"]
        truth = sk["dogru_isaret"] + sk["kacan"]
        if truth:
            ok = sk["kacan"] == 0
            res_txt = f"{sk['dogru_isaret']}/{truth} yakalandı" if ok else f"{sk['kacan']} kaçtı"
            kind = "Baskın"
        else:
            ok = sk["yanlis_isaret"] == 0
            res_txt = "işaret yok" if ok else f"{sk['yanlis_isaret']} yanlış işaret"
            kind = "Baskın değil"
        cls = "yes" if ok else "no-x"
        rows.append(f"<tr><td>{desc}</td><td>{kind}</td><td class=\"{cls}\">{res_txt}</td><td>{meaning}</td></tr>")
    return ("<table><thead><tr><th>Senaryo</th><th>Gerçek</th><th>Sonuç</th><th>Ne gösterir</th></tr></thead>"
            "<tbody>" + "".join(rows) + "</tbody></table>")


TABLE_GROUPS = [
    ("Kimlik ve sistem", ["users", "verification_codes", "notifications", "sim_clock", "demo_state",
                          "scheduler_state"]),
    ("İçerik", ["topics", "messages", "message_versions", "media"]),
    ("Öneri ve karar", ["proposals", "objections", "closure_texts", "decisions", "dissents",
                        "regulation_changes"]),
    ("Karar Saati ve oy", ["decision_sessions", "session_items", "ballots", "dev_vote_plan"]),
    ("Havale", ["delegation_requests"]),
    ("Kararların sonucu", ["petitions", "petition_replies", "calendar_events", "event_attendance",
                           "event_reports"]),
    ("Mahzen", ["cellar_threads", "cellar_posts", "cellar_votes", "cellar_ballots"]),
    ("Defter", ["ledger_outbox"]),
]


def t_teknik_tablolar() -> str:
    grouped = {t for _, ts in TABLE_GROUPS for t in ts}
    missing = [t for t in DB_TABLES if t not in grouped]
    stale = [t for t in grouped if t not in DB_TABLES]
    if missing or stale:
        raise SystemExit(f"Tablo grupları güncel değil: eksik {missing}, olmayan {stale}")
    rows = "".join(f"<tr><td>{g}</td><td class=\"mono\">{', '.join(ts)}</td></tr>" for g, ts in TABLE_GROUPS)
    return f"<table><thead><tr><th style=\"width:24%\">Grup</th><th>Tablolar</th></tr></thead><tbody>{rows}</tbody></table>"


ROUTER_LABELS = {
    "auth": "Kimlik", "users": "Kullanıcı ve profil", "ontology": "Ontoloji ve yönetmelik",
    "topics": "Konular ve mesajlar", "proposals": "Öneriler", "decision_hour": "Karar Saati, şerh, havale",
    "cellar": "Mahzen", "petitions": "Muhatap ve dilekçe", "calendar": "Takvim ve etkinlik",
    "media": "Görseller", "news": "Haberler", "search": "Arama", "notifications": "Bildirimler",
    "ledger": "Defter", "health": "Sağlık", "dev_demo": "Geliştirme (yalnızca dev)",
    "devtools": "Geliştirme (yalnızca yerel mod)",
}


def t_teknik_api() -> str:
    unknown = [k for k in ROUTES if k not in ROUTER_LABELS]
    if unknown:
        raise SystemExit(f"Yönlendirici etiketi yok: {unknown}")
    rows = []
    for key, label in ROUTER_LABELS.items():
        eps = ROUTES.get(key)
        if not eps:
            continue
        items = " · ".join(e.replace(" ", "\u00a0", 1) for e in eps)
        rows.append(f"<tr><td>{label}<br><span class=\"kicker\">{key} · {len(eps)}</span></td>"
                    f"<td class=\"mono\" style=\"font-size:7.6pt\">{items}</td></tr>")
    return ("<table><thead><tr><th style=\"width:22%\">Bölüm</th><th>Uç noktalar</th></tr></thead>"
            "<tbody>" + "".join(rows) + "</tbody></table>")


def t_dsm() -> str:
    """Paket bağımlılık matrisi (sema.json): satır içe aktaran, sütun içe aktarılan paket."""
    pk = json.loads((ROOT / "sema.json").read_text(encoding="utf-8"))["packages"]
    # Katman sırası: bir paket yalnızca kendinden sonrakileri içe aktarıyorsa sayılar köşegenin üstünde kalır.
    units = [u for u in ["devserver", "evaluation", "cli", "main", "routers", "services", "context", "graph",
                         "clock", "db", "domain", "config", "errors", "data"] if u in pk["units"]]
    if set(units) != set(pk["units"]):
        raise SystemExit(f"DSM paket listesi güncel değil: {sorted(set(pk['units']) - set(units))}")
    head = "".join(f'<th class="n" style="writing-mode:vertical-rl;transform:rotate(180deg);'
                   f'padding:2pt 0">{u}</th>' for u in units)
    rows = []
    for u in units:
        deps = pk["deps"].get(u, {})
        cells = "".join(
            '<td class="n" style="background:#E6E1D6">·</td>' if v == u else
            f'<td class="n">{deps[v]}</td>' if v in deps else '<td class="n"></td>' for v in units)
        rows.append(f'<tr><td class="k">{u}</td>{cells}<td class="n">{sum(deps.values())}</td></tr>')
    return ('<table class="num grid"><thead><tr><th>paket</th>' + head + '<th class="n">top.</th></tr></thead>'
            "<tbody>" + "".join(rows) + "</tbody></table>")


def t_gantt() -> str:
    """Aşama başına commit sayısı ve tarih aralığı (git geçmişinden, diyagramlar._GANTT)."""
    import diyagramlar
    commits = diyagramlar._commits()
    phase_of = {h: i for i, (_, hs) in enumerate(diyagramlar._GANTT) for h in hs.split()}
    rows: dict[int, list] = {i: [] for i in range(len(diyagramlar._GANTT))}
    names = [n.replace("\n", " ") for n, _ in diyagramlar._GANTT]
    for h, t, subj in commits:
        i = phase_of.get(h)
        if i is None:
            i = names.index("Tohum içeriği") if subj.startswith("Tohum") else len(names) - 1
        rows[i].append(t)
    out = []
    for i, n in enumerate(names):
        ts = sorted(rows[i])
        if not ts:
            continue
        a, b = ts[0], ts[-1]
        span = (f"{a.day}.{a.month:02d}" if a.date() == b.date()
                else f"{a.day}.{a.month:02d} – {b.day}.{b.month:02d}")
        out.append(f'<tr><td>{n}</td><td class="n">{len(ts)}</td><td class="n">{span}</td></tr>')
    total = sum(len(v) for v in rows.values())
    out.append(f'<tr><td><b>Toplam</b></td><td class="n"><b>{total}</b></td><td></td></tr>')
    return ('<table class="num"><thead><tr><th>Aşama</th><th class="n">Commit</th><th class="n">Tarih</th>'
            "</tr></thead><tbody>" + "".join(out) + "</tbody></table>")


# --- UML ve diğer diyagramlar (diyagramlar.py) -----------------------------------------------------

# Milimetre: A4 sütunu 176, A5 sütunu 126, A5 sayfa yüksekliği (kenar boşluklarından sonra) 185.
A4_COL, A5_COL, A5_PAGE = 176.0, 126.0, 185.0
# A5'te sütuna konan diyagramın en küçük ölçeği (mm/birim): 9,6 birimlik yazı 5,6 pt olur. Daha
# küçüğünü gerektiren diyagram kendi sayfasına, sığmazsa yan çevrilerek yerleşir.
A5_MIN = 0.205
A5_MAX = 0.26


def uml_figures(body: str, edition: str) -> str:
    sys.path.insert(0, str(ROOT))
    import diyagramlar

    def one(m: re.Match) -> str:
        attrs, name, rest = m.group(1), m.group(2), m.group(3)
        d = getattr(diyagramlar, name)()
        if edition == "a4":
            width = min(A4_COL, d.w * A4_COL / 760)
            return (f'<figure class="uml"{attrs}><div class="umlbox" style="width:{width:.1f}mm">'
                    f'{d.svg}</div>{rest}</figure>')
        inline = min(A5_COL / d.w, A5_MAX)
        if inline >= A5_MIN and d.h * inline <= 120:
            return (f'<figure class="uml"{attrs}><div class="umlbox" style="width:{d.w * inline:.1f}mm">'
                    f'{d.svg}</div>{rest}</figure>')
        cap = 18  # açıklamaya ayrılan yükseklik
        portrait = min(A5_COL / d.w, (A5_PAGE - cap) / d.h, A5_MAX)
        landscape = min(A5_PAGE / d.w, (A5_COL - cap) / d.h, A5_MAX)
        sc = max(portrait, landscape)
        box = (f'<div class="umlbox" style="width:{d.w * sc:.1f}mm;height:{d.h * sc:.1f}mm">'
               f'{d.svg}</div>{rest}')
        if landscape > portrait * 1.04:
            return f'<figure class="uml turn"{attrs}><div class="rot">{box}</div></figure>'
        return f'<figure class="uml page"{attrs}>{box}</figure>'

    return re.sub(r'<figure class="uml"([^>]*)>\s*\{\{uml:([a-z0-9_]+)\}\}(.*?)</figure>', one, body,
                  flags=re.S)


# --- grafikler (SVG) --------------------------------------------------------------------------------


def svg_merdiven() -> str:
    keys = ["rastgele", "hic_kimse", "yeni_uye", "kume", "karar_agaci"]
    w, row, left = W, 30, 190
    h = 34 + row * len(keys)
    scale = (w - left - 20) / 1.0
    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Kesinlik ve duyarlılık">']
    for i in range(0, 11, 2):
        x = left + scale * i / 10
        parts.append(f'<line x1="{x}" y1="18" x2="{x}" y2="{h - 6}" stroke="{HAIR}" stroke-width="0.6"/>'
                     f'<text x="{x}" y="12" font-size="9" text-anchor="middle" class="m" fill="{SOFT}">{tr(i / 10, 1)}</text>')
    for i, k in enumerate(keys):
        y = 24 + i * row
        p, r = res[k]["kesinlik"], res[k]["duyarlilik"]
        parts.append(f'<text x="{left - 8}" y="{y + 14}" font-size="11.5" text-anchor="end">{NAMES[k]}</text>')
        parts.append(f'<rect x="{left}" y="{y + 2}" width="{max(1, scale * p):.1f}" height="9" fill="{INK}"/>')
        # Siyah-beyaz baskıda da ayrılsın: kesinlik dolu, duyarlılık boş (çerçeveli) çubuk.
        parts.append(f'<rect x="{left}" y="{y + 13.5}" width="{max(1, scale * r):.1f}" height="8" fill="#fff" stroke="{INK}" stroke-width="1"/>')
        parts.append(f'<text x="{left + scale * p + 4:.1f}" y="{y + 10}" font-size="8.5" class="m" fill="{INK}">{tr(p)}</text>')
        parts.append(f'<text x="{left + scale * r + 4:.1f}" y="{y + 21}" font-size="8.5" class="m" fill="{INK}">{tr(r)}</text>')
    parts.append(f'<rect x="{w - 210}" y="{h - 16}" width="9" height="9" fill="{INK}"/><text x="{w - 197}" y="{h - 8}" font-size="10">kesinlik</text>'
                 f'<rect x="{w - 130}" y="{h - 15.5}" width="8" height="8" fill="#fff" stroke="{INK}" stroke-width="1"/><text x="{w - 117}" y="{h - 8}" font-size="10">duyarlılık</text>')
    parts.append("</svg>")
    return "".join(parts)


def svg_basabas() -> str:
    pts = [(r["sinif_payi"], r["basabas_orani"]) for r in extra["sinif_payi"] if r["basabas_orani"]]
    w, h, l, b, t, rgt = W, 230, 60, 40, 16, 20
    xmax, ymax = 0.5, 5.0

    def x(v: float) -> float:
        return l + (w - l - rgt) * v / xmax

    def y(v: float) -> float:
        return h - b - (h - b - t) * min(v, ymax) / ymax

    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Başa baş oranı">']
    for v in (0, 1, 2, 3, 4, 5):
        parts.append(f'<line x1="{l}" y1="{y(v)}" x2="{w - rgt}" y2="{y(v)}" stroke="{HAIR}" stroke-width="0.6"/>'
                     f'<text x="{l - 6}" y="{y(v) + 3}" font-size="9" text-anchor="end" class="m" fill="{SOFT}">{v}</text>')
    for v in (0, 0.1, 0.2, 0.35, 0.5):
        parts.append(f'<text x="{x(v)}" y="{h - b + 14}" font-size="9" text-anchor="middle" class="m" fill="{SOFT}">%{int(v * 100)}</text>')
    for r_line, label in ((1, "r = 1: iki hata eşit"), (5, "r = 5: raporun varsayımı")):
        parts.append(f'<line x1="{l}" y1="{y(r_line)}" x2="{w - rgt}" y2="{y(r_line)}" stroke="{SEAL}" stroke-width="0.9" stroke-dasharray="4 3"/>'
                     f'<text x="{w - rgt - 4}" y="{y(r_line) - 4}" font-size="9.5" text-anchor="end" fill="{SEAL}">{label}</text>')
    path = " ".join(f"{'M' if i == 0 else 'L'}{x(a):.1f} {y(bb):.1f}" for i, (a, bb) in enumerate(pts))
    parts.append(f'<path d="{path}" fill="none" stroke="{INK}" stroke-width="1.6"/>')
    for a, bb in pts:
        parts.append(f'<circle cx="{x(a):.1f}" cy="{y(bb):.1f}" r="3" fill="{INK}"/>'
                     f'<text x="{x(a) + 6:.1f}" y="{y(bb) - 6:.1f}" font-size="9.5" class="m">{tr(bb)}</text>')
    parts.append(f'<text x="{(l + w - rgt) / 2}" y="{h - 6}" font-size="10.5" text-anchor="middle" fill="{SOFT}">senaryolarda birlikte kaydolan gerçek grubun (sınıf) bulunma payı</text>')
    parts.append(f'<text x="14" y="{(h - b + t) / 2}" font-size="10.5" text-anchor="middle" fill="{SOFT}" transform="rotate(-90 14 {(h - b + t) / 2})">başa baş oranı r*</text>')
    parts.append("</svg>")
    return "".join(parts)


def svg_gecikme() -> str:
    items = list(lat["olcumler"].items())
    w, row, left = W, 24, 200
    h = 30 + row * len(items)
    vmax = max(m["en_buyuk"] for _, m in items)
    scale = (w - left - 40) / vmax
    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Gecikme dağılımı">']
    for v in range(0, int(vmax) + 1, 20):
        xx = left + scale * v
        parts.append(f'<line x1="{xx}" y1="16" x2="{xx}" y2="{h - 4}" stroke="{HAIR}" stroke-width="0.6"/>'
                     f'<text x="{xx}" y="11" font-size="9" text-anchor="middle" class="m" fill="{SOFT}">{v} ms</text>')
    for i, (label, m) in enumerate(items):
        yy = 22 + i * row
        parts.append(f'<text x="{left - 8}" y="{yy + 11}" font-size="10.5" text-anchor="end">{label}</text>')
        parts.append(f'<line x1="{left + scale * m["p50"]:.1f}" y1="{yy + 7}" x2="{left + scale * m["en_buyuk"]:.1f}" y2="{yy + 7}" stroke="{SOFT}" stroke-width="1"/>')
        parts.append(f'<rect x="{left + scale * m["p50"] - 2:.1f}" y="{yy + 1}" width="4" height="12" fill="{INK}"/>')
        parts.append(f'<rect x="{left + scale * m["p99"] - 2.5:.1f}" y="{yy + 1}" width="5" height="12" fill="#fff" stroke="{INK}" stroke-width="1.1"/>')
        parts.append(f'<circle cx="{left + scale * m["en_buyuk"]:.1f}" cy="{yy + 7}" r="2.6" fill="none" stroke="{SOFT}"/>')
    parts.append("</svg>")
    return "".join(parts)


TABLES = {"merdiven": t_merdiven, "karisiklik": t_karisiklik, "bicim": t_bicim, "esik": t_esik,
          "oran": t_oran, "canli": t_canli, "gecikme": t_gecikme, "veri": t_veri,
          "crisp_veri": t_crisp_veri, "crisp_karisiklik": t_crisp_karisiklik,
          "crisp_senaryo": t_crisp_senaryo, "teknik_tablolar": t_teknik_tablolar, "teknik_api": t_teknik_api,
          "dsm": t_dsm, "gantt": t_gantt}
SVGS = {"merdiven": svg_merdiven, "basabas": svg_basabas, "gecikme": svg_gecikme}


# --- birleştirme ------------------------------------------------------------------------------------


# A5: görsel → kırpılacak bölgeler (x0, y0, x1, y1, metin genişliğinin yüzdesi). Bölgeler alt alta durur.
CROPS_A5: dict[str, list[tuple[int, int, int, int, int]]] = {
    "istanbul-daralma.png": [(20, 110, 890, 600, 100)],
    "r9-red.png": [(0, 0, 830, 530, 100)],
    "karar-saati-sonuc.png": [(95, 235, 712, 805, 72), (728, 235, 1345, 785, 72)],
    "yonetmelik.png": [(368, 228, 1340, 900, 100)],
    "sansur-seridi.png": [(0, 0, 840, 740, 95)],
    "mahzen.png": [(0, 0, 840, 880, 100)],
    "konu-pazar.png": [(95, 115, 935, 840, 100), (985, 282, 1343, 392, 75)],
    "dilekce.png": [(0, 0, 820, 730, 100)],
    "dilekce-telefon.png": [(0, 0, 390, 844, 50)],
    "etkinlik-formu.png": [(245, 0, 1040, 742, 100)],
    "takvim.png": [(0, 0, 690, 955, 78), (700, 0, 1380, 640, 78)],
    "etkinlik.png": [(35, 115, 915, 420, 100), (965, 135, 1285, 350, 60)],
    "gazete.png": [(95, 225, 960, 720, 100), (1000, 225, 1345, 800, 55)],
    "gazete-telefon.png": [(0, 0, 390, 812, 50)],
    "gorsel-mesaj.png": [(0, 0, 880, 560, 100)],
    "gorsel-yukleme.png": [(0, 0, 880, 225, 100)],
    "defter.png": [(0, 0, 640, 800, 75)],
    "arama.png": [(30, 190, 870, 460, 100), (870, 270, 1290, 400, 60)],
    "denetim-geri-sayim.png": [(320, 0, 1120, 560, 100)],
    "denetim-crt.png": [(0, 0, 880, 620, 80), (904, 0, 1784, 620, 80)],
    "denetim-ifsa-kareleri.png": [(0, 0, 2180, 910, 100)],
}


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


def crop_images(body: str) -> str:
    def one(m: re.Match) -> str:
        name, alt = m.group(1), m.group(2)
        crops = CROPS_A5.get(name)
        if not crops:
            raise SystemExit(f"A5 için kırpma tanımı yok: {name}")
        width, _ = png_size(ROOT / "gorseller" / name)
        out = []
        for x0, y0, x1, y1, pct in crops:
            cw, ch = x1 - x0, y1 - y0
            out.append(
                f'<div class="crop" style="width:{pct}%;aspect-ratio:{cw}/{ch}">'
                f'<img src="gorseller/{name}" alt="{alt}" style="width:{100 * width / cw:.3f}%;'
                f'margin-left:-{100 * x0 / cw:.3f}%;margin-top:-{100 * y0 / cw:.3f}%"></div>')
        return "".join(out)

    return re.sub(r'<img src="gorseller/([^"]+)" alt="([^"]*)">', one, body)


def build(edition: str = "a4") -> str:
    head = (ROOT / "bolumler" / "_head.html").read_text(encoding="utf-8")
    if edition == "a5":
        head += (ROOT / "bolumler" / "_a5.html").read_text(encoding="utf-8")
    cover = (ROOT / "bolumler" / "_kapak.html").read_text(encoding="utf-8")
    body = "\n".join((ROOT / "bolumler" / f).read_text(encoding="utf-8") for f in FRAGMENTS)
    while "{{include:" in body:
        body = re.sub(r"\{\{include:([a-z0-9_-]+\.html)\}\}",
                      lambda m: (ROOT / "bolumler" / m.group(1)).read_text(encoding="utf-8"), body)

    body = uml_figures(body, edition)

    order = re.findall(r'<section id="([a-z]+)"', body)
    expected = [s for _, _, ids in PARTS for s in ids]
    if order != expected:
        raise SystemExit(f"Bölüm sırası beklenenden farklı:\n{order}\n{expected}")
    number = {sid: i + 1 for i, sid in enumerate(order)}

    def number_section(m: re.Match) -> str:
        return m.group(0).replace('<span class="no">#</span>', f'<span class="no">{number[m.group(1)]}</span>')

    body = re.sub(r'<section id="([a-z]+)"[^>]*>\s*<h2><span class="no">#</span>', number_section, body)
    body = re.sub(r"\{\{ref:([a-z]+)\}\}", lambda m: str(number[m.group(1)]), body)

    figs: list[str] = []
    for m in re.finditer(r'data-fig="([a-z0-9-]+)"', body):
        if m.group(1) not in figs:
            figs.append(m.group(1))
    fignum = {f: i + 1 for i, f in enumerate(figs)}
    body = re.sub(r'(<figure[^>]*data-fig="([a-z0-9-]+)"[^>]*>.*?<b>Şekil )#(\.</b>)',
                  lambda m: f"{m.group(1)}{fignum[m.group(2)]}{m.group(3)}", body, flags=re.S)
    body = re.sub(r"\{\{fig:([a-z0-9-]+)\}\}", lambda m: str(fignum[m.group(1)]), body)

    body = re.sub(r"\{\{t:([a-z_]+)\}\}", lambda m: TABLES[m.group(1)](), body)
    body = re.sub(r"\{\{svg:([a-z]+)\}\}", lambda m: SVGS[m.group(1)](), body)
    body = re.sub(r"\{\{v:([^}]+)\}\}", lambda m: value(m.group(1)), body)
    body = re.sub(r"\{\{p:([^}]+)\}\}", lambda m: pct(float(raw(m.group(1)))), body)

    titles = dict(re.findall(r'<section id="([a-z]+)"[^>]*>\s*<h2><span class="no">\d+</span>([^<]+)</h2>', body))
    toc = []
    for roman, name, ids in PARTS:
        toc.append(f'<div class="part"><span>{roman}</span>{name}</div>')
        toc += [f'<div><span>{number[s]}</span>{titles[s]}</div>' for s in ids]
    cover = cover.replace("{{toc}}", "\n".join(toc))
    for roman, name, ids in PARTS:
        body = body.replace(f'<section id="{ids[0]}"',
                            f'<div class="partHead"><span>Bölüm {roman}</span>{name}</div>\n<section id="{ids[0]}"', 1)

    # Sürüme özgü açıklama parçaları: yalnızca kendi sürümünde kalır.
    other = "a4" if edition == "a5" else "a5"
    body = re.sub(rf'<span class="{other}">.*?</span>', "", body, flags=re.S)
    body = re.sub(rf'<span class="{edition}">(.*?)</span>', r"\1", body, flags=re.S)
    if edition == "a5":
        body = crop_images(body)

    left = re.findall(r"\{\{[^}]+\}\}|<span class=\"no\">#</span>|Şekil #\.", body + cover)
    if left:
        raise SystemExit(f"Doldurulmamış yer tutucular: {sorted(set(left))}")
    return f"{head}</head>\n<body>\n{cover}\n{body}\n</body>\n</html>\n"


if __name__ == "__main__":
    edition = "a5" if "--a5" in sys.argv[1:] else "a4"
    if edition == "a5":
        W = 560
    out = ROOT / ("rapor-a5.html" if edition == "a5" else "rapor.html")
    out.write_text(build(edition), encoding="utf-8")
    print(f"{out} yazıldı")
