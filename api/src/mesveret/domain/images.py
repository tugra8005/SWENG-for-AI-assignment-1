"""Yüklenen görselin denetimi ve iki sürümü: özgün (EXIF'siz JPEG) ve gazete baskısı (yarım ton).

Saf işlem: girdi baytlar, çıktı baytlar; veritabanı ve ağ yok. Aynı girdi her seferinde aynı
baytları üretir (tohum görsellerinin hash'i sabit kalır).
"""

from __future__ import annotations

import hashlib
import io
import math
import warnings
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

INK = (0x1B, 0x1A, 0x17)  # #1B1A17, gazete mürekkebi
PAPER = (0xF4, 0xEF, 0xE4)  # #F4EFE4, kâğıt
MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 40_000_000  # çözülmeden önce bakılır: küçük dosyada dev görsel (sıkıştırma bombası)
MAX_SIDE = 1600  # özgün sürümün uzun kenarı
PRINT_SIDE = 1200  # baskı sürümünün uzun kenarı
FORMATS = {"JPEG": "JPEG", "PNG": "PNG", "WEBP": "WebP"}
SCREEN_ANGLE = 45  # siyah mürekkebin klasik tram açısı
LEVELS = 16  # baskı sürümündeki ton sayısı (4 bitlik PNG)


class ImageRejected(ValueError):
    """Görsel kabul edilmedi; ileti kullanıcıya gösterilir."""


@dataclass(frozen=True)
class Processed:
    original: bytes  # JPEG, EXIF ve konum bilgisi yok
    print: bytes  # PNG, yarım ton
    width: int
    height: int
    sha256: str  # özgün sürümün hash'i (deftere yazılan)


def _open(data: bytes) -> Image.Image:
    if len(data) > MAX_BYTES:
        raise ImageRejected("Görsel en fazla 8 MB olabilir.")
    if not data:
        raise ImageRejected("Dosya boş.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            img = Image.open(io.BytesIO(data))
            if img.format not in FORMATS:
                raise ImageRejected("Yalnızca JPEG, PNG ve WebP görseller yüklenebilir.")
            if img.width * img.height > MAX_PIXELS:
                raise ImageRejected("Görsel çok büyük (en fazla 40 megapiksel).")
            img.seek(0)  # hareketli PNG/WebP: ilk kare
            img.load()
    except ImageRejected:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning,
            OSError, SyntaxError, ValueError) as exc:
        raise ImageRejected("Dosya bir görsel değil ya da okunamadı.") from exc
    return img


def _flatten(img: Image.Image) -> Image.Image:
    """Yönü düzeltir (EXIF Orientation), saydamlığı kâğıt rengine oturtur, RGB'ye çevirir."""
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        base = Image.new("RGBA", rgba.size, (*PAPER, 255))
        base.alpha_composite(rgba)
        return base.convert("RGB")
    return img.convert("RGB")


def _jpeg(img: Image.Image) -> bytes:
    out = io.BytesIO()
    # exif/icc_profile verilmez: kaydedilen dosyada EXIF (konum, cihaz) bulunmaz.
    img.save(out, format="JPEG", quality=85, optimize=True, progressive=True)
    return out.getvalue()


def halftone(img: Image.Image, *, side: int = PRINT_SIDE, cell: int | None = None) -> bytes:
    """45° nokta ızgarasıyla tek renk baskı: her hücrede noktanın alanı o bölgenin koyuluğuyla
    orantılıdır. Mürekkep #1B1A17, kâğıt #F4EFE4; çıktı 16 tonlu PNG."""
    gray = img.convert("L")
    gray.thumbnail((side, side), Image.Resampling.LANCZOS)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    w, h = gray.size
    cell = cell or max(4, round(max(w, h) / 170))
    ss = 3  # süper örnekleme: noktalar büyük çizilip küçültülünce kenarları yumuşar

    rotated = gray.rotate(SCREEN_ANGLE, expand=True, fillcolor=255,
                          resample=Image.Resampling.BICUBIC)
    rw, rh = rotated.size
    gw, gh = math.ceil(rw / cell), math.ceil(rh / cell)
    padded = Image.new("L", (gw * cell, gh * cell), 255)
    padded.paste(rotated, ((gw * cell - rw) // 2, (gh * cell - rh) // 2))
    tones = padded.resize((gw, gh), Image.Resampling.BOX).tobytes()  # L: bir bayt bir ton

    mask = Image.new("L", (gw * cell * ss, gh * cell * ss), 0)
    draw = ImageDraw.Draw(mask)
    # Tam koyu hücrede nokta komşularına taşar ama köşegenlerde kâğıt kalır (ters nokta deseni).
    full = cell * ss * math.sqrt(2) / 2 * 0.9
    for gy in range(gh):
        cy = (gy + 0.5) * cell * ss
        for gx in range(gw):
            dark = 1 - tones[gy * gw + gx] / 255
            if dark < 0.03:
                continue
            r = full * math.sqrt(dark)
            cx = (gx + 0.5) * cell * ss
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    mask = mask.resize((gw * cell, gh * cell), Image.Resampling.LANCZOS)
    mask = mask.rotate(-SCREEN_ANGLE, expand=True, resample=Image.Resampling.BICUBIC)
    mw, mh = mask.size
    left, top = (mw - w) // 2, (mh - h) // 2
    mask = mask.crop((left, top, left + w, top + h))

    # Mürekkep örtüsü 0–255 → 16 ton; palet kâğıttan mürekkebe doğrusal.
    q = mask.point([round(v * (LEVELS - 1) / 255) for v in range(256)])
    out_img = Image.frombytes("P", q.size, q.tobytes())
    palette: list[int] = []
    for i in range(LEVELS):
        t = i / (LEVELS - 1)
        palette += [round(PAPER[c] + (INK[c] - PAPER[c]) * t) for c in range(3)]
    out_img.putpalette(palette)
    out = io.BytesIO()
    out_img.save(out, format="PNG", optimize=True, bits=4)
    return out.getvalue()


def process(data: bytes) -> Processed:
    img = _flatten(_open(data))
    img.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    original = _jpeg(img)
    return Processed(
        original=original, print=halftone(img), width=img.width, height=img.height,
        sha256=hashlib.sha256(original).hexdigest(),
    )


def check_alt(text: str) -> str:
    """Alt metin zorunludur: görmeyen okur için görselin ne gösterdiği."""
    text = " ".join((text or "").split())
    if len(text) < 3:
        raise ImageRejected("Görselin ne gösterdiğini bir cümleyle yazın (alt metin zorunlu).")
    if len(text) > 300:
        raise ImageRejected("Alt metin en fazla 300 karakter olabilir.")
    return text
