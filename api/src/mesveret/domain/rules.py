"""Denetim kuralları R1, R2, R3, R5, R6 (R4 havalede: ``domain.delegation``).

Her öneri açılırken çalışır; ihlaller Türkçe gerekçeyle döner. Hâtif oylama anında
aynı kuralları yeniden çalıştırır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from mesveret.domain.ontology import OntologyView, ResourceInfo, ResourceKind, ScopeInfo
from mesveret.domain.regulation import Regulation
from mesveret.domain.scopes import GENERAL_SCOPE_ID, ScopeSubtype
from mesveret.domain.types import ProposalType

ISTANBUL_TZ = "Europe/Istanbul"

_SUBTYPE_LABEL = {ScopeSubtype.SEHIR: "şehir", ScopeSubtype.YAS_GRUBU: "yaş grubu"}


@dataclass(frozen=True)
class ProposalDraft:
    type: ProposalType
    proposer_id: str
    scope_id: str
    area_id: str | None
    resource_ids: tuple[str, ...] = ()
    parent_topic_id: str | None = None
    target_key: str | None = None
    title: str = ""
    body: str = ""


@dataclass(frozen=True)
class VoteRight:
    has_right: bool
    reason: str | None = None


@dataclass(frozen=True)
class RuleContext:
    onto: OntologyView
    reg: Regulation
    now: datetime
    proposer_right: VoteRight
    last_rejection: datetime | None = None


@dataclass(frozen=True)
class Violation:
    rule: str
    message: str


@dataclass(frozen=True)
class Narrowing:
    resource_id: str
    scope_id: str
    share: int | None
    message: str


@dataclass
class RuleReport:
    violations: list[Violation] = field(default_factory=list)
    narrowings: list[Narrowing] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


def format_points(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def format_date(dt: datetime) -> str:
    from zoneinfo import ZoneInfo

    return dt.astimezone(ZoneInfo(ISTANBUL_TZ)).strftime("%d.%m.%Y %H:%M")


def _scope_label(scope: ScopeInfo) -> str:
    return scope.name if scope.id != GENERAL_SCOPE_ID else "Genel kapsam"


def _check_r1(d: ProposalDraft, c: RuleContext, report: RuleReport) -> None:
    if d.type is not ProposalType.ALT_KONU:
        return
    parent_area_id = c.onto.topic_area(d.parent_topic_id) if d.parent_topic_id else None
    if parent_area_id is None:
        report.violations.append(Violation("GECERLILIK", "Üst konu bulunamadı."))
        return
    if d.area_id is None or d.area_id not in c.onto.area_subtree(parent_area_id):
        area = c.onto.area(d.area_id) if d.area_id else None
        parent = c.onto.area(parent_area_id)
        area_name = area.name if area else "—"
        parent_name = parent.name if parent else parent_area_id
        report.violations.append(Violation(
            "R1",
            f"Alt konunun alanı ('{area_name}'), üst konunun alanının ('{parent_name}') "
            "kendisi ya da alt alanlarından biri olmalı.",
        ))


def _check_r2_resource(
    scope: ScopeInfo, r: ResourceInfo, c: RuleContext, report: RuleReport
) -> None:
    owner = c.onto.scope(r.owner_scope_id)
    owner_label = _scope_label(owner) if owner else r.owner_scope_id
    if scope.id == r.owner_scope_id:
        return
    prefix = "Bu kapsam bu kaynak hakkında karar veremez"
    if not c.onto.is_strict_subset(scope.id, r.owner_scope_id):
        report.violations.append(Violation(
            "R2", f"{prefix}: '{r.name}' kaynağının sahibi {owner_label}."
        ))
        return
    if not r.divisible:
        report.violations.append(Violation(
            "R2", f"{prefix}: '{r.name}' bölünemez ve sahibi {owner_label}."
        ))
        return
    if scope.subtype is not r.division_type:
        label = _SUBTYPE_LABEL.get(r.division_type, "kapsam") if r.division_type else "kapsam"
        report.violations.append(Violation(
            "R2", f"{prefix}: '{r.name}' yalnızca {label} bazında bölünebilir."
        ))
        return
    share = r.shares.get(scope.id)
    if share is None:
        report.violations.append(Violation(
            "R2", f"{prefix}: '{r.name}' içinde {scope.name} için tanımlı bir pay yok."
        ))
        return
    report.narrowings.append(Narrowing(
        r.id, scope.id, share,
        f"Bu karar yalnızca {scope.name} payını etkiler ({format_points(share)} puan).",
    ))


def _check_r2_r3(d: ProposalDraft, c: RuleContext, report: RuleReport) -> None:
    scope = c.onto.scope(d.scope_id)
    if scope is None:
        report.violations.append(Violation("GECERLILIK", "Seçmen kapsamı bulunamadı."))
    resources: list[ResourceInfo] = []
    for rid in d.resource_ids:
        r = c.onto.resource(rid)
        if r is None:
            report.violations.append(Violation("GECERLILIK", f"Kaynak bulunamadı: {rid}."))
        else:
            resources.append(r)

    articles = [r for r in resources if r.kind is ResourceKind.YONETMELIK_MADDESI]
    if articles and d.type is not ProposalType.YONETMELIK:
        report.violations.append(Violation(
            "R3", "Yönetmelik maddeleri yalnızca Yönetmelik önerisiyle değiştirilebilir."
        ))
    if d.type is ProposalType.YONETMELIK:
        if d.scope_id != GENERAL_SCOPE_ID:
            report.violations.append(Violation(
                "R3", "Yönetmelik değişiklikleri Genel kapsamda, yavaş şeritte oylanır."
            ))
        if not articles:
            report.violations.append(Violation(
                "R3", "Yönetmelik önerisi değiştireceği maddeyi belirtmeli."
            ))

    if scope is not None:
        for r in resources:
            _check_r2_resource(scope, r, c, report)


def _check_r5(c: RuleContext, report: RuleReport) -> None:
    if not c.proposer_right.has_right:
        reason = c.proposer_right.reason or "Bu kapsamın üyesi değilsiniz."
        report.violations.append(Violation(
            "R5", f"Seçmen kapsamında oy hakkınız yok: {reason}"
        ))


def _check_r6(c: RuleContext, report: RuleReport) -> None:
    if c.last_rejection is None:
        return
    reopen_at = c.last_rejection + c.reg.duration("red_bekleme")
    if c.now < reopen_at:
        report.violations.append(Violation(
            "R6",
            f"Bu hedefe yönelik bir öneri {format_date(c.last_rejection)} tarihinde "
            f"oylamayla reddedildi; {format_date(reopen_at)} tarihine kadar yeniden açılamaz.",
        ))


def _check_area(d: ProposalDraft, c: RuleContext, report: RuleReport) -> None:
    if d.type in (ProposalType.KONU, ProposalType.ALT_KONU):
        if d.area_id is None or c.onto.area(d.area_id) is None:
            report.violations.append(Violation("GECERLILIK", "Alan bulunamadı."))


def check_proposal(d: ProposalDraft, c: RuleContext) -> RuleReport:
    report = RuleReport()
    _check_area(d, c, report)
    _check_r1(d, c, report)
    _check_r2_r3(d, c, report)
    _check_r5(c, report)
    _check_r6(c, report)
    return report
