"""Denetim kuralları R1, R2, R3, R5, R6, R7, R8 (R4 havalede: ``domain.delegation``).

Her öneri açılırken çalışır; ihlaller Türkçe gerekçeyle döner. Hâtif oylama anında
aynı kuralları yeniden çalıştırır.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from mesveret.domain.ontology import OntologyView, ResourceInfo, ResourceKind, ScopeInfo
from mesveret.domain.regulation import Regulation, range_violations
from mesveret.domain.scopes import GENERAL_SCOPE_ID, ScopeSubtype
from mesveret.domain.text import contains_words, genitive, tokens
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
    # SILME: dayanılan içerik kuralları, kuralı ihlal eden kısım (metinden alıntı), hedefin
    # güncel metni ve hedefin öneri sahibine ait bir mesaj olup olmadığı.
    content_rules: tuple[str, ...] = ()
    excerpt: str = ""
    target_text: str = ""
    own_content: bool = False
    # Bölünebilir kaynağın yapılandırılmış etkisi: {kaynak: {kapsam: yeni_pay}}. None: bildirilmedi.
    share_effect: Mapping[str, Mapping[str, int]] | None = None
    # YONETMELIK: hedef madde, işlem (degistir/ekle/kaldir) ve önerilen değer.
    article_key: str | None = None
    article_action: str | None = None
    new_value: Mapping | None = None


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
    total: int | None = None  # kaynağın tamamı (payların toplamı)
    effect_title: str | None = None  # "Etkinlik bütçesinin İstanbul payı"


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


def _check_share_effect(
    d: ProposalDraft, scope: ScopeInfo, r: ResourceInfo, report: RuleReport
) -> None:
    """R2'nin ters yönü: bütünün kaynağı böldüğü öneri etkisini kapsam başına bildirmeli."""
    effect = (d.share_effect or {}).get(r.id)
    if scope.id == r.owner_scope_id:
        if effect is None:
            example = ", ".join(f"{sid}: {format_points(v)}" for sid, v in list(r.shares.items())[:2])
            report.violations.append(Violation(
                "R2", f"'{r.name}' bölünebilir bir kaynak: öneri etkisini kapsam başına yeni "
                      f"paylarla bildirmeli ({{{example}, …}}); metin tek başına yetmez. Payları "
                      "değiştirmiyorsa boş bir etki bildirin.",
            ))
            return
    elif effect and set(effect) - {scope.id}:
        report.violations.append(Violation(
            "R2", f"Bu öneri '{r.name}' için {scope.name} payına daraltıldı; yalnızca kendi "
                  "payını değiştirebilir.",
        ))
        return
    for sid, value in (effect or {}).items():
        if sid not in r.shares:
            report.violations.append(Violation(
                "R2", f"'{r.name}' içinde payı olmayan kapsam: {sid}."))
        elif isinstance(value, bool) or not isinstance(value, int) or value < 0:
            report.violations.append(Violation(
                "R2", f"'{r.name}' için yeni pay negatif olmayan tam sayı olmalı ({sid})."))


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
        total=sum(r.shares.values()),
        effect_title=f"{genitive(r.name)} {scope.name} payı",
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
            before = len(report.violations)
            _check_r2_resource(scope, r, c, report)
            if r.divisible and len(report.violations) == before:
                _check_share_effect(d, scope, r, report)
    divisible = {r.id for r in resources if r.divisible}
    for rid in (d.share_effect or {}):
        if rid not in divisible:
            report.violations.append(Violation(
                "R2", f"Pay etkisi bildirilen kaynak ({rid}) bölünebilir bir ETKILER etiketi değil."))


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


def _check_r7(d: ProposalDraft, c: RuleContext, report: RuleReport) -> None:
    """Silme gerekçesi: başkasının içeriğini silmek bir içerik kuralına ve alıntıya dayanır."""
    if d.type is not ProposalType.SILME:
        return
    known = c.reg.content_rules()
    unknown = [code for code in d.content_rules if code not in known]
    if unknown:
        report.violations.append(Violation("R7", f"Böyle bir içerik kuralı yok: {', '.join(unknown)}."))
    if d.own_content and not d.content_rules and not d.excerpt.strip():
        return  # yazarın kendi mesajı: gerekçe gerekmez
    if not d.content_rules:
        options = "; ".join(f"{r.code} {r.title}" for r in known.values())
        report.violations.append(Violation(
            "R7", f"Silme önerisi en az bir içerik kuralına dayanmalı ({options}). Kendi "
                  "mesajınızın silinmesi için gerekçe gerekmez." if known else
                  "Yürürlükte içerik kuralı yok; başkasının içeriği silinemez. Kendi mesajınızın "
                  "silinmesi için gerekçe gerekmez.",
        ))
    part = tokens(d.excerpt)
    if not part:
        report.violations.append(Violation(
            "R7", "Metnin hangi kısmının kuralı ihlal ettiğini, metinden alıntılayarak belirtin.",
        ))
    elif not contains_words(tokens(d.target_text), part):
        report.violations.append(Violation(
            "R7", "Belirtilen kısım silinmesi önerilen metinde geçmiyor; metinden aynen alıntılayın.",
        ))


def _check_r8(d: ProposalDraft, c: RuleContext, report: RuleReport) -> None:
    """Yönetmeliğin tabanı: değiştirilemez maddeye dokunulamaz; parametre izinli aralığında kalır."""
    if d.type is not ProposalType.YONETMELIK or not d.article_key:
        return
    key = d.article_key
    if c.reg.is_unchangeable(key):
        title = c.reg.values.get(key, {}).get("baslik")
        report.violations.append(Violation(
            "R8", f"Bu madde değiştirilemez: {key}{f' ({title})' if title else ''}. Değiştirilemez "
                  "maddeler oylamayla değiştirilemez, kaldırılamaz; değiştirilmeleri önerilemez (D7).",
        ))
        return
    if d.article_action not in (None, "degistir") or not d.new_value:
        return
    outside = range_violations(key, d.new_value)
    if outside:
        report.violations.append(Violation(
            "R8", f"{key} değiştirilemez izinli aralığın dışında: {'; '.join(outside)}. İzinli "
                  "aralıklar oylamayla genişletilemez (D7).",
        ))


def _check_area(d: ProposalDraft, c: RuleContext, report: RuleReport) -> None:
    needs_area = d.type in (ProposalType.KONU, ProposalType.ALT_KONU)
    if needs_area and (d.area_id is None or c.onto.area(d.area_id) is None):
        report.violations.append(Violation("GECERLILIK", "Alan bulunamadı."))


def check_proposal(d: ProposalDraft, c: RuleContext) -> RuleReport:
    report = RuleReport()
    _check_area(d, c, report)
    _check_r1(d, c, report)
    _check_r2_r3(d, c, report)
    _check_r5(c, report)
    _check_r6(c, report)
    _check_r7(d, c, report)
    _check_r8(d, c, report)
    return report
