"""Yönetmelik = veri.

Tüm eşikler ve süreler ``YonetmelikMaddesi`` düğümlerinde durur; bu modül yalnızca
varsayılanları, değer şemalarını ve tipli okuyucuları tanımlar. İş kodu eşik ya da
süre sabiti içermez, her zaman bir ``Regulation`` örneğinden okur.

İki tür madde vardır: parametreler (süre, oran, sayı) ve içerik kuralları (``IK-<n>``). İçerik
kuralı bir metin kuralıdır; başkasının içeriğini silme önerisi en az birine dayanmak zorundadır.
Parametrelerin kümesi sabittir, yalnızca değerleri değişir. İçerik kuralları ise yönetmelik
önerisiyle eklenip kaldırılabilir; tohumdaki üç kural bilerek dardır.

Yönetmeliğin bir tabanı vardır: değiştirilemez maddeler (D1–D7 temel ilkeleri) ve her sayısal
parametrenin değiştirilemez izinli aralığı. Maddeler oylamayla değiştirilemez, kaldırılamaz;
parametreler aralıklarının dışına çıkarılamaz (R8).
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
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

    def at_least_as_strict_as(self, other: Ratio) -> bool:
        """Bu eşiği geçen her pay ``other`` eşiğini de geçer mi (taban karşılaştırması)."""
        if self.value != other.value:
            return self.value > other.value
        return other.comparison == ">=" or self.comparison == ">"

    def describe(self) -> str:
        op = "fazlası" if self.comparison == ">" else "en az"
        pct = f"%{float(self.value) * 100:.4g}"
        return f"{self.value} ({pct}) — {op}" if self.comparison == ">" else f"{op} {self.value} ({pct})"


@dataclass(frozen=True)
class Interval:
    """Değiştirilemez izinli aralık (uçlar dahil). Oranlarda uçlar ``Ratio``dur: değer alt uçtan
    daha katı ya da ona eşit, üst uçtan daha gevşek ya da ona eşit olmalı."""

    lo: Fraction | Ratio
    hi: Fraction | Ratio
    text: str  # "12 saat – 72 saat", "> 1/2 – ≥ 2/3"

    def contains(self, x: Fraction | Ratio) -> bool:
        if isinstance(self.lo, Ratio) and isinstance(self.hi, Ratio) and isinstance(x, Ratio):
            return x.at_least_as_strict_as(self.lo) and self.hi.at_least_as_strict_as(x)
        return self.lo <= x <= self.hi  # type: ignore[operator]


def _hours(lo: float, hi: float, text: str | None = None) -> dict[str, Interval]:
    return {"sure": Interval(Fraction(lo), Fraction(hi), text or f"{lo} saat – {hi} saat")}


def _days(lo: int, hi: int, text: str | None = None) -> dict[str, Interval]:
    return {"sure": Interval(Fraction(lo * 24), Fraction(hi * 24), text or f"{lo} – {hi} gün")}


def _ratio(lo_cmp: str, lo: str, hi_cmp: str, hi: str) -> dict[str, Interval]:
    op = {">": ">", ">=": "≥"}
    return {"oran": Interval(Ratio(Fraction(lo), lo_cmp), Ratio(Fraction(hi), hi_cmp),
                             f"{op[lo_cmp]} {lo} – {op[hi_cmp]} {hi}")}


def _num(lo: float, hi: float, text: str, name: str = "deger") -> dict[str, Interval]:
    return {name: Interval(Fraction(str(lo)), Fraction(str(hi)), text)}


@dataclass(frozen=True)
class DecisionHourSpec:
    weekday: int  # Pazartesi = 0 … Pazar = 6
    hour: int
    minute: int
    tz: str
    window: timedelta


@dataclass(frozen=True)
class ContentRule:
    code: str  # "IK-2"
    title: str
    text: str
    keywords: tuple[str, ...]  # Hâtif'in anahtar kelime denetimi için


CONTENT_RULE_KIND = "icerik_kurali"
CONTENT_RULE_KEY = re.compile(r"^IK-([1-9][0-9]*)$")


def content_rule_number(key: str) -> int | None:
    m = CONTENT_RULE_KEY.match(key)
    return int(m.group(1)) if m else None


@dataclass(frozen=True)
class Article:
    key: str
    kind: str
    default: dict[str, Any]
    description: str
    min_ratio: Fraction = Fraction(0)
    max_ratio: Fraction = Fraction(1)
    unchangeable: bool = False  # YonetmelikMaddesi.degistirilemez
    # Sayısal parametrenin değiştirilemez izinli aralığı: ölçülen nicelik → aralık (bkz. _measures).
    allowed: Mapping[str, Interval] = field(default_factory=dict)


WEEKDAYS = ["PAZARTESI", "SALI", "CARSAMBA", "PERSEMBE", "CUMA", "CUMARTESI", "PAZAR"]

# (anahtar, ilke, açıklama). Metinler bilgilendiricidir; ilkeleri kod uygular, bu maddeler
# yalnızca onların oylamayla kaldırılamayacağını kayda geçirir.
PRINCIPLES = [
    ("D1", "Her yurttaşın bir temel oyu vardır.",
     ("Oy havale edilebilir ama elden alınamaz; havale pencere dışında her an geri alınır. "
      "Hiçbir oylama bir yurttaşın oyunu sıfırlayamaz.")),
    ("D2", "Her yurttaş öneri açabilir.",
     ("Seçmen kapsamında oy hakkı olan her yurttaş öneri açabilir; öneri açma hakkı bir role, "
      "rütbeye ya da onaya bağlanamaz.")),
    ("D3", "Kaybeden taraf Şerh ekleyebilir; Şerh silinemez.",
     ("Kapanış oylamasında kaybeden metnin sahibi ve destekçileri Karar'a Şerh ekler. Şerh "
      "düzenlenemez, hiçbir önerinin hedefi olamaz.")),
    ("D4", "İçerik yalnızca oylamayla silinebilir.",
     ("Hiçbir rol ya da yönetici içerik silemez; silme bir öneridir ve Karar Saati'nde oylanır. "
      "Silinen içerik defterde kalır.")),
    ("D5", "Eşzamanlı çoğunluk ilkesi.",
     ("Bölünebilir bir kaynakta payı orantısız azaltılan alt kapsam ayrıca oylar; öneri o "
      "kapsamda da çoğunluk almadan geçemez.")),
    ("D6", "Defter değiştirilemez.",
     "Deftere yazılan kayıt güncellenemez ve silinemez; zincir herkes tarafından doğrulanabilir."),
    ("D7", "Bu listenin kendisi.",
     ("D1–D7 ve sayısal parametrelerin izinli aralıkları değiştirilemez; listeye madde "
      "eklenemez, listeden madde çıkarılamaz, bir madde değiştirilebilir yapılamaz, bir aralık "
      "genişletilemez.")),
]


def _articles() -> dict[str, Article]:
    items = [
        # İzinli aralıklar (allowed) değiştirilemez; seçimleri ve gerekçeleri DESIGN.md §5.2'de.
        Article("sessiz_onay_suresi", "sure", {"saat": 24},
                "Hızlı şeritteki önerinin itiraza açık kalma süresi.", allowed=_hours(12, 72)),
        Article("itiraz_esigi", "itiraz", {"min": 3, "oran": "1/20", "aktiflik_gun": 30},
                "Hızlı şerit önerisini yavaş şeride aktaran itiraz sayısı: "
                "max(min, kapsamdaki aktif üyelerin oranı). Aktif: son aktiflik_gun günde giriş.",
                allowed={**_num(3, 20, "en az 3–20 itiraz", "min"),
                         **_num(Fraction(1, 50), Fraction(1, 5), "oran %2 – %20", "oran"),
                         **_num(7, 90, "aktiflik 7–90 gün", "aktiflik_gun")}),
        Article("basit_cogunluk", "oran", {"oran": "1/2", "karsilastirma": ">"},
                "Kullanılan oylar içinde kabul için gereken pay.", Fraction(1, 2),
                allowed=_ratio(">", "1/2", ">=", "2/3")),
        Article("yonetmelik_esigi", "oran", {"oran": "2/3", "karsilastirma": ">="},
                "Yönetmelik değişikliği için kullanılan oylar içinde gereken pay. "
                "Bu maddenin kendisi de bu eşikle değişir.",
                allowed=_ratio(">=", "2/3", ">=", "3/4")),
        Article("silme_esigi", "oran", {"oran": "2/3", "karsilastirma": ">="},
                "Başkasının içeriğini silmek için kullanılan oylar içinde gereken pay. Kendi "
                "mesajının silinmesi basit çoğunlukla oylanır.",
                allowed=_ratio(">=", "2/3", ">=", "3/4")),
        Article("orantisizlik_esigi", "yuzde_puani", {"deger": 10},
                "Bölünebilir kaynakta bir alt kapsamın payındaki göreli azalma, tüm alt "
                "kapsamların ortalama göreli değişiminden en az bu kadar yüzde puanı fazlaysa o "
                "kapsam orantısız etkilenir ve öneri o kapsamda ayrıca oylanır.",
                allowed=_num(5, 30, "5 – 30 yüzde puanı")),
        Article("red_bekleme", "sure", {"gun": 30},
                "Oylamayla reddedilen hedefe yeni öneri açılamayan süre.", allowed=_days(7, 90)),
        Article("musavir_esigi", "tamsayi", {"deger": 5},
                "Bir alanda Müşavir etiketi için gereken doğrudan havale sayısı.",
                allowed=_num(3, 50, "3 – 50 havale")),
        Article("havale_suresi", "sure", {"gun": 180},
                "Havalenin verildiği ya da yenilendiği andan itibaren geçerli kaldığı süre; sonunda "
                "oy sahibine döner. Değişiklik yalnızca yeni verilen ve yenilenen havaleleri etkiler.",
                allowed=_days(30, 365)),
        Article("havale_uyari_suresi", "sure", {"gun": 14},
                "Süresi bu kadar içinde dolacak havaleler için girişte, profilde ve Havale "
                "sayfasında uyarı şeridi gösterilir (bildirim sistemi yok).",
                allowed=_days(3, 30)),
        Article("ilgi_bekleme", "sure", {"gun": 14},
                "İlgi kapsamına katıldıktan sonra oy hakkının doğması için geçen süre.",
                allowed=_days(0, 30)),
        Article("adres_bekleme", "sure", {"gun": 90},
                "Adres değişikliğinden sonra yeni şehirde oy hakkının doğması için geçen süre.",
                allowed=_days(0, 180)),
        Article("karar_saati", "karar_saati",
                {"gun": "PAZAR", "saat": "20:00", "tz": "Europe/Istanbul", "pencere_dakika": 60},
                "Haftalık planlı oylama oturumu ve oy penceresinin uzunluğu.",
                allowed=_num(30, 180, "pencere 30 – 180 dakika", "pencere_dakika")),
        Article("kapanis_rakip_suresi", "sure", {"saat": 48},
                "Kapanış önerisine rakip karar metni eklenebilen süre.",
                allowed=_hours(24, 7 * 24, "24 saat – 7 gün")),
        Article("yeniden_acma", "sure", {"gun": 90},
                "Karara bağlanmış konunun yeniden açılabilmesi için geçmesi gereken süre.",
                allowed=_days(30, 365)),
        Article("olgunlasma_dar", "sure", {"saat": 48},
                "Tek bir nitelik kapsamına ya da yaprak alanın ilgi kapsamına sorulan öneri, "
                "Karar Saati'nde oylanmadan önce en az bu kadar yayında kalır.",
                allowed=_hours(24, 14 * 24, "24 saat – 14 gün")),
        Article("olgunlasma_genis", "sure", {"saat": 72},
                "Daha geniş (yaprak olmayan alanın ilgi kapsamına sorulan) öneri için olgunlaşma.",
                allowed=_hours(24, 14 * 24, "24 saat – 14 gün")),
        Article("olgunlasma_genel", "sure", {"gun": 7},
                "Genel kapsamlı ve yönetmelik önerileri için olgunlaşma.",
                allowed=_hours(24, 14 * 24, "24 saat – 14 gün")),
        Article("mahzen_kapasite", "tamsayi", {"deger": 100},
                "Mahzen'de yaşayan en fazla başlık sayısı; aşılınca en alttaki kalıcı silinir.",
                allowed=_num(30, 300, "30 – 300 başlık")),
        Article("mahzen_ust_sinir", "tamsayi", {"deger": 300},
                "Bu yanıt sayısına ulaşan Mahzen başlığı artık yükselemez.",
                allowed=_num(50, 1000, "50 – 1000 yanıt")),
        Article("mahzen_ifsa_esigi", "oran", {"oran": "1/2", "karsilastirma": ">"},
                "İfşa oylamasının geçmesi için EVET sayısının seçmen listesine oranı.",
                Fraction(0), allowed=_ratio(">", "1/2", ">=", "3/4")),
        Article("baskin_yeni_uye_suresi", "sure", {"gun": 7},
                "Anlık görüntüden en fazla bu kadar önce katılan seçmen baskın adayıdır.",
                allowed=_days(1, 30)),
        Article("baskin_katilim_araligi", "sure", {"saat": 24},
                "Baskın kümesindeki katılım anlarının yayılabileceği en uzun aralık.",
                allowed=_hours(1, 7 * 24, "1 saat – 7 gün")),
        Article("baskin_min_kume", "tamsayi", {"deger": 4},
                "Baskın olarak işaretlenecek en küçük küme boyutu.",
                allowed=_num(3, 20, "3 – 20 hesap")),
        Article("baskin_yogunluk_esigi", "oran", {"oran": "1/2", "karsilastirma": ">="},
                "Baskın kümesinde gereken kenar yoğunluğu (kenar / olası kenar).",
                allowed=_ratio(">=", "1/3", ">=", "1")),
        Article("baskin_min_agirlik", "sayi", {"deger": 1},
                "Kümelemede kenar sayılması için gereken en düşük etkileşim ağırlığı.",
                allowed=_num(Fraction(1, 2), 10, "0,5 – 10")),
        Article("etkilesim_agirliklari", "agirliklar",
                {"yanit": 1, "havale": 2, "yakin_kayit": 1, "yakin_kayit_dk": 60,
                 "ortak_baslik": 0.5, "ortak_baslik_dk": 30},
                "İlişki grafındaki sinyallerin ağırlıkları ve zaman pencereleri.",
                allowed={**{k: Interval(Fraction(1, 10), Fraction(10), "ağırlıklar 0,1 – 10")
                            for k in ("yanit", "havale", "yakin_kayit", "ortak_baslik")},
                         **{k: Interval(Fraction(5), Fraction(240), "pencereler 5 – 240 dakika")
                            for k in ("yakin_kayit_dk", "ortak_baslik_dk")}}),
        # Değiştirilemez maddeler: yönetmeliğin tabanı (bkz. DESIGN.md §5.1).
        *(Article(key, "temel_ilke", {"baslik": title, "metin": text}, "Değiştirilemez madde.",
                  unchangeable=True) for key, title, text in PRINCIPLES),
        # İçerik kuralları: silme önerisinin dayanabileceği tek gerekçeler.
        Article("IK-1", CONTENT_RULE_KIND, {
            "baslik": "Spam ve reklam",
            "metin": "Tartışmayla ilgisi olmayan ticari tanıtım, reklam ya da aynı iletinin "
                     "tekrar tekrar gönderilmesi.",
            "anahtar_kelimeler": ["reklam", "indirim", "kampanya", "tıkla", "satın al", "sipariş",
                                  "kupon", "promosyon", "fırsat", "bedava"],
        }, "İçerik kuralı: spam ve reklam."),
        Article("IK-2", CONTENT_RULE_KIND, {
            "baslik": "Hakaret ve tehdit",
            "metin": "Bir kişiyi ya da grubu aşağılayan sözler, küfür veya zarar verme tehdidi. "
                     "Sert eleştiri hakaret değildir.",
            "anahtar_kelimeler": ["cahil", "aptal", "salak", "ahmak", "gerizekalı", "şerefsiz",
                                  "baş belası", "döverim", "gebertirim", "öldürürüm", "ezerim"],
        }, "İçerik kuralı: hakaret ve tehdit."),
        Article("IK-3", CONTENT_RULE_KIND, {
            "baslik": "Başkasının kişisel bilgilerini ifşa etme",
            "metin": "Başka birinin telefonunu, adresini, kimlik numarasını ya da benzeri "
                     "kişisel bilgisini rızası olmadan paylaşmak.",
            "anahtar_kelimeler": ["telefon", "numarası", "adresi", "ev adresi", "kimlik no",
                                  "tc kimlik", "iban", "plaka", "oturuyor"],
        }, "İçerik kuralı: başkasının kişisel bilgilerini ifşa etme."),
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
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
        raise RegulationError("Süre negatif olmayan bir tam sayı olmalı.")
    return {unit: amount}


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


def _v_yuzde_puani(article: Article, value: Mapping) -> dict:
    _only_keys(value, {"deger"})
    v = _positive_number(value.get("deger"), "Yüzde puanı")
    if v > 100:
        raise RegulationError("Yüzde puanı 100'den büyük olamaz.")
    return {"deger": v}


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


def _v_temel_ilke(article: Article, value: Mapping) -> dict:
    _only_keys(value, {"baslik", "metin"})
    if not all(isinstance(value.get(k), str) and value[k].strip() for k in ("baslik", "metin")):
        raise RegulationError("İlkenin başlığı ve metni boş olmayan metin olmalı.")
    return {"baslik": value["baslik"].strip(), "metin": value["metin"].strip()}


def _v_icerik_kurali(article: Article, value: Mapping) -> dict:
    _only_keys(value, {"baslik", "metin", "anahtar_kelimeler"})
    title, text = value.get("baslik"), value.get("metin")
    if not isinstance(title, str) or not title.strip() or len(title) > 80:
        raise RegulationError("Kuralın başlığı 1–80 karakterlik bir metin olmalı.")
    if not isinstance(text, str) or not text.strip() or len(text) > 1000:
        raise RegulationError("Kuralın metni 1–1000 karakterlik bir metin olmalı.")
    words = value.get("anahtar_kelimeler")
    if not isinstance(words, list) or not words or len(words) > 40 or not all(
        isinstance(w, str) and w.strip() for w in words
    ):
        raise RegulationError("Anahtar kelimeler 1–40 öğelik, boş olmayan metinlerden oluşan bir "
                              "liste olmalı.")
    return {"baslik": title.strip(), "metin": text.strip(),
            "anahtar_kelimeler": [w.strip() for w in words]}


_VALIDATORS: dict[str, Callable[[Article, Mapping], dict]] = {
    "sure": _v_sure,
    "oran": _v_oran,
    "tamsayi": _v_tamsayi,
    "sayi": _v_sayi,
    "yuzde_puani": _v_yuzde_puani,
    "itiraz": _v_itiraz,
    "karar_saati": _v_karar_saati,
    "agirliklar": _v_agirliklar,
    CONTENT_RULE_KIND: _v_icerik_kurali,
    "temel_ilke": _v_temel_ilke,
}


def article_kind(key: str) -> str | None:
    """Maddenin türü. Tohumda olmayan ``IK-<n>`` anahtarları eklenmiş içerik kurallarıdır."""
    article = DEFAULT_ARTICLES.get(key)
    if article is not None:
        return article.kind
    return CONTENT_RULE_KIND if CONTENT_RULE_KEY.match(key) else None


def validate_value(key: str, value: Any) -> dict:
    """Madde değerini doğrular ve normalize eder; geçersizse ``RegulationError``."""
    kind = article_kind(key)
    if kind is None:
        raise RegulationError(f"Böyle bir yönetmelik maddesi yok: {key}.")
    article = DEFAULT_ARTICLES.get(key) or Article(key, kind, {}, "Eklenmiş içerik kuralı.")
    if not isinstance(value, Mapping):
        raise RegulationError("Madde değeri bir nesne olmalı.")
    return _VALIDATORS[article.kind](article, value)


# --- okuma ----------------------------------------------------------------------------------


class Regulation:
    """Belirli bir andaki madde değerleri (ör. Karar Saati anlık görüntüsü)."""

    def __init__(self, values: Mapping[str, dict], unchangeable: Iterable[str] | None = None):
        self.values: dict[str, dict] = dict(values)
        # Graf düğümlerindeki degistirilemez bayrağı; verilmezse tohum tanımlarından.
        self.unchangeable: frozenset[str] = frozenset(
            unchangeable if unchangeable is not None
            else (k for k, a in DEFAULT_ARTICLES.items() if a.unchangeable)
        )

    def is_unchangeable(self, key: str) -> bool:
        return key in self.unchangeable



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

    def content_rules(self) -> dict[str, ContentRule]:
        """Yürürlükteki içerik kuralları, koda göre (IK-1, IK-2, …)."""
        keys = sorted((k for k in self.values if CONTENT_RULE_KEY.match(k)),
                      key=lambda k: content_rule_number(k) or 0)
        out = {}
        for key in keys:
            v = self.values[key]
            out[key] = ContentRule(key, v["baslik"], v["metin"], tuple(v["anahtar_kelimeler"]))
        return out


# --- izinli aralıklar -------------------------------------------------------------------------------


def _measures(kind: str, value: Mapping) -> dict[str, Fraction | Ratio]:
    """Maddenin aralıkla karşılaştırılan nicelikleri (süreler saat cinsinden)."""
    if kind == "sure":
        (unit, amount), = value.items()
        return {"sure": Fraction(amount) * {"dakika": Fraction(1, 60), "saat": 1, "gun": 24}[unit]}
    if kind == "oran":
        return {"oran": Ratio(Fraction(value["oran"]), value.get("karsilastirma", ">="))}
    if kind in ("tamsayi", "sayi", "yuzde_puani"):
        return {"deger": Fraction(str(value["deger"]))}
    if kind == "itiraz":
        return {"min": Fraction(value["min"]), "oran": Fraction(value["oran"]),
                "aktiflik_gun": Fraction(value["aktiflik_gun"])}
    if kind == "karar_saati":
        return {"pencere_dakika": Fraction(value["pencere_dakika"])}
    if kind == "agirliklar":
        return {k: Fraction(str(v)) for k, v in value.items()}
    return {}


def range_violations(key: str, value: Mapping) -> list[str]:
    """Değerin dışına çıktığı izinli aralıkların metinleri; aralık içindeyse boş liste."""
    article = DEFAULT_ARTICLES.get(key)
    if article is None or not article.allowed:
        return []
    try:
        measured = _measures(article.kind, value)
    except (KeyError, ValueError, ZeroDivisionError, TypeError):
        return []  # biçim hatasını değer doğrulaması bildirir
    out = [iv.text for name, iv in article.allowed.items()
           if name in measured and not iv.contains(measured[name])]
    return list(dict.fromkeys(out))


def describe_range(key: str) -> str | None:
    article = DEFAULT_ARTICLES.get(key)
    if article is None or not article.allowed:
        return None
    return " · ".join(dict.fromkeys(iv.text for iv in article.allowed.values()))


def _bound(x: Fraction | Ratio) -> str:
    return f"{x.comparison} {x.value}" if isinstance(x, Ratio) else str(x)


def range_bounds(key: str) -> dict[str, list[str]] | None:
    """Aralıkların uygulanan sınırları; metin değişmeden sınır değişirse yönetmelik hash'i de değişir."""
    article = DEFAULT_ARTICLES.get(key)
    if article is None or not article.allowed:
        return None
    return {name: [_bound(iv.lo), _bound(iv.hi)] for name, iv in sorted(article.allowed.items())}
