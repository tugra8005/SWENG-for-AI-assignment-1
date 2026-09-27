"""Olgunlaşma: bir öneri Karar Saati'nde oylanmadan önce en az ne kadar yayında kalmalı.

Takvime bağlı bir kesim (ör. "Pazar 18:00'den sonra açılanlar sonraki haftaya") yerine
öneri başına, etkiyle ölçeklenen bir süre uygulanır:

- **dar**: tek bir nitelik kapsamı (şehir, yaş grubu) ya da yaprak alanın ilgi kapsamı,
- **geniş**: yaprak olmayan alanın ilgi kapsamı,
- **genel**: Genel kapsamlı öneriler ve yönetmelik önerileri.

Süre öneri yayına girdiği andan sayılır; hızlı şeritten itirazla yavaş şeride düşen önerilerde
düştükleri andan. Pencere açıldığında olgunlaşmamış öneri sonraki uygun oturuma kayar.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum

from mesveret.domain.decision_hour import next_occurrence
from mesveret.domain.ontology import OntologyView, ScopeInfo
from mesveret.domain.regulation import DecisionHourSpec, Regulation
from mesveret.domain.scopes import ScopeType
from mesveret.domain.types import FAST_LANE_TYPES, ProposalType


class MaturityClass(StrEnum):
    DAR = "dar"
    GENIS = "genis"
    GENEL = "genel"


LABELS = {MaturityClass.DAR: "dar", MaturityClass.GENIS: "geniş", MaturityClass.GENEL: "genel"}


def maturity_class(type_: ProposalType, scope: ScopeInfo | None, onto: OntologyView) -> MaturityClass:
    if type_ is ProposalType.YONETMELIK or scope is None or scope.type is ScopeType.GENEL:
        return MaturityClass.GENEL
    if scope.type is ScopeType.NITELIK:
        return MaturityClass.DAR
    area = scope.value
    if area is not None and onto.area_subtree(area) == {area}:
        return MaturityClass.DAR
    return MaturityClass.GENIS


def maturity_duration(klass: MaturityClass, reg: Regulation) -> timedelta:
    return reg.duration(f"olgunlasma_{klass.value}")


def matures_at(
    type_: ProposalType,
    *,
    created_at: datetime,
    queued_at: datetime | None,
    klass: MaturityClass,
    reg: Regulation,
) -> datetime:
    """Hızlı şerit türleri yavaş şeride ancak itirazla düşer: süre düştükleri andan sayılır."""
    base = queued_at if type_ in FAST_LANE_TYPES and queued_at is not None else created_at
    return base + maturity_duration(klass, reg)


def first_session_at(matures: datetime, now: datetime, spec: DecisionHourSpec) -> datetime:
    """Önerinin oylanacağı ilk planlı oturum: olgunlaşmadan ve şimdiden önce olmayan ilk oturum."""
    return next_occurrence(max(matures, now) - timedelta(microseconds=1), spec)
