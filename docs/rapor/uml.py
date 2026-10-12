"""Raporun diyagramları için küçük bir SVG çizicisi.

Diyagramlar (sınıf, kullanım durumu, sıralama, durum, etkinlik, bileşen, paket, dağıtım, ER, veri
akışı, Gantt) raporun yazı tipleriyle ve siyah-beyaz baskıya uygun çizilir: renk yalnızca mürekkep
ve açık gri dolgudur, ayrım çizgi biçimiyle (dolu, kesikli, boş ya da dolu uç) yapılır.

Yazı genişliği raporun kendi yazı tiplerinden ölçülür (Pillow), kutular yazıya göre boyutlanır.
Koordinatlar SVG birimidir; rapor 760 birimi A4 sütun genişliğine eşler.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from html import escape
from pathlib import Path

from PIL import ImageFont

ROOT = Path(__file__).resolve().parent
_FONT_DIR = ROOT.parent.parent / "client" / "node_modules" / "@expo-google-fonts"
_FONTS = {
    "serif": "newsreader/400Regular/Newsreader_400Regular.ttf",
    "serifb": "newsreader/600SemiBold/Newsreader_600SemiBold.ttf",
    "serifi": "newsreader/400Regular_Italic/Newsreader_400Regular_Italic.ttf",
    "serifbi": "newsreader/600SemiBold_Italic/Newsreader_600SemiBold_Italic.ttf",
    "mono": "ibm-plex-mono/400Regular/IBMPlexMono_400Regular.ttf",
    "monob": "ibm-plex-mono/500Medium/IBMPlexMono_500Medium.ttf",
}
_ATTRS = {
    "serif": "", "serifb": ' font-weight="600"', "serifi": ' font-style="italic"',
    "serifbi": ' font-weight="600" font-style="italic"', "mono": ' class="m"',
    "monob": ' class="m" font-weight="500"',
}
INK, SOFT, MUTED, HAIR, WASH, WHITE = "#1B1A17", "#4A463E", "#6B6558", "#CFC6B3", "#F4EFE4", "#FFFFFF"
GREY = "#E6E1D6"


@lru_cache(maxsize=None)
def _font(kind: str) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_FONT_DIR / _FONTS[kind]), 200)


def tw(text: str, size: float = 11, kind: str = "serif") -> float:
    """Yazının SVG birimi cinsinden genişliği."""
    return _font(kind).getlength(text) * size / 200


# --- tuval -------------------------------------------------------------------------------------------


@dataclass
class Diagram:
    svg: str
    w: float
    h: float


class Canvas:
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.back: list[str] = []
        self.x0 = self.y0 = math.inf
        self.x1 = self.y1 = -math.inf

    def grow(self, x0: float, y0: float, x1: float, y1: float) -> None:
        self.x0, self.y0 = min(self.x0, x0, x1), min(self.y0, y0, y1)
        self.x1, self.y1 = max(self.x1, x0, x1), max(self.y1, y0, y1)

    def add(self, s: str, bbox: tuple[float, float, float, float] | None = None, *,
            behind: bool = False) -> None:
        (self.back if behind else self.parts).append(s)
        if bbox:
            self.grow(*bbox)

    def text(self, x: float, y: float, s: str, size: float = 11, kind: str = "serif",
             anchor: str = "start", fill: str = INK, behind: bool = False) -> float:
        w = tw(s, size, kind)
        x0 = x - (w if anchor == "end" else w / 2 if anchor == "middle" else 0)
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}"{_ATTRS[kind]}'
                 + (f' text-anchor="{anchor}"' if anchor != "start" else "")
                 + (f' fill="{fill}"' if fill != INK else "") + f">{escape(s)}</text>",
                 (x0, y - size * 0.8, x0 + w, y + size * 0.25), behind=behind)
        return w

    def rect(self, x: float, y: float, w: float, h: float, *, rx: float = 0, fill: str = WHITE,
             stroke: str = INK, sw: float = 1, dash: str | None = None, behind: bool = False) -> None:
        self.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}"'
                 + (f' rx="{rx}"' if rx else "") + f' fill="{fill}" stroke="{stroke}" stroke-width="{sw}"'
                 + (f' stroke-dasharray="{dash}"' if dash else "") + "/>", (x, y, x + w, y + h),
                 behind=behind)

    def line(self, pts: list[tuple[float, float]], *, sw: float = 1, dash: str | None = None,
             stroke: str = INK, behind: bool = False) -> None:
        d = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f} {y:.1f}" for i, (x, y) in enumerate(pts))
        self.add(f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="{sw}"'
                 + (f' stroke-dasharray="{dash}"' if dash else "") + ' stroke-linejoin="round"/>',
                 (min(p[0] for p in pts), min(p[1] for p in pts),
                  max(p[0] for p in pts), max(p[1] for p in pts)), behind=behind)

    def path(self, d: str, bbox: tuple[float, float, float, float], *, fill: str = "none",
             stroke: str = INK, sw: float = 1, behind: bool = False) -> None:
        self.add(f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"'
                 ' stroke-linejoin="round"/>', bbox, behind=behind)

    def circle(self, cx: float, cy: float, r: float, *, fill: str = WHITE, stroke: str = INK,
               sw: float = 1) -> None:
        self.add(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" fill="{fill}" stroke="{stroke}"'
                 f' stroke-width="{sw}"/>', (cx - r, cy - r, cx + r, cy + r))

    def ellipse(self, cx: float, cy: float, rx: float, ry: float, *, fill: str = WHITE) -> None:
        self.add(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="{fill}"'
                 f' stroke="{INK}" stroke-width="1"/>', (cx - rx, cy - ry, cx + rx, cy + ry))

    def done(self, label: str, pad: float = 4) -> Diagram:
        x0, y0 = self.x0 - pad, self.y0 - pad
        w, h = self.x1 - self.x0 + 2 * pad, self.y1 - self.y0 + 2 * pad
        body = "".join(self.back + self.parts)
        svg = (f'<svg class="uml" viewBox="{x0:.1f} {y0:.1f} {w:.1f} {h:.1f}" role="img" '
               f'aria-label="{escape(label)}">{body}</svg>')
        return Diagram(svg, w, h)


# --- kutular ve bağlantı uçları ------------------------------------------------------------------


@dataclass
class Box:
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    @property
    def r(self) -> float:
        return self.x + self.w

    @property
    def b(self) -> float:
        return self.y + self.h

    def p(self, side: str, t: float = 0.5) -> tuple[float, float]:
        """Kenar üzerindeki nokta: side t/b/l/r, t kenar boyunca 0..1."""
        if side == "t":
            return (self.x + self.w * t, self.y)
        if side == "b":
            return (self.x + self.w * t, self.b)
        if side == "l":
            return (self.x, self.y + self.h * t)
        return (self.r, self.y + self.h * t)


def _unit(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy) or 1
    return dx / n, dy / n


def _end(c: Canvas, tip: tuple[float, float], frm: tuple[float, float], kind: str) -> None:
    """Uç işareti: tip noktasında, frm'den tip'e yön."""
    ux, uy = _unit(frm, tip)
    px, py = -uy, ux
    x, y = tip

    def at(a: float, b: float) -> tuple[float, float]:
        return (x - ux * a + px * b, y - uy * a + py * b)

    def poly(pts: list[tuple[float, float]], fill: str) -> None:
        d = "M" + " L".join(f"{u:.1f} {v:.1f}" for u, v in pts) + " Z"
        c.path(d, (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts),
                   max(p[1] for p in pts)), fill=fill)

    if kind == "open":
        c.line([at(9, -4.5), (x, y), at(9, 4.5)])
    elif kind == "filled":
        poly([(x, y), at(9, -4), at(9, 4)], INK)
    elif kind == "tri":
        poly([(x, y), at(12, -7), at(12, 7)], WHITE)
    elif kind == "ftri":
        poly([(x, y), at(12, -7), at(12, 7)], INK)
    elif kind in ("diamond", "odiamond"):
        poly([(x, y), at(8, -5), at(16, 0), at(8, 5)], INK if kind == "diamond" else WHITE)
    elif kind.startswith("crow"):
        # crow_one, crow_zero_one, crow_many (sıfır ya da çok), crow_one_many
        many = kind in ("crow_many", "crow_one_many")
        if many:
            c.line([at(0, -6), at(11, 0), at(0, 6)])
            c.line([at(0, 0), at(11, 0)])
        if kind in ("crow_one", "crow_one_many"):
            c.line([at(15, -6), at(15, 6)])
            if kind == "crow_one":
                c.line([at(9, -6), at(9, 6)])
        if kind in ("crow_zero_one", "crow_many"):
            cx, cy = at(19, 0)
            c.circle(cx, cy, 3.5)
            if kind == "crow_zero_one":
                c.line([at(10, -6), at(10, 6)])


def edge(c: Canvas, pts: list[tuple[float, float]], *, head: str | None = None,
         tail: str | None = None, dash: bool = False, label: str | None = None,
         lpos: tuple[float, float] | None = None, lseg: int | None = None, lsize: float = 9.5,
         lkind: str = "serif", lanchor: str = "middle", ldy: float = -4, sw: float = 1) -> None:
    """Çizgi ve uçları. Etiket: lpos verilirse o noktada, yoksa lseg (varsayılan orta)
    parçasının ortasında, çizginin üstünde."""
    c.line(pts, dash="5 3" if dash else None, sw=sw)
    if head:
        _end(c, pts[-1], pts[-2], head)
    if tail:
        _end(c, pts[0], pts[1], tail)
    if label:
        if lpos is None:
            i = lseg if lseg is not None else (len(pts) - 2) // 2
            (ax, ay), (bx, by) = pts[i], pts[i + 1]
            lpos = ((ax + bx) / 2, (ay + by) / 2 + ldy)
        for k, line in enumerate(label.split("\n")):
            w = tw(line, lsize, lkind)
            x = lpos[0] - (w / 2 if lanchor == "middle" else w if lanchor == "end" else 0)
            c.rect(x - 2, lpos[1] + k * (lsize + 2) - lsize * 0.85, w + 4, lsize + 2, fill=WHITE,
                   stroke=WHITE, sw=0)
            c.text(lpos[0], lpos[1] + k * (lsize + 2), line, lsize, lkind, anchor=lanchor)


def vh(a: tuple[float, float], b: tuple[float, float], mid: float | None = None) -> list:
    """Dikey–yatay–dikey yol (a'dan b'ye)."""
    m = (a[1] + b[1]) / 2 if mid is None else mid
    return [a, (a[0], m), (b[0], m), b]


def hv(a: tuple[float, float], b: tuple[float, float], mid: float | None = None) -> list:
    """Yatay–dikey–yatay yol."""
    m = (a[0] + b[0]) / 2 if mid is None else mid
    return [a, (m, a[1]), (m, b[1]), b]


# --- sınıf diyagramı ---------------------------------------------------------------------------------


MEMBER = 9.6


def cls(c: Canvas, x: float, y: float, name: str, attrs: tuple | list = (), ops: tuple | list = (),
        *, stereo: str | None = None, italic: bool = False, w: float | None = None,
        fill: str = WHITE, head: str = WASH, size: float = 11.5, center_x: bool = False,
        mkind: str = "mono") -> Box:
    """UML sınıf kutusu: ad, nitelikler, işlemler. center_x: x kutunun ortası.
    mkind: üye yazısı (kod için mono, kavramsal model için serif)."""
    nk = "serifbi" if italic else "serifb"
    msize = MEMBER if mkind == "mono" else MEMBER + 1
    lines_w = [tw(name, size, nk)] + [tw(a, msize, mkind) for a in [*attrs, *ops]]
    if stereo:
        lines_w.append(tw(f"«{stereo}»", 9, "serifi"))
    width = w or max(lines_w) + 16
    if center_x:
        x -= width / 2
    head_h = 20 + (11 if stereo else 0)
    ah = (len(attrs) * (MEMBER + 3.4) + 6) if attrs else 0
    oh = (len(ops) * (MEMBER + 3.4) + 6) if ops else 0
    if not attrs and not ops:
        ah = 0
    h = head_h + ah + oh
    c.rect(x, y, width, h, fill=fill)
    c.rect(x, y, width, head_h, fill=head)
    yy = y + 13
    if stereo:
        c.text(x + width / 2, yy - 1, f"«{stereo}»", 9, "serifi", anchor="middle", fill=SOFT)
        yy += 11
    c.text(x + width / 2, yy + 1.5, name, size, nk, anchor="middle")
    yy = y + head_h
    for group in (attrs, ops):
        if not group:
            continue
        c.line([(x, yy), (x + width, yy)])
        ty = yy + MEMBER + 2
        for m in group:
            c.text(x + 7, ty, m, msize, mkind)
            ty += MEMBER + 3.4
        yy += len(group) * (MEMBER + 3.4) + 6
    return Box(x, y, width, h)


def tree(c: Canvas, parent: Box, children: list[Box], *, bus: float | None = None,
         head: str = "tri", dash: bool = False) -> None:
    """Kalıtım ya da gerçekleme ağacı: çocuklardan ortak hatta, hattan ebeveyne tek uç."""
    top = min(ch.y for ch in children)
    y = bus if bus is not None else (parent.b + top) / 2
    xs = [ch.cx for ch in children]
    c.line([(min(xs + [parent.cx]), y), (max(xs + [parent.cx]), y)], dash="5 3" if dash else None)
    for ch in children:
        c.line([(ch.cx, ch.y), (ch.cx, y)], dash="5 3" if dash else None)
    edge(c, [(parent.cx, y), parent.p("b")], head=head, dash=dash)


# --- kutu, not, paket, düğüm ----------------------------------------------------------------------


def box(c: Canvas, x: float, y: float, lines: list[str] | str, *, size: float = 11,
        kinds: list[str] | None = None, rx: float = 4, w: float | None = None,
        h: float | None = None, fill: str = WHITE, pad: float = 10, center_x: bool = False,
        dash: str | None = None, sw: float = 1, align: str = "middle") -> Box:
    lines = [lines] if isinstance(lines, str) else lines
    kinds = kinds or ["serif"] * len(lines)
    sizes = [size * (0.85 if k.startswith("mono") or k == "serifi" else 1) for k in kinds]
    width = w or max(tw(t, s, k) for t, s, k in zip(lines, sizes, kinds, strict=True)) + 2 * pad
    height = h or sum(s + 4 for s in sizes) + 10
    if center_x:
        x -= width / 2
    c.rect(x, y, width, height, rx=rx, fill=fill, dash=dash, sw=sw)
    total = sum(s + 4 for s in sizes) - 4
    ty = y + (height - total) / 2 + sizes[0] * 0.78
    for t, s, k in zip(lines, sizes, kinds, strict=True):
        if align == "middle":
            c.text(x + width / 2, ty, t, s, k, anchor="middle")
        else:
            c.text(x + pad, ty, t, s, k)
        ty += s + 4
    return Box(x, y, width, height)


def note(c: Canvas, x: float, y: float, lines: list[str], *, size: float = 9.5,
         w: float | None = None) -> Box:
    width = w or max(tw(t, size, "serifi") for t in lines) + 20
    h = len(lines) * (size + 3) + 10
    f = 8
    c.path(f"M{x} {y} H{x + width - f} L{x + width} {y + f} V{y + h} H{x} Z",
           (x, y, x + width, y + h), fill=WASH)
    c.path(f"M{x + width - f} {y} V{y + f} H{x + width}", (x, y, x + width, y + f))
    ty = y + 5 + size
    for t in lines:
        c.text(x + 8, ty, t, size, "serifi", fill=SOFT)
        ty += size + 3
    return Box(x, y, width, h)


def package(c: Canvas, x: float, y: float, w: float, h: float, name: str, *,
            fill: str = WHITE, sub: str | None = None, title_inside: bool = False) -> Box:
    tab_w = tw(name, 10.5, "serifb") + 14
    if title_inside:
        tab_w = min(tab_w, 60)
    c.rect(x, y - 14, tab_w, 14, fill=WASH)
    c.rect(x, y, w, h, fill=fill)
    if title_inside:
        c.text(x + 8, y + 15, name, 10.5, "serifb")
        if sub:
            c.text(x + 8, y + 28, sub, 9, "serifi", fill=SOFT)
    else:
        c.text(x + 7, y - 3.5, name, 10.5, "serifb")
    return Box(x, y, w, h)


def node3d(c: Canvas, x: float, y: float, w: float, h: float, name: str, *, d: float = 8,
           sub: str | None = None) -> Box:
    c.path(f"M{x} {y} L{x + d} {y - d} H{x + w + d} V{y + h - d} L{x + w} {y + h}",
           (x, y - d, x + w + d, y + h), fill=GREY)
    c.path(f"M{x + w} {y} L{x + w + d} {y - d}", (x + w, y - d, x + w + d, y))
    c.rect(x, y, w, h)
    c.text(x + 8, y + 15, name, 10.5, "serifb")
    if sub:
        c.text(x + 8, y + 27, sub, 9, "serifi", fill=SOFT)
    return Box(x, y, w, h)


def component(c: Canvas, x: float, y: float, name: str, lines: list[str] = (), *,
              w: float | None = None, stereo: str = "component", size: float = 11) -> Box:
    width = w or max([tw(name, size, "serifb") + 30] + [tw(t, 9.2, "serif") for t in lines]) + 18
    h = 34 + len(lines) * 12
    c.rect(x, y, width, h)
    # bileşen simgesi
    ix, iy = x + width - 18, y + 6
    c.rect(ix, iy, 12, 14)
    c.rect(ix - 3, iy + 3, 6, 3)
    c.rect(ix - 3, iy + 8, 6, 3)
    c.text(x + 8, y + 13, f"«{stereo}»", 8.5, "serifi", fill=SOFT)
    c.text(x + 8, y + 26, name, size, "serifb")
    ty = y + 38
    for t in lines:
        c.text(x + 8, ty, t, 9.2, "serif", fill=SOFT)
        ty += 12
    return Box(x, y, width, h)


def artifact(c: Canvas, x: float, y: float, name: str, *, w: float | None = None,
             sub: str | None = None) -> Box:
    width = w or max(tw(name, 9.6, "mono"), tw(sub or "", 8.6, "serifi")) + 30
    h = 20 if not sub else 31
    c.rect(x, y, width, h)
    fx, fy = x + width - 13, y + 4
    c.path(f"M{fx} {fy} H{fx + 6} L{fx + 9} {fy + 3} V{fy + 11} H{fx} Z", (fx, fy, fx + 9, fy + 11))
    c.text(x + 6, y + 13.5, name, 9.6, "mono")
    if sub:
        c.text(x + 6, y + 25, sub, 8.6, "serifi", fill=SOFT)
    return Box(x, y, width, h)


def db_icon(c: Canvas, x: float, y: float, w: float, h: float, name: str, sub: str = "") -> Box:
    e = 6
    c.path(f"M{x} {y + e} V{y + h - e} A{w / 2} {e} 0 0 0 {x + w} {y + h - e} V{y + e}",
           (x, y, x + w, y + h), fill=WHITE)
    c.ellipse(x + w / 2, y + e, w / 2, e, fill=GREY)
    c.text(x + w / 2, y + h / 2 + 6, name, 10.5, "serifb", anchor="middle")
    if sub:
        c.text(x + w / 2, y + h / 2 + 18, sub, 8.6, "serifi", anchor="middle", fill=SOFT)
    return Box(x, y, w, h)


# --- kullanım durumu ---------------------------------------------------------------------------------


def actor(c: Canvas, x: float, y: float, name: str, *, stereo: str | None = None,
          system: bool = False) -> Box:
    """Aktör: (x, y) başın üstünün ortası. system: kutu biçimli sistem aktörü."""
    if system:
        lines = name.split("\n")
        b = box(c, x, y + 4, lines, size=10.5, kinds=["serifb"] * len(lines), rx=0, center_x=True,
                fill=WASH)
        c.text(b.cx, y + 1, f"«{stereo or 'sistem'}»", 8.5, "serifi", anchor="middle", fill=SOFT)
        return Box(b.x, y - 8, b.w, b.h + 12)
    c.circle(x, y + 7, 7)
    c.line([(x, y + 14), (x, y + 32)])
    c.line([(x - 11, y + 20), (x + 11, y + 20)])
    c.line([(x - 9, y + 46), (x, y + 32), (x + 9, y + 46)])
    tw_ = 0.0
    for k, part in enumerate(name.split("\n")):
        tw_ = max(tw_, c.text(x, y + 58 + k * 11.5, part, 10.5, "serifb", anchor="middle"))
    if stereo:
        c.text(x, y + 58 + 11.5 * (name.count("\n") + 1), f"«{stereo}»", 8.5, "serifi",
               anchor="middle", fill=SOFT)
    return Box(x - max(tw_ / 2, 12), y, max(tw_, 24), 46)


def usecase(c: Canvas, cx: float, cy: float, text: str, *, code: str | None = None,
            size: float = 10.2, w: float | None = None) -> Box:
    lines = text.split("\n")
    width = w or max(tw(t, size) for t in lines) + 34
    ry = 13 + 6 * (len(lines) - 1) + (5 if code else 0)
    c.ellipse(cx, cy, width / 2, ry)
    total = len(lines) * (size + 2) + (9 if code else 0)
    ty = cy - total / 2 + size * 0.8
    if code:
        c.text(cx, ty - 1, code, 7.8, "mono", anchor="middle", fill=SOFT)
        ty += 9
    for t in lines:
        c.text(cx, ty, t, size, anchor="middle")
        ty += size + 2
    return Box(cx - width / 2, cy - ry, width, 2 * ry)


def ellipse_point(b: Box, toward: tuple[float, float]) -> tuple[float, float]:
    """Elips sınırında, merkezden toward yönündeki nokta."""
    rx, ry = b.w / 2, b.h / 2
    dx, dy = toward[0] - b.cx, toward[1] - b.cy
    if dx == dy == 0:
        return (b.cx, b.cy)
    t = 1 / math.sqrt((dx / rx) ** 2 + (dy / ry) ** 2)
    return (b.cx + dx * t, b.cy + dy * t)


# --- durum ve etkinlik ------------------------------------------------------------------------------


def state(c: Canvas, x: float, y: float, name: str, inner: list[str] = (), *,
          w: float | None = None, center_x: bool = True, fill: str = WHITE, size: float = 10.8,
          final_like: bool = False) -> Box:
    width = w or max([tw(name, size, "serifb")] + [tw(t, 8.8, "serifi") for t in inner]) + 22
    h = 24 + (len(inner) * 11 + 6 if inner else 0)
    if center_x:
        x -= width / 2
    c.rect(x, y, width, h, rx=9, fill=fill, sw=1.6 if final_like else 1)
    c.text(x + width / 2, y + 16, name, size, "serifb", anchor="middle")
    if inner:
        c.line([(x, y + 23), (x + width, y + 23)])
        ty = y + 34
        for t in inner:
            c.text(x + 8, ty, t, 8.8, "serifi", fill=SOFT)
            ty += 11
    return Box(x, y, width, h)


def start_node(c: Canvas, x: float, y: float) -> Box:
    c.circle(x, y, 6, fill=INK)
    return Box(x - 6, y - 6, 12, 12)


def final_node(c: Canvas, x: float, y: float) -> Box:
    c.circle(x, y, 8)
    c.circle(x, y, 4.5, fill=INK)
    return Box(x - 8, y - 8, 16, 16)


def decision(c: Canvas, x: float, y: float, r: float = 9, text: str | None = None) -> Box:
    c.path(f"M{x} {y - r} L{x + r} {y} L{x} {y + r} L{x - r} {y} Z", (x - r, y - r, x + r, y + r))
    if text:
        c.text(x + r + 4, y - r + 2, text, 8.8, "serifi", fill=SOFT)
    return Box(x - r, y - r, 2 * r, 2 * r)


def bar(c: Canvas, x: float, y: float, w: float, vertical: bool = False) -> Box:
    if vertical:
        c.rect(x - 2.5, y, 5, w, fill=INK, sw=0)
        return Box(x - 2.5, y, 5, w)
    c.rect(x, y - 2.5, w, 5, fill=INK, sw=0)
    return Box(x, y - 2.5, w, 5)


def action(c: Canvas, cx: float, y: float, text: str, *, w: float | None = None,
           size: float = 10.2) -> Box:
    lines = text.split("\n")
    return box(c, cx, y, lines, size=size, rx=10, w=w, center_x=True, pad=9)


def swimlanes(c: Canvas, x: float, y: float, widths: list[float], h: float,
              names: list[str]) -> list[float]:
    """Dikey kulvarlar; her kulvarın orta x'ini döner."""
    xs = []
    cur = x
    for w, n in zip(widths, names, strict=True):
        c.rect(cur, y, w, 22, fill=WASH, behind=True)
        c.rect(cur, y, w, h, fill="none", behind=True)
        c.text(cur + w / 2, y + 15, n, 10.5, "serifb", anchor="middle")
        xs.append(cur + w / 2)
        cur += w
    return xs


# --- sıralama diyagramı -----------------------------------------------------------------------------


def sequence(label: str, parts: list[tuple[str, str, str]], steps: list[tuple],
             *, min_gap: float = 70, top: float = 0, size: float = 9.8) -> Diagram:
    """parts: (anahtar, başlık, tür) tür: actor | obj | db | ext. Başlıkta "\\n" alt satır.
    steps: ("msg"|"ret"|"async", a, b, metin), ("self", a, metin), ("note", a, metin),
    ("frag", tür, koşul, a, b), ("else", koşul), ("end",), ("gap", h), ("on", a), ("off", a)."""
    c = Canvas()
    keys = [p[0] for p in parts]
    idx = {k: i for i, k in enumerate(keys)}
    head_w = []
    for _, title, kind in parts:
        lines = title.split("\n")
        head_w.append(max(tw(t, 10.2 if i == 0 else 8.6, "serifb" if i == 0 else "serifi")
                          for i, t in enumerate(lines)) + 16)
    n = len(parts)
    gaps = [max(min_gap, head_w[i] / 2 + head_w[i + 1] / 2 + 12) for i in range(n - 1)]
    for st in steps:
        if st[0] in ("msg", "ret", "async"):
            a, b = sorted((idx[st[1]], idx[st[2]]))
            need = tw(st[3], size) + 22
            have = sum(gaps[a:b])
            if have < need:
                extra = (need - have) / (b - a)
                for i in range(a, b):
                    gaps[i] += extra
        elif st[0] == "self":
            i = idx[st[1]]
            need = tw(st[2], size) + 34
            if i < n - 1 and gaps[i] < need:
                gaps[i] = need
    xs = [head_w[0] / 2]
    for g in gaps:
        xs.append(xs[-1] + g)
    head_h = max(42 if p[2] == "actor" else 22 + 10 * p[1].count("\n") for p in parts)
    y0 = top
    # başlıklar
    for (key, title, kind), x, hw in zip(parts, xs, head_w, strict=True):
        lines = title.split("\n")
        if kind == "actor":
            actor(c, x, y0 - 2, lines[0])
            continue
        hh = 22 + 10 * (len(lines) - 1)
        if kind == "db":
            db_icon(c, x - hw / 2, y0 + head_h - hh - 6, hw, hh + 6, lines[0],
                    lines[1] if len(lines) > 1 else "")
            continue
        c.rect(x - hw / 2, y0 + head_h - hh, hw, hh, fill=WASH if kind == "ext" else WHITE)
        c.text(x, y0 + head_h - hh + 14, lines[0], 10.2, "serifb", anchor="middle")
        for k, t in enumerate(lines[1:]):
            c.text(x, y0 + head_h - hh + 25 + k * 10, t, 8.6, "serifi", anchor="middle", fill=SOFT)
    y = y0 + head_h + (16 if any(p[2] == "actor" for p in parts) else 0) + 14
    frames: list[dict] = []
    active: dict[str, list[float]] = {}
    act_spans: list[tuple[float, float, float]] = []
    for st in steps:
        kind = st[0]
        if kind in ("msg", "ret", "async"):
            a, b = xs[idx[st[1]]], xs[idx[st[2]]]
            off_a = 4 if st[1] in active and active[st[1]] else 0
            off_b = 4 if st[2] in active and active[st[2]] else 0
            ax = a + (off_a if b > a else -off_a)
            bx = b - (off_b if b > a else -off_b)
            k_ = "serif" if kind != "ret" else "serifi"
            w_ = tw(st[3], size, k_)
            c.rect((a + b) / 2 - w_ / 2 - 2, y - 3 - size * 0.85, w_ + 4, size + 1, fill=WHITE,
                   stroke=WHITE, sw=0)
            c.text((a + b) / 2, y - 3, st[3], size, k_, anchor="middle", fill=INK if kind != "ret" else SOFT)
            edge(c, [(ax, y), (bx, y)], head="filled" if kind == "msg" else "open",
                 dash=kind == "ret")
            y += 22
        elif kind == "self":
            a = xs[idx[st[1]]]
            w_ = tw(st[2], size)
            c.rect(a + 29, y + 9 - size * 0.85, w_ + 4, size + 1, fill=WHITE, stroke=WHITE, sw=0)
            c.text(a + 31, y + 9, st[2], size)
            edge(c, [(a + 4, y), (a + 24, y), (a + 24, y + 12), (a + 4, y + 12)], head="filled")
            y += 30
        elif kind == "note":
            who = st[1] if isinstance(st[1], tuple) else (st[1],)
            xa = min(xs[idx[k]] for k in who)
            lines = st[2].split("\n")
            wn = max(tw(t, 9, "serifi") for t in lines) + 20
            xb = max(xs[idx[k]] for k in who)
            x = (xa + xb) / 2 - wn / 2 if len(who) > 1 else xa - wn / 2
            nb = note(c, x, y - 8, lines, size=9, w=wn)
            y = nb.b + 18
        elif kind == "frag":
            _, fkind, guard, a, b = st
            frames.append({"kind": fkind, "guard": guard, "a": idx[a], "b": idx[b], "y": y - 12,
                           "else": []})
            y += 16
        elif kind == "else":
            frames[-1]["else"].append((y - 6, st[1]))
            y += 14
        elif kind == "end":
            f = frames.pop()
            depth = len(frames)
            xa = xs[f["a"]] - head_w[f["a"]] / 2 - 6 + depth * 5
            xb = xs[f["b"]] + max(head_w[f["b"]] / 2, 30) + 6 - depth * 5
            c.rect(xa, f["y"], xb - xa, y - f["y"] - 6, fill="none", behind=True)
            tag = f["kind"]
            tw_ = tw(tag, 9, "monob") + 10
            c.path(f"M{xa} {f['y']} H{xa + tw_} V{f['y'] + 9} L{xa + tw_ - 5} {f['y'] + 14} H{xa} Z",
                   (xa, f["y"], xa + tw_, f["y"] + 14), fill=WASH)
            c.text(xa + 4, f["y"] + 10.5, tag, 9, "monob")

            def guard(x: float, y_: float, g: str) -> None:
                gw = tw(g, 9, "serifi")
                c.rect(x - 1, y_ - 8, gw + 2, 10.5, fill=WHITE, stroke=WHITE, sw=0)
                c.text(x, y_, g, 9, "serifi", fill=SOFT)

            guard(xa + tw_ + 5, f["y"] + 10.5, f["guard"])
            for ey, g in f["else"]:
                c.line([(xa, ey), (xb, ey)], dash="4 3")
                guard(xa + 6, ey + 10.5, g)
            y += 10
        elif kind == "gap":
            y += st[1]
        elif kind == "on":
            active.setdefault(st[1], []).append(y - 10)
        elif kind == "off":
            y_start = active[st[1]].pop()
            act_spans.append((xs[idx[st[1]]], y_start, y - 12))
    end = y + 2
    for (key, title, kind), x in zip(parts, xs, strict=True):
        start = y0 + head_h + (16 if kind == "actor" else 0)
        c.line([(x, start), (x, end)], dash="4 3", behind=True, stroke=SOFT)
    for x, a, b in act_spans:
        c.rect(x - 4, a, 8, b - a, fill=GREY, behind=True)
    return c.done(label)


# --- ER --------------------------------------------------------------------------------------------


def entity(c: Canvas, x: float, y: float, name: str, cols: list[tuple[str, str]], *,
           w: float | None = None, more: int = 0, ext: bool = False) -> Box:
    """ER varlığı: cols (işaret, ad) — işaret PK, FK, PK/FK, U ya da ''."""
    rows = [f"{k:<3} {n}" if k else f"    {n}" for k, n in cols]
    if more:
        rows.append(f"    … {more} sütun daha")
    width = w or max([tw(name, 10.5, "monob") + 16] + [tw(r, 8.8, "mono") + 14 for r in rows])
    h = 18 + len(rows) * 11.6 + 5
    c.rect(x, y, width, h, fill=WHITE, dash="4 2" if ext else None)
    c.rect(x, y, width, 18, fill=GREY if not ext else WHITE, dash="4 2" if ext else None)
    c.text(x + width / 2, y + 13, name, 10.5, "monob", anchor="middle")
    ty = y + 18 + 10.5
    for r, (k, _) in zip(rows, [*cols, ("", "")], strict=False):
        c.text(x + 7, ty, r, 8.8, "mono", fill=INK if k.startswith("PK") or k == "FK" else SOFT)
        ty += 11.6
    return Box(x, y, width, h)


# --- veri akışı (Gane–Sarson) ----------------------------------------------------------------------


def dfd_process(c: Canvas, x: float, y: float, num: str, text: str, *, w: float = 130) -> Box:
    lines = text.split("\n")
    h = 26 + len(lines) * 13
    c.rect(x, y, w, h, rx=8)
    c.line([(x, y + 16), (x + w, y + 16)])
    c.text(x + w / 2, y + 12, num, 9, "monob", anchor="middle")
    ty = y + 30
    for t in lines:
        c.text(x + w / 2, ty, t, 10.2, "serif", anchor="middle")
        ty += 13
    return Box(x, y, w, h)


def dfd_store(c: Canvas, x: float, y: float, code: str, text: str, *, w: float | None = None) -> Box:
    width = w or tw(text, 10, "serif") + tw(code, 9, "monob") + 30
    h = 20
    c.path(f"M{x + width} {y} H{x} V{y + h} H{x + width}", (x, y, x + width, y + h), fill=WHITE)
    c.line([(x + tw(code, 9, "monob") + 12, y), (x + tw(code, 9, "monob") + 12, y + h)])
    c.text(x + 5, y + 14, code, 9, "monob")
    c.text(x + tw(code, 9, "monob") + 18, y + 14, text, 10)
    return Box(x, y, width, h)


def dfd_entity(c: Canvas, x: float, y: float, text: str, *, w: float | None = None) -> Box:
    lines = text.split("\n")
    width = w or max(tw(t, 10.5, "serifb") for t in lines) + 22
    h = 12 + len(lines) * 13
    c.rect(x + 4, y + 4, width, h, fill=GREY, behind=False)
    c.rect(x, y, width, h, fill=WHITE)
    ty = y + 16
    for t in lines:
        c.text(x + width / 2, ty, t, 10.5, "serifb", anchor="middle")
        ty += 13
    return Box(x, y, width, h)
