"""Mühürlü oy (commit-reveal).

Oy anında deftere yalnızca ``sha256(kanonik_json(oy) ‖ tuz)`` yazılır. Tuz ve seçim
pencere boyunca sunucuda durur; pencere kapanınca ikisi de deftere açılır ve herkes
commit'i yeniden hesaplayabilir.
"""

import hashlib
import hmac
import json
import secrets
from typing import Any


def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def new_salt() -> str:
    return secrets.token_hex(32)


def derived_salt(key: bytes, *parts: object) -> str:
    """Geliştirme ortamı için tekrarlanabilir tuz: sunucu anahtarından HMAC ile türetilir.

    Anahtarı bilmeyen tuzu tahmin edemez; ama aynı girdiyle hep aynı tuz çıkar, böylece demo iki
    çalıştırmada aynı defteri üretir. Üretimde ``new_salt`` kullanılır."""
    msg = "tuz:" + ":".join(str(p) for p in parts)
    return hmac.new(key, msg.encode(), hashlib.sha256).hexdigest()


def make_commit(vote: Any, salt: str) -> str:
    return hashlib.sha256(canonical_json(vote) + salt.encode()).hexdigest()


def verify_commit(commit: str, vote: Any, salt: str) -> bool:
    return hmac.compare_digest(commit, make_commit(vote, salt))
