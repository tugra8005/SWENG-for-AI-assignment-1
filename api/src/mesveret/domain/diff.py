"""Kelime bazlı fark (sürüm geçmişi ve düzenleme önerileri için)."""

import re
from difflib import SequenceMatcher

_TOKEN = re.compile(r"\s+|\w+|[^\w\s]", re.UNICODE)


def word_diff(old: str, new: str) -> list[tuple[str, str]]:
    """``[(işlem, metin)]``; işlem ``equal``, ``delete`` ya da ``insert``."""
    a, b = _TOKEN.findall(old), _TOKEN.findall(new)
    chunks: list[tuple[str, str]] = []

    def push(op: str, parts: list[str]) -> None:
        text = "".join(parts)
        if not text:
            return
        if chunks and chunks[-1][0] == op:
            chunks[-1] = (op, chunks[-1][1] + text)
        else:
            chunks.append((op, text))

    for tag, i1, i2, j1, j2 in SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag == "equal":
            push("equal", a[i1:i2])
        else:
            push("delete", a[i1:i2])
            push("insert", b[j1:j2])
    return chunks
