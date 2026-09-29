"""Mahzen başlık kimliği (Gölge).

``HMAC-SHA256(sunucu_anahtarı, user_id ‖ ":" ‖ thread_id)`` değerinin ilk 8 hex karakteri.
Aynı başlıkta aynı kişiye aynı kimlik düşer; anahtarı bilmeyen biri iki başlıktaki
kimlikleri eşleştiremez. Sunucu anahtarı bildiği için anonimlik sunucuya karşı değildir.
"""

import hashlib
import hmac


def shade_id(key: bytes, user_id: str, thread_id: str) -> str:
    msg = f"{user_id}:{thread_id}".encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()[:8]


def vote_pseudonym(key: bytes, user_id: str, session_id: int) -> str:
    """Gizli oyun oturuma özel takma kimliği: ``HMAC(anahtar, "oy:" ‖ oturum ‖ ":" ‖ user_id)``,
    ilk 8 hex karakter. Aynı kişinin farklı oturumlardaki takma kimlikleri eşleştirilemez.

    "oy:" ön eki alan ayracıdır: anahtar Gölge kimlikleriyle ortaktır; ayraç olmasaydı #5 numaralı
    oturumdaki takma kimlik #5 numaralı Mahzen başlığındaki Gölge kimliğiyle aynı çıkabilirdi."""
    msg = f"oy:{session_id}:{user_id}".encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()[:8]
