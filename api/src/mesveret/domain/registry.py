"""Kayıt defteri (Registry) deseni: Factory Method'un genişletilebilir hâli.

Yeni bir bileşen (öneri türü, baskın tespit yöntemi…) kendini bir dekoratörle kaydeder; onu
kullanan kod merkezi bir sözlüğü ya da ``if/elif`` zincirini elle güncellemez (Açık/Kapalı
ilkesi). ``create`` fabrika metodudur: hangi somut sınıfın örnekleneceğine anahtar karar verir.

    KINDS = Registry[ProposalKind]("öneri türleri")

    @KINDS.register("KONU")
    class TopicKind(ProposalKind): ...

    KINDS.create("KONU")
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any


class Registry[T]:
    def __init__(self, name: str) -> None:
        self.name = name
        self._items: dict[str, type[T]] = {}

    def register(self, key: str) -> Callable[[type[T]], type[T]]:
        def wrap(cls: type[T]) -> type[T]:
            if key in self._items:
                raise KeyError(f"{key} zaten kayıtlı ({self.name}).")
            self._items[key] = cls
            return cls

        return wrap

    def get(self, key: str) -> type[T]:
        try:
            return self._items[key]
        except KeyError:
            raise KeyError(
                f"Bilinmeyen {self.name} anahtarı: {key}. Seçenekler: {', '.join(self._items)}"
            ) from None

    def create(self, key: str, **kwargs: Any) -> T:
        return self.get(key)(**kwargs)

    def __contains__(self, key: object) -> bool:
        return key in self._items

    def __iter__(self) -> Iterator[str]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)
