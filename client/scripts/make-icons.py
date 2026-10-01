"""Uygulama simgelerini üretir: kâğıt zemin üzerinde bordo mühür, ortada Newsreader "M".

    python3 scripts/make-icons.py

Çıktılar ``assets/images/`` altındadır: icon.png (1024), favicon.png (48, sade disk),
splash-icon.png, seal-mark.png (arayüz süsü), android-icon-foreground/background (512) ve
android-icon-monochrome (432).
Pillow ve projenin kendi yazı tipleri (@expo-google-fonts) kullanılır.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "images"
FONTS = ROOT / "node_modules" / "@expo-google-fonts"
SERIF = FONTS / "newsreader" / "800ExtraBold" / "Newsreader_800ExtraBold.ttf"
MONO = FONTS / "ibm-plex-mono" / "700Bold" / "IBMPlexMono_700Bold.ttf"

PAPER = (244, 239, 228, 255)  # #F4EFE4
SEAL = (122, 30, 43, 255)  # #7A1E2B
RING_TEXT = "MEŞVERET · RESMÎ KAYIT · OYLAMAYLA YÖNETİLİR · "
SS = 4  # süper örnekleme: büyük çizip küçültünce kenarlar yumuşar


def seal(size: int, color=SEAL, ring_text: bool = True, tilt: float = -7.0, ink: bool = True) -> Image.Image:
    """Şeffaf zemin üzerinde mühür (``size`` × ``size``)."""
    n = size * SS
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = n / 2
    r_out, r_in = n * 0.47, n * 0.36

    def ring(r: float, w: float) -> None:
        d.ellipse((c - r, c - r, c + r, c + r), outline=color, width=int(w))

    ring(r_out, n * 0.028)
    ring(r_out - n * 0.04, n * 0.008)
    ring(r_in, n * 0.012)

    if ring_text:
        font = ImageFont.truetype(str(MONO), int(n * 0.052))
        r_text = (r_out - n * 0.04 + r_in) / 2
        chars = list(RING_TEXT)
        step = 360 / len(chars)
        for i, ch in enumerate(chars):
            angle = -90 + i * step  # üstten başlar, saat yönünde
            glyph = Image.new("RGBA", (int(n * 0.09), int(n * 0.09)), (0, 0, 0, 0))
            gd = ImageDraw.Draw(glyph)
            gd.text((glyph.width / 2, glyph.height / 2), ch, font=font, fill=color, anchor="mm")
            glyph = glyph.rotate(-(angle + 90), resample=Image.Resampling.BICUBIC)
            x = c + r_text * math.cos(math.radians(angle)) - glyph.width / 2
            y = c + r_text * math.sin(math.radians(angle)) - glyph.height / 2
            img.alpha_composite(glyph, (int(x), int(y)))

    m_font = ImageFont.truetype(str(SERIF), int(n * (0.42 if ring_text else 0.62)))
    d.text((c, c + n * 0.015), "M", font=m_font, fill=color, anchor="mm")

    if ink:
        # Islak mühür: mürekkep yer yer tutmamış gibi ince benekler (deterministik).
        rnd = random.Random(1923)
        mask = Image.new("L", (n, n), 255)
        md = ImageDraw.Draw(mask)
        for _ in range(int(n * 0.6)):
            x, y = rnd.uniform(0, n), rnd.uniform(0, n)
            rad = rnd.uniform(n * 0.001, n * 0.004)
            md.ellipse((x - rad, y - rad, x + rad, y + rad), fill=rnd.randint(90, 200))
        mask = mask.filter(ImageFilter.GaussianBlur(n * 0.0015))
        alpha = ImageChops.multiply(img.getchannel("A"), mask)
        img.putalpha(alpha)

    img = img.rotate(tilt, resample=Image.Resampling.BICUBIC)
    return img.resize((size, size), Image.Resampling.LANCZOS)


def paper(size: int) -> Image.Image:
    base = Image.new("RGBA", (size, size), PAPER)
    grain_path = OUT / "paper-grain.png"
    if grain_path.exists():
        grain = Image.open(grain_path).convert("RGBA")
        tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        for x in range(0, size, grain.width):
            for y in range(0, size, grain.height):
                tile.alpha_composite(grain, (x, y))
        base.alpha_composite(tile)
    return base


def favicon(size: int = 48) -> Image.Image:
    """Küçük boyutta halka yazısı okunmaz: bordo disk, kâğıt rengi M."""
    n = size * SS
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((n * 0.03, n * 0.03, n * 0.97, n * 0.97), fill=SEAL)
    d.ellipse((n * 0.11, n * 0.11, n * 0.89, n * 0.89), outline=PAPER, width=int(n * 0.03))
    font = ImageFont.truetype(str(SERIF), int(n * 0.6))
    d.text((n / 2, n / 2 + n * 0.02), "M", font=font, fill=PAPER, anchor="mm")
    return img.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    icon = paper(1024)
    s = seal(860)
    icon.alpha_composite(s, ((1024 - 860) // 2, (1024 - 860) // 2))
    icon.save(OUT / "icon.png")

    favicon(48).save(OUT / "favicon.png")

    seal(456).save(OUT / "splash-icon.png")
    # Arayüzde künye ve alt bilgi süsü (şeffaf, küçük boyutta çizilir).
    seal(256).save(OUT / "seal-mark.png")

    # Android uyarlanabilir simge: güvenli alan ortadaki ~%66; mühür onun içinde kalır.
    fg = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    fs = seal(300)
    fg.alpha_composite(fs, (106, 106))
    fg.save(OUT / "android-icon-foreground.png")
    paper(512).save(OUT / "android-icon-background.png")
    mono = Image.new("RGBA", (432, 432), (0, 0, 0, 0))
    ms = seal(250, color=(255, 255, 255, 255), ink=False)
    mono.alpha_composite(ms, (91, 91))
    mono.save(OUT / "android-icon-monochrome.png")
    print("simgeler yazıldı:", OUT)


if __name__ == "__main__":
    main()
