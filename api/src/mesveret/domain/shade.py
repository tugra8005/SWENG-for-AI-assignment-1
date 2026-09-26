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
