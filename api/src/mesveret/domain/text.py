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


def count_stem_hits(stems: Sequence[str], words: Sequence[str]) -> int:
    return sum(1 for w in words if any(w.startswith(s) for s in stems))
