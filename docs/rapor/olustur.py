"""Raporu bölüm parçalarından ve ölçüm dosyalarından üretir.

    python3 docs/rapor/olustur.py        # docs/rapor/rapor.html yazılır
    node docs/rapor/pdf.mjs              # A4 PDF (ayrıntı dosyanın başında)

Sayılar elle yazılmaz: baskın tespitinin sonuçları ``docs/degerlendirme/sonuclar.json``'dan,
gecikme ``docs/degerlendirme/gecikme.json``'dan, test sayıları ``testler.json``'dan okunur.
Parçalardaki yer tutucular:

- ``{{t:ad}}``  tablo, ``{{svg:ad}}`` grafik, ``{{v:yol}}`` tek değer (ör. ``{{v:canli.secmen}}``),
- ``{{ref:bolum}}`` bölüm numarası (``<section id="bolum">``),
- ``<b>Şekil #.</b>`` ve ``{{fig:ad}}``: şekiller sırayla numaralanır (``data-fig="ad"``).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EVAL = ROOT.parent / "degerlendirme"
PARTS = [
    ("I", "Problem ve analiz", ["ozet", "cerceve", "paydas", "yz", "metrik", "baskin"]),
    ("II", "Tasarım ve kod", ["desen", "sistem"]),
    ("III", "Politikalar", ["azinlik", "kapsam", "sinirlama", "akis", "yonetmelik", "havale",
                            "silme", "mahzen", "sonuc", "gorsel", "butunluk", "kolaylik"]),
    ("IV", "Süreç", ["sorunlar", "aciklar", "test", "beyan", "kaynak"]),
]
FRAGMENTS = ["analiz.html", "desenler.html", "sistem.html", "politikalar.html", "kolaylik.html",
             "surec.html"]
NAMES = {"rastgele": "Rastgele", "hic_kimse": "Hiç kimse", "yeni_uye": "Yeni üye kuralı",
         "kume": "Küme kuralı (üretim)", "karar_agaci": "Karar ağacı (öğrenilen)"}
GROUPS = {"baskin_hizli": "hızlı baskın", "baskin_kamufle": "kamufle baskın",
          "baskin_bolunmus": "bölünmüş baskın", "baskin_sabirli": "sabırlı baskın",
          "baskin_sessiz": "sessiz baskın", "sinif": "gerçek grup (sınıf)",
          "duyuru": "duyuru dalgası", "tekil": "tek tük yeni üye"}

INK, SOFT, HAIR, SEAL, OK = "#1B1A17", "#4A463E", "#CFC6B3", "#7A1E2B", "#2F4A2A"


def tr(x: float, d: int = 2) -> str:
    """Türkçe ondalık: 0,32."""
    return f"{x:.{d}f}".replace(".", ",")


def thousands(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def pct(x: float, d: int = 1) -> str:
    return "%" + tr(100 * x, d)


# --- veriler ----------------------------------------------------------------------------------------

ev = json.loads((EVAL / "sonuclar.json").read_text(encoding="utf-8"))
lat = json.loads((EVAL / "gecikme.json").read_text(encoding="utf-8"))
tests = json.loads((ROOT / "testler.json").read_text(encoding="utf-8"))
res = {r["tespitci"]: r for r in ev["sonuclar"] if r["kume"] == "sinama"}
new = {r["tespitci"]: r for r in ev["sonuclar"] if r["kume"] == "yeni"}
extra = ev["ek"]
live = extra["canli"]


def raw(path: str) -> object:
    cur: object = {"canli": live, "veri": extra["veri"], "test": tests, "sonuc": res, "yeni": new,
                   "sinif": extra["sinif_payi"], "bicim": extra["bicime_gore"],
                   "gecikme": lat["olcumler"]}
    for part in path.split("."):
        cur = cur[int(part)] if part.isdigit() else cur[part]  # type: ignore[index]
    return cur


def value(path: str) -> str:
    cur: object = {"canli": live, "veri": extra["veri"], "test": tests, "sonuc": res, "yeni": new,
                   "sinif": extra["sinif_payi"], "bicim": extra["bicime_gore"],
                   "gecikme": lat["olcumler"]}
    for part in path.split("."):
        cur = cur[int(part)] if part.isdigit() else cur[part]  # type: ignore[index]
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


# --- grafikler (SVG) --------------------------------------------------------------------------------


def svg_merdiven() -> str:
    keys = ["rastgele", "hic_kimse", "yeni_uye", "kume", "karar_agaci"]
    w, row, left = 760, 30, 190
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
    w, h, l, b, t, rgt = 760, 230, 60, 40, 16, 20
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
    w, row, left = 760, 24, 200
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
          "oran": t_oran, "canli": t_canli, "gecikme": t_gecikme, "veri": t_veri}
SVGS = {"merdiven": svg_merdiven, "basabas": svg_basabas, "gecikme": svg_gecikme}


# --- birleştirme ------------------------------------------------------------------------------------


def build() -> str:
    head = (ROOT / "bolumler" / "_head.html").read_text(encoding="utf-8")
    cover = (ROOT / "bolumler" / "_kapak.html").read_text(encoding="utf-8")
    body = "\n".join((ROOT / "bolumler" / f).read_text(encoding="utf-8") for f in FRAGMENTS)

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

    body = re.sub(r"\{\{t:([a-z]+)\}\}", lambda m: TABLES[m.group(1)](), body)
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

    left = re.findall(r"\{\{[^}]+\}\}|<span class=\"no\">#</span>|Şekil #\.", body + cover)
    if left:
        raise SystemExit(f"Doldurulmamış yer tutucular: {sorted(set(left))}")
    return f"{head}</head>\n<body>\n{cover}\n{body}\n</body>\n</html>\n"


if __name__ == "__main__":
    out = ROOT / "rapor.html"
    out.write_text(build(), encoding="utf-8")
    print(f"{out} yazıldı")
