"""Yönetmelik = veri.

Tüm eşikler ve süreler ``YonetmelikMaddesi`` düğümlerinde durur; bu modül yalnızca
varsayılanları, değer şemalarını ve tipli okuyucuları tanımlar. İş kodu eşik ya da
süre sabiti içermez, her zaman bir ``Regulation`` örneğinden okur.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from fractions import Fraction
from typing import Any


class RegulationError(ValueError):
    """Geçersiz madde değeri; mesaj kullanıcıya gösterilir."""


@dataclass(frozen=True)
class Ratio:
    value: Fraction
    comparison: str  # ">" ya da ">="

    def passes(self, part: int | Fraction, whole: int | Fraction) -> bool:
        if whole <= 0:
            return False
        share = Fraction(part) / Fraction(whole)
        return share > self.value if self.comparison == ">" else share >= self.value

    def describe(self) -> str:
        op = "fazlası" if self.comparison == ">" else "en az"
        pct = f"%{float(self.value) * 100:.4g}"
        return f"{self.value} ({pct}) — {op}" if self.comparison == ">" else f"{op} {self.value} ({pct})"


@dataclass(frozen=True)
class DecisionHourSpec:
    weekday: int  # Pazartesi = 0 … Pazar = 6
    hour: int
    minute: int
    tz: str
    window: timedelta


@dataclass(frozen=True)
class Article:
    key: str
    kind: str
    default: dict[str, Any]
    description: str
    min_ratio: Fraction = Fraction(0)
    max_ratio: Fraction = Fraction(1)


WEEKDAYS = ["PAZARTESI", "SALI", "CARSAMBA", "PERSEMBE", "CUMA", "CUMARTESI", "PAZAR"]


def _articles() -> dict[str, Article]:
    items = [
        Article("sessiz_onay_suresi", "sure", {"saat": 24},
                "Hızlı şeritteki önerinin itiraza açık kalma süresi."),
        Article("itiraz_esigi", "itiraz", {"min": 3, "oran": "1/20", "aktiflik_gun": 30},
                "Hızlı şerit önerisini yavaş şeride aktaran itiraz sayısı: "
                "max(min, kapsamdaki aktif üyelerin oranı). Aktif: son aktiflik_gun günde giriş."),
        Article("basit_cogunluk", "oran", {"oran": "1/2", "karsilastirma": ">"},
                "Kullanılan oylar içinde kabul için gereken pay.", Fraction(1, 2)),
        Article("yonetmelik_esigi", "oran", {"oran": "2/3", "karsilastirma": ">="},
                "Yönetmelik değişikliği için kullanılan oylar içinde gereken pay. "
                "Bu maddenin kendisi de bu eşikle değişir.", Fraction(1, 2)),
        Article("red_bekleme", "sure", {"gun": 30},
                "Oylamayla reddedilen hedefe yeni öneri açılamayan süre."),
        Article("musavir_esigi", "tamsayi", {"deger": 5},
                "Bir alanda Müşavir etiketi için gereken doğrudan havale sayısı."),
        Article("ilgi_bekleme", "sure", {"gun": 14},
                "İlgi kapsamına katıldıktan sonra oy hakkının doğması için geçen süre."),
        Article("adres_bekleme", "sure", {"gun": 90},
                "Adres değişikliğinden sonra yeni şehirde oy hakkının doğması için geçen süre."),
        Article("karar_saati", "karar_saati",
                {"gun": "PAZAR", "saat": "20:00", "tz": "Europe/Istanbul", "pencere_dakika": 60},
                "Haftalık planlı oylama oturumu ve oy penceresinin uzunluğu."),
        Article("kapanis_rakip_suresi", "sure", {"saat": 48},
                "Kapanış önerisine rakip karar metni eklenebilen süre."),
        Article("yeniden_acma", "sure", {"gun": 90},
                "Karara bağlanmış konunun yeniden açılabilmesi için geçmesi gereken süre."),
        Article("mahzen_kapasite", "tamsayi", {"deger": 100},
                "Mahzen'de yaşayan en fazla başlık sayısı; aşılınca en alttaki kalıcı silinir."),
        Article("mahzen_ust_sinir", "tamsayi", {"deger": 300},
                "Bu yanıt sayısına ulaşan Mahzen başlığı artık yükselemez."),
        Article("mahzen_ifsa_esigi", "oran", {"oran": "1/2", "karsilastirma": ">"},
                "İfşa oylamasının geçmesi için EVET sayısının seçmen listesine oranı.",
                Fraction(0)),
        Article("baskin_yeni_uye_suresi", "sure", {"gun": 7},
                "Anlık görüntüden en fazla bu kadar önce katılan seçmen baskın adayıdır."),
        Article("baskin_katilim_araligi", "sure", {"saat": 24},
                "Baskın kümesindeki katılım anlarının yayılabileceği en uzun aralık."),
        Article("baskin_min_kume", "tamsayi", {"deger": 4},
                "Baskın olarak işaretlenecek en küçük küme boyutu."),
        Article("baskin_yogunluk_esigi", "oran", {"oran": "1/2", "karsilastirma": ">="},
                "Baskın kümesinde gereken kenar yoğunluğu (kenar / olası kenar)."),
        Article("baskin_min_agirlik", "sayi", {"deger": 1},
                "Kümelemede kenar sayılması için gereken en düşük etkileşim ağırlığı."),
        Article("etkilesim_agirliklari", "agirliklar",
                {"yanit": 1, "havale": 2, "yakin_kayit": 1, "yakin_kayit_dk": 60,
                 "ortak_baslik": 0.5, "ortak_baslik_dk": 30},
                "İlişki grafındaki sinyallerin ağırlıkları ve zaman pencereleri."),
    ]
    return {a.key: a for a in items}


DEFAULT_ARTICLES: dict[str, Article] = _articles()


# --- doğrulama ---------------------------------------------------------------------------


def _parse_fraction(text: Any) -> Fraction:
    if not isinstance(text, str):
        raise RegulationError("Oran 'pay/payda' biçiminde bir metin olmalı (ör. \"2/3\").")
    try:
        return Fraction(text.strip())
    except (ValueError, ZeroDivisionError) as exc:
        raise RegulationError(f"Oran okunamadı: {text!r}.") from exc


def _positive_number(value: Any, label: str, *, integer: bool = False) -> int | float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise RegulationError(f"{label} bir sayı olmalı.")
    if integer and not float(value).is_integer():
        raise RegulationError(f"{label} bir tam sayı olmalı.")
    if value <= 0:
        raise RegulationError(f"{label} sıfırdan büyük olmalı.")
    return int(value) if integer else value


def _only_keys(value: Mapping, allowed: set[str]) -> None:
    extra = set(value) - allowed
    if extra:
        raise RegulationError(f"Tanınmayan alan(lar): {', '.join(sorted(extra))}.")


def _v_sure(article: Article, value: Mapping) -> dict:
    _only_keys(value, {"dakika", "saat", "gun"})
    if len(value) != 1:
        raise RegulationError("Süre tek bir birimle verilmeli: dakika, saat ya da gun.")
    (unit, amount), = value.items()
    return {unit: _positive_number(amount, "Süre", integer=True)}


def _v_oran(article: Article, value: Mapping) -> dict:
    _only_keys(value, {"oran", "karsilastirma"})
    frac = _parse_fraction(value.get("oran"))
    comparison = value.get("karsilastirma", ">=")
    if comparison not in (">", ">="):
        raise RegulationError("Karşılaştırma '>' ya da '>=' olmalı.")
    if not (article.min_ratio <= frac <= article.max_ratio) or frac <= 0 and comparison == ">=":
        raise RegulationError(
            f"Oran {article.min_ratio} ile {article.max_ratio} arasında olmalı."
        )
    return {"oran": f"{frac.numerator}/{frac.denominator}", "karsilastirma": comparison}


def _v_tamsayi(article: Article, value: Mapping) -> dict:
    _only_keys(value, {"deger"})
    return {"deger": _positive_number(value.get("deger"), "Değer", integer=True)}


def _v_sayi(article: Article, value: Mapping) -> dict:
    _only_keys(value, {"deger"})
    return {"deger": _positive_number(value.get("deger"), "Değer")}


def _v_itiraz(article: Article, value: Mapping) -> dict:
    _only_keys(value, {"min", "oran", "aktiflik_gun"})
    frac = _parse_fraction(value.get("oran"))
    if not (0 < frac <= 1):
        raise RegulationError("İtiraz oranı 0 ile 1 arasında olmalı.")
    return {
        "min": _positive_number(value.get("min"), "En az itiraz", integer=True),
        "oran": f"{frac.numerator}/{frac.denominator}",
        "aktiflik_gun": _positive_number(value.get("aktiflik_gun"), "Aktiflik günü", integer=True),
    }


def _v_karar_saati(article: Article, value: Mapping) -> dict:
    _only_keys(value, {"gun", "saat", "tz", "pencere_dakika"})
    if value.get("gun") not in WEEKDAYS:
        raise RegulationError(f"Gün şunlardan biri olmalı: {', '.join(WEEKDAYS)}.")
    saat = value.get("saat")
    try:
        hh, mm = (int(p) for p in str(saat).split(":"))
        assert 0 <= hh < 24 and 0 <= mm < 60
    except (ValueError, AssertionError) as exc:
        raise RegulationError("Saat SS:DD biçiminde olmalı (ör. 20:00).") from exc
    if value.get("tz") != "Europe/Istanbul":
        raise RegulationError("Saat dilimi Europe/Istanbul olmalı.")
    window = _positive_number(value.get("pencere_dakika"), "Pencere", integer=True)
    return {"gun": value["gun"], "saat": f"{hh:02d}:{mm:02d}", "tz": value["tz"],
            "pencere_dakika": window}


def _v_agirliklar(article: Article, value: Mapping) -> dict:
    keys = set(article.default)
    _only_keys(value, keys)
    if set(value) != keys:
        raise RegulationError(f"Tüm alanlar verilmeli: {', '.join(sorted(keys))}.")
    return {k: _positive_number(value[k], k, integer=k.endswith("_dk")) for k in article.default}


_VALIDATORS: dict[str, Callable[[Article, Mapping], dict]] = {
    "sure": _v_sure,
    "oran": _v_oran,
    "tamsayi": _v_tamsayi,
    "sayi": _v_sayi,
    "itiraz": _v_itiraz,
    "karar_saati": _v_karar_saati,
    "agirliklar": _v_agirliklar,
}


def validate_value(key: str, value: Any) -> dict:
    """Madde değerini doğrular ve normalize eder; geçersizse ``RegulationError``."""
    article = DEFAULT_ARTICLES.get(key)
    if article is None:
        raise RegulationError(f"Böyle bir yönetmelik maddesi yok: {key}.")
    if not isinstance(value, Mapping):
        raise RegulationError("Madde değeri bir nesne olmalı.")
    return _VALIDATORS[article.kind](article, value)


# --- okuma ----------------------------------------------------------------------------------


class Regulation:
    """Belirli bir andaki madde değerleri (ör. Karar Saati anlık görüntüsü)."""

    def __init__(self, values: Mapping[str, dict]):
        self.values: dict[str, dict] = dict(values)

    @classmethod
    def defaults(cls) -> Regulation:
        return cls({k: dict(a.default) for k, a in DEFAULT_ARTICLES.items()})

    def raw(self, key: str) -> dict:
        try:
            return self.values[key]
        except KeyError as exc:
            raise RegulationError(f"Yönetmelikte madde eksik: {key}.") from exc

    def duration(self, key: str) -> timedelta:
        value = self.raw(key)
        if "dakika" in value:
            return timedelta(minutes=value["dakika"])
        if "saat" in value:
            return timedelta(hours=value["saat"])
        return timedelta(days=value["gun"])

    def ratio(self, key: str) -> Ratio:
        value = self.raw(key)
        return Ratio(Fraction(value["oran"]), value.get("karsilastirma", ">="))

    def integer(self, key: str) -> int:
        return int(self.raw(key)["deger"])

    def number(self, key: str) -> float:
        return float(self.raw(key)["deger"])

    def objection_threshold(self, active_members: int) -> int:
        value = self.raw("itiraz_esigi")
        share = Fraction(value["oran"]) * active_members
        return max(int(value["min"]), math.ceil(share))

    def objection_activity_window(self) -> timedelta:
        return timedelta(days=self.raw("itiraz_esigi")["aktiflik_gun"])

    def decision_hour(self) -> DecisionHourSpec:
        value = self.raw("karar_saati")
        hh, mm = (int(p) for p in value["saat"].split(":"))
        return DecisionHourSpec(
            weekday=WEEKDAYS.index(value["gun"]),
            hour=hh,
            minute=mm,
            tz=value["tz"],
            window=timedelta(minutes=value["pencere_dakika"]),
        )

    def interaction_weights(self) -> dict[str, float]:
        return dict(self.raw("etkilesim_agirliklari"))
