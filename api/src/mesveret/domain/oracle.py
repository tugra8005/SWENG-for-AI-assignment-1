"""Hâtif: kural tabanlı sembolik bilirkişi.

Gerçek bir yapay zekâ çağrısı yoktur. Hâtif her yeni öneriye bir etiket önerisi yorumu
bırakır ve Karar Saati'nde deterministik oy verir: R1–R6 ve H1–H3 geçerse EVET.

- H1 alan: metindeki kelimeler alanların anahtar kelimeleriyle eşlenir.
- H2 kaynak: metinde adı geçen ama ETKILER olarak etiketlenmemiş kaynak.
- H3 şehir: metin tek bir şehri anıyor, seçmen kapsamı başka bir şehrin kapsamı.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from mesveret.domain.ontology import OntologyView
from mesveret.domain.rules import RuleReport
from mesveret.domain.scopes import ScopeSubtype
from mesveret.domain.text import count_stem_hits, normalize, phrase_in, tokens

MIN_AREA_HITS = 2


@dataclass(frozen=True)
class Finding:
    kind: str  # H1, H2, H3
    suggestion: str  # alan id, kaynak id ya da kapsam id
    message: str


def _h1(words: list[str], area_id: str | None, onto: OntologyView) -> list[Finding]:
    hits: dict[str, int] = {}
    for area in onto.all_areas():
        stems = [normalize(k) for k in area.keywords]
        n = count_stem_hits(stems, words)
        if n:
            hits[area.id] = n
    if not hits:
        return []
    best = max(hits.values())
    leaders = [a for a, n in hits.items() if n == best]
    if best < MIN_AREA_HITS or len(leaders) != 1:
        return []
    best_id = leaders[0]
    if area_id is not None and area_id in onto.area_ancestors(best_id):
        return []
    best_area = onto.area(best_id)
    chosen = onto.area(area_id) if area_id else None
    chosen_label = f"'{chosen.name}'" if chosen else "seçilen alan"
    return [Finding(
        "H1", best_id,
        f"Alan: metin '{best_area.name if best_area else best_id}' alanına daha yakın "
        f"görünüyor ({best} anahtar kelime); {chosen_label} bu alanın üstü değil.",
    )]


def _h2(words: list[str], resource_ids: Sequence[str], onto: OntologyView) -> list[Finding]:
    found = []
    for r in onto.all_resources():
        if r.id in resource_ids or not r.aliases:
            continue
        if any(phrase_in(normalize(alias).split(), words) for alias in r.aliases):
            found.append(Finding(
                "H2", r.id,
                f"Kaynak: metin '{r.name}' kaynağından söz ediyor ama öneri bu kaynağı "
                "etkilenen kaynak olarak etiketlemiyor.",
            ))
    return found


def _h3(words: list[str], scope_id: str, onto: OntologyView) -> list[Finding]:
    scope = onto.scope(scope_id)
    if scope is None or scope.subtype is not ScopeSubtype.SEHIR:
        return []
    mentioned = [
        c for c in onto.city_scopes()
        if c.value and phrase_in(normalize(c.value).split(), words)
    ]
    if len(mentioned) != 1 or mentioned[0].id == scope_id:
        return []
    city = mentioned[0]
    return [Finding(
        "H3", city.id,
        f"Şehir: metin {city.name} şehrinden söz ediyor ama seçmen kapsamı {scope.name}.",
    )]


def label_check(
    text: str,
    area_id: str | None,
    scope_id: str,
    resource_ids: Sequence[str],
    onto: OntologyView,
) -> list[Finding]:
    words = tokens(text)
    return [*_h1(words, area_id, onto), *_h2(words, resource_ids, onto), *_h3(words, scope_id, onto)]


def oracle_vote(report: RuleReport, findings: Sequence[Finding]) -> bool:
    return report.ok and not findings


def oracle_comment(report: RuleReport, findings: Sequence[Finding], onto: OntologyView) -> str:
    lines: list[str] = []
    if report.ok:
        lines.append("Denetimler: R1–R6 geçti.")
    else:
        lines.append("Denetimler: " + "; ".join(f"{v.rule} — {v.message}" for v in report.violations))
    for n in report.narrowings:
        scope = onto.scope(n.scope_id)
        lines.append(
            "Talep kaynağın tamamını hedefliyordu; seçmen kapsamı yalnızca "
            f"{scope.name if scope else n.scope_id} payına karar verebilir, daraltma uygulandı."
        )
    if not findings:
        lines.append("Etiketler uyumlu görünüyor.")
        lines.append("Oylamada verilecek oy: EVET (etiketler değişmezse).")
        return "\n".join(lines)
    lines.append("Etiket önerisi:")
    for f in findings:
        label = f.suggestion
        if f.kind == "H1" and (a := onto.area(f.suggestion)):
            label = a.name
        elif f.kind == "H2" and (r := onto.resource(f.suggestion)):
            label = r.name
        elif f.kind == "H3" and (s := onto.scope(f.suggestion)):
            label = s.name
        lines.append(f"• {f.message} Öneri: {label}.")
    lines.append("Oylamada verilecek oy: HAYIR (etiketler böyle kalırsa).")
    return "\n".join(lines)
