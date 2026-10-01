import io

import pytest
from PIL import Image, ImageDraw

from mesveret.domain import images


def _photo(size=(900, 600), fmt="JPEG", **save) -> bytes:
    img = Image.new("RGB", size, (200, 180, 150))
    d = ImageDraw.Draw(img)
    d.ellipse((100, 100, 500, 500), fill=(40, 30, 20))
    d.rectangle((550, 50, 850, 300), fill=(120, 140, 90))
    buf = io.BytesIO()
    img.save(buf, format=fmt, **save)
    return buf.getvalue()


def _exif_with_gps(orientation: int = 1) -> Image.Exif:
    exif = Image.Exif()
    exif[0x0112] = orientation  # Orientation
    exif[0x010F] = "Telefon A.Ş."  # Make
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2] = "N", (41.0, 2.0, 30.0)  # 41°02'30" K (İstanbul)
    gps[3], gps[4] = "E", (28.0, 58.0, 0.0)
    return exif


def test_processing_is_deterministic():
    data = _photo()
    a, b = images.process(data), images.process(data)
    assert a.original == b.original and a.print == b.print and a.sha256 == b.sha256
    assert len(a.sha256) == 64


def test_exif_and_location_are_stripped():
    data = _photo(exif=_exif_with_gps())
    assert Image.open(io.BytesIO(data)).getexif().get_ifd(0x8825)  # girdide konum var
    out = images.process(data)
    for blob in (out.original, out.print):
        img = Image.open(io.BytesIO(blob))
        assert not img.getexif()
        assert "exif" not in img.info and "icc_profile" not in img.info


def test_exif_orientation_is_applied_before_stripping():
    # Orientation 6: telefon dik tutulmuş; görüntülendiğinde 90° döndürülmeli.
    out = images.process(_photo(size=(900, 600), exif=_exif_with_gps(orientation=6)))
    assert (out.width, out.height) == (600, 900)


def test_long_side_is_limited_and_aspect_kept():
    out = images.process(_photo(size=(4000, 1000), fmt="PNG"))
    assert (out.width, out.height) == (1600, 400)
    baski = Image.open(io.BytesIO(out.print))
    assert baski.size == (1200, 300)


def test_print_version_is_a_sixteen_tone_ink_on_paper_png():
    out = images.process(_photo())
    baski = Image.open(io.BytesIO(out.print))
    assert baski.format == "PNG" and baski.mode == "P"
    colors = {c for _, c in baski.convert("RGB").getcolors(maxcolors=256) or []}
    assert images.PAPER in colors and images.INK in colors
    assert len(colors) <= images.LEVELS


def test_transparent_png_is_set_on_paper():
    img = Image.new("RGBA", (300, 200), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle((0, 0, 100, 100), fill=(0, 0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    out = images.process(buf.getvalue())
    jpg = Image.open(io.BytesIO(out.original)).convert("RGB")
    pixel = jpg.getpixel((250, 150))
    assert isinstance(pixel, tuple)
    assert all(abs(c - p) < 6 for c, p in zip(pixel, images.PAPER, strict=True))


@pytest.mark.parametrize("data, message", [
    (b"", "Dosya boş."),
    (b"merhaba, bu bir metin", "Dosya bir görsel değil ya da okunamadı."),
    (_photo(fmt="GIF"), "Yalnızca JPEG, PNG ve WebP görseller yüklenebilir."),
    (_photo(fmt="BMP"), "Yalnızca JPEG, PNG ve WebP görseller yüklenebilir."),
    (b"\xff\xd8\xff" + b"0" * 64, "Dosya bir görsel değil ya da okunamadı."),
])
def test_rejected_files(data, message):
    with pytest.raises(images.ImageRejected, match=message):
        images.process(data)


def test_size_and_pixel_limits():
    with pytest.raises(images.ImageRejected, match="en fazla 8 MB"):
        images.process(b"\0" * (images.MAX_BYTES + 1))
    # Küçük dosyada dev boyut (sıkıştırma bombası): çözülmeden reddedilir.
    buf = io.BytesIO()
    Image.new("L", (8000, 6000), 255).save(buf, format="PNG")
    assert len(buf.getvalue()) < 1_000_000
    with pytest.raises(images.ImageRejected, match="40 megapiksel"):
        images.process(buf.getvalue())


def test_webp_is_accepted():
    out = images.process(_photo(fmt="WEBP"))
    assert Image.open(io.BytesIO(out.original)).format == "JPEG"


@pytest.mark.parametrize("alt, ok", [
    ("", False), ("  a ", False), ("Salonda film gösterimi", True), ("x" * 301, False),
])
def test_alt_text_is_required(alt, ok):
    if ok:
        assert images.check_alt(alt) == alt
    else:
        with pytest.raises(images.ImageRejected):
            images.check_alt(alt)


def test_alt_text_whitespace_is_collapsed():
    assert images.check_alt("  Kordon'da\n  bisiklet   yolu ") == "Kordon'da bisiklet yolu"
