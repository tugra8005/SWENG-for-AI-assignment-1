"""Muhataplar: her konu önerisi bir yere iletilmek için açılır.

Muhatap türleri:

- ``TAKVIM``: Meşveret Takvimi. Kabul edilen konu bir etkinlik olur (tarih, yer, katılım).
- ``KURUM``: belediye ya da bakanlık. Kabul edilen konu kuruma dilekçe olarak gider; kapanış
  Kararı da karar bildirimi olarak aynı kuruma iletilir.
- ``IC``: Meşveret'in kendisi. Yönetmelik, silme ve düzenleme önerileri buraya gider; konu
  önerisi iç düzene yazamaz (iç düzen yönetmelik önerisiyle değişir).

R9 (R2'nin muhatap karşılığı): bir kapsam yalnızca yetki alanındaki muhataba yazar. Şehir
kapsamı kendi belediyesine, Genel kapsam ulusal kurumlara ve belediyelere, ilgi ve yaş kapsamları
ulusal kurumlara yazar; takvime her kapsam yazabilir.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from mesveret.domain.ontology import ScopeInfo
from mesveret.domain.scopes import ScopeSubtype, ScopeType


class AddresseeKind(StrEnum):
    TAKVIM = "TAKVIM"
    KURUM = "KURUM"
    IC = "IC"


@dataclass(frozen=True)
class Addressee:
    id: str
    kind: AddresseeKind
    name: str  # dilekçenin "Sayın …" satırı ve künye
    short: str  # manşetlerde
    level: str  # takvim | ic | yerel | ulusal
    city_scope_id: str | None = None  # belediye: şehrin kapsamı


# 30 büyükşehir; diğer illerde il belediyesi.
METROPOLITAN = frozenset({
    "Adana", "Ankara", "Antalya", "Aydın", "Balıkesir", "Bursa", "Denizli", "Diyarbakır",
    "Erzurum", "Eskişehir", "Gaziantep", "Hatay", "İstanbul", "İzmir", "Kahramanmaraş", "Kayseri",
    "Kocaeli", "Konya", "Malatya", "Manisa", "Mardin", "Mersin", "Muğla", "Ordu", "Sakarya",
    "Samsun", "Şanlıurfa", "Tekirdağ", "Trabzon", "Van",
})

TAKVIM = Addressee("takvim", AddresseeKind.TAKVIM, "Meşveret Takvimi", "takvim", "takvim")
MESVERET = Addressee("mesveret", AddresseeKind.IC, "Meşveret (iç düzen)", "Meşveret", "ic")
ALL_MUNICIPALITIES = Addressee(
    "belediyeler", AddresseeKind.KURUM, "Üye şehirlerin belediyeleri", "belediyeler", "yerel")
NATIONAL = (
    Addressee("bakanlik:ulastirma", AddresseeKind.KURUM, "T.C. Ulaştırma ve Altyapı Bakanlığı",
              "Ulaştırma Bakanlığı", "ulusal"),
    Addressee("bakanlik:kultur", AddresseeKind.KURUM, "T.C. Kültür ve Turizm Bakanlığı",
              "Kültür ve Turizm Bakanlığı", "ulusal"),
    Addressee("bakanlik:cevre", AddresseeKind.KURUM,
              "T.C. Çevre, Şehircilik ve İklim Değişikliği Bakanlığı", "Çevre Bakanlığı", "ulusal"),
)


def municipality(city: ScopeInfo) -> Addressee:
    """Şehir kapsamının belediyesi: ``sehir:istanbul`` → ``belediye:istanbul``."""
    slug = city.id.split(":", 1)[1]
    name = city.value or city.name
    suffix = "Büyükşehir Belediyesi" if name in METROPOLITAN else "Belediyesi"
    return Addressee(f"belediye:{slug}", AddresseeKind.KURUM, f"{name} {suffix}",
                     f"{name} Belediyesi", "yerel", city_scope_id=city.id)


def catalog(cities: Iterable[ScopeInfo]) -> list[Addressee]:
    """Konu önerisinin seçebileceği muhataplar (iç düzen hariç), formdaki sırayla."""
    towns = sorted((municipality(c) for c in cities), key=lambda a: a.name)
    return [TAKVIM, *towns, ALL_MUNICIPALITIES, *NATIONAL]


def lookup(addressee_id: str | None, cities: Iterable[ScopeInfo]) -> Addressee | None:
    if addressee_id == MESVERET.id:
        return MESVERET
    return next((a for a in catalog(cities) if a.id == addressee_id), None)


def recipients(a: Addressee, cities: Iterable[ScopeInfo]) -> list[Addressee]:
    """Dilekçenin gideceği kurumlar: "belediyeler" bütün şehir belediyelerine açılır."""
    if a.id == ALL_MUNICIPALITIES.id:
        return sorted((municipality(c) for c in cities), key=lambda m: m.name)
    return [a]


def jurisdiction_refusal(scope: ScopeInfo, a: Addressee) -> str | None:
    """R9: kapsam bu muhataba yazabiliyorsa ``None``, yazamıyorsa Türkçe gerekçe."""
    if a.kind is AddresseeKind.TAKVIM:
        return None
    if a.kind is AddresseeKind.IC:
        return ("Konu önerisi Meşveret'in iç düzenine yazılamaz: iç düzen yönetmelik önerisiyle "
                "değişir. Takvimi ya da bir kurumu seçin.")
    general = scope.type is ScopeType.GENEL
    city = scope.subtype is ScopeSubtype.SEHIR
    if a.level == "ulusal":
        if city:
            return (f"{scope.name} kapsamı ulusal kurumlara yazamaz ({a.name}). Ulusal kurumlara "
                    "Genel kapsam ya da ilgi ve yaş kapsamları yazar; şehir kapsamı kendi "
                    "belediyesine yazar.")
        return None
    # yerel: belediyeler
    if general:
        return None
    if a.id == ALL_MUNICIPALITIES.id:
        return ("Bütün belediyelere yalnızca Genel kapsam yazabilir; bir şehrin kapsamı yalnızca "
                "kendi belediyesine yazar.")
    if city and a.city_scope_id == scope.id:
        return None
    if city:
        return (f"{scope.name} kapsamı yalnızca kendi belediyesine yazabilir; {a.name} bu "
                "kapsamın yetki alanında değil.")
    return (f"{scope.name} bir şehrin sakinleri değil; belediyeye yalnızca o şehrin kapsamı ya da "
            "Genel kapsam yazabilir. Takvimi ya da ulusal bir kurumu seçin.")
