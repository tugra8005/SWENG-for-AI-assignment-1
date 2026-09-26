"""Alan testleri için küçük bir ontoloji.

Alan ağacı:
    kultur ─┬─ sinema ── belgesel
            └─ edebiyat
    kent ──── ulasim
"""

from mesveret.domain.ontology import AreaInfo, InMemoryOntology, ResourceInfo, ResourceKind, ScopeInfo
from mesveret.domain.scopes import ScopeSubtype, ScopeType


def sample_ontology() -> InMemoryOntology:
    areas = [
        AreaInfo("kultur", "Kültür", None, ("kültür", "sanat")),
        AreaInfo("sinema", "Sinema", "kultur", ("sinema", "film", "yönetmen")),
        AreaInfo("belgesel", "Belgesel", "sinema", ("belgesel",)),
        AreaInfo("edebiyat", "Edebiyat", "kultur", ("edebiyat", "roman", "şiir")),
        AreaInfo("kent", "Kent", None, ("kent", "şehir")),
        AreaInfo("ulasim", "Ulaşım", "kent", ("ulaşım", "otobüs", "bisiklet", "metro")),
    ]
    scopes = [
        ScopeInfo("genel", ScopeType.GENEL, "Genel"),
        ScopeInfo("sehir:istanbul", ScopeType.NITELIK, "İstanbul", ScopeSubtype.SEHIR, "İstanbul"),
        ScopeInfo("sehir:ankara", ScopeType.NITELIK, "Ankara", ScopeSubtype.SEHIR, "Ankara"),
        ScopeInfo("yas:25-34", ScopeType.NITELIK, "25-34 yaş", ScopeSubtype.YAS_GRUBU, "25-34"),
        ScopeInfo("ilgi:sinema", ScopeType.ILGI, "Sinema ilgi kapsamı", None, "sinema"),
    ]
    subset_of = {
        "sehir:istanbul": {"genel"},
        "sehir:ankara": {"genel"},
        "yas:25-34": {"genel"},
        "ilgi:sinema": {"genel"},
    }
    resources = [
        ResourceInfo(
            "butce", ResourceKind.ORTAK, "Etkinlik bütçesi", "genel",
            divisible=True, division_type=ScopeSubtype.SEHIR,
            shares={"sehir:istanbul": 4000, "sehir:ankara": 3000},
            aliases=("bütçe", "etkinlik bütçe"),
        ),
        ResourceInfo("salon", ResourceKind.ORTAK, "Ortak toplantı salonu", "genel",
                     aliases=("salon", "toplantı salon")),
        ResourceInfo("madde:red_bekleme", ResourceKind.YONETMELIK_MADDESI, "red_bekleme", "genel"),
        ResourceInfo("konu:ist-parklari", ResourceKind.KONU, "İstanbul parkları", "sehir:istanbul"),
        ResourceInfo("konu:film-gunleri", ResourceKind.KONU, "Film günleri", "genel"),
    ]
    topic_areas = {"konu:ist-parklari": "kent", "konu:film-gunleri": "sinema"}
    return InMemoryOntology(areas, scopes, subset_of, resources, topic_areas)
