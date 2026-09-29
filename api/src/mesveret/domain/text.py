"""Türkçe metin normalizasyonu (Hâtif'in anahtar kelime eşlemesi ve hedef anahtarları için)."""

import re
from collections.abc import Sequence

_APOSTROPHES = re.compile(r"['’`]")
_WORD = re.compile(r"\w+", re.UNICODE)


def turkish_lower(text: str) -> str:
    return text.replace("İ", "i").replace("I", "ı").lower()


def normalize(text: str) -> str:
    """Küçük harf (Türkçe kurallarıyla), kesme işaretleri kaldırılır, boşluklar sadeleşir."""
    return " ".join(tokens(text))


def tokens(text: str) -> list[str]:
    return _WORD.findall(_APOSTROPHES.sub("", turkish_lower(text)))


def phrase_in(stems: Sequence[str], words: Sequence[str]) -> bool:
    """``stems`` ardışık kelimelerin başlarıyla eşleşiyor mu (ek almış kelimeler için)."""
    n = len(stems)
    if n == 0:
        return False
    for i in range(len(words) - n + 1):
        if all(words[i + j].startswith(stems[j]) for j in range(n)):
            return True
    return False


def contains_words(words: Sequence[str], part: Sequence[str]) -> bool:
    """``part`` kelimeleri ``words`` içinde bütün kelimeler olarak ve art arda geçiyor mu."""
    n = len(part)
    return n > 0 and any(list(words[i:i + n]) == list(part) for i in range(len(words) - n + 1))


def count_stem_hits(stems: Sequence[str], words: Sequence[str]) -> int:
    return sum(1 for w in words if any(w.startswith(s) for s in stems))


_BACK = {"a": "ın", "ı": "ın", "o": "un", "u": "un"}
_FRONT = {"e": "in", "i": "in", "ö": "ün", "ü": "ün"}
_VOWELS = set(_BACK) | set(_FRONT)


def genitive(phrase: str) -> str:
    """Tamlayan eki (ilgi hâli): "Etkinlik bütçesi" → "Etkinlik bütçesinin".

    Son kelimenin son ünlüsüne göre büyük ünlü uyumu uygulanır; ünlüyle bitenlere "n"
    kaynaştırması eklenir. Ünsüz yumuşaması (kitap → kitabın) yapılmaz.
    """
    word = turkish_lower(phrase.split()[-1]) if phrase.strip() else ""
    last = next((c for c in reversed(word) if c in _VOWELS), "e")
    suffix = {**_BACK, **_FRONT}[last]
    if word and word[-1] in _VOWELS:
        suffix = "n" + suffix
    return phrase + suffix


def decimal_tr(value: float, digits: int = 1) -> str:
    """Türkçe ondalık yazımı: 61.538 → "61,5"."""
    return f"{value:.{digits}f}".replace(".", ",")


def percent_tr(value: float, digits: int = 1, *, compact: bool = False) -> str:
    """Türkçe yüzde; işaret yüzde işaretinin önünde: 33.33 → "%33,3", -50 → "-%50,0".

    ``compact`` tam sayıda ondalığı atar: 50 → "%50", 66.67 → "%66,7". Bütün yüzdeler buradan geçer
    (istemcide karşılığı ``lib/format.ts``)."""
    text = decimal_tr(abs(value), digits)
    if compact and text.endswith("," + "0" * digits):
        text = text[: -(digits + 1)]
    sign = "-" if round(value, digits) < 0 else ""
    return f"{sign}%{text}"


_VOICELESS = set("fstkçşhp")


def locative_name(name: str) -> str:
    """Özel adın bulunma hâli, kesme işaretiyle: Genel → Genel'de, İstanbul → İstanbul'da,
    İzmir → İzmir'de. Son ünlü kalın ise -da, ince ise -de; sert ünsüzle bitiyorsa t ile."""
    word = turkish_lower(name.split()[-1]) if name.strip() else ""
    last = next((c for c in reversed(word) if c in _VOWELS), "e")
    vowel = "a" if last in _BACK else "e"
    cons = "t" if word and word[-1] in _VOICELESS else "d"
    return f"{name}'{cons}{vowel}"
