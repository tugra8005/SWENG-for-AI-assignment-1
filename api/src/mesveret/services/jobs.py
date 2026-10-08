"""Zamanlanmış işler (Command deseni).

Her iş, ne yapılacağını kapsülleyen bir nesnedir: vade anı, açıklaması ve ``run``. Zamanlayıcı
(``services.scheduler``) işin ne yaptığını bilmez; yalnızca vadesi en erken olanı seçip
çalıştırır ve açıklamasını kaydeder. Bu yüzden ``advance-time`` çıktısı, arka plan günlüğü ve
testler aynı işleri aynı sırada görür.

Kaynaklar (``SOURCES``) vadesi gelen işleri üretir. Yeni bir zamanlanmış olay, yeni bir iş sınıfı
ve kaynağıdır; zamanlayıcının döngüsü değişmez. Her iş idempotenttir: durumu denetler, bir kez
yazar (iki süreç aynı işi seçse de sonuç tektir).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from mesveret.context import Ctx
from mesveret.db.models import Proposal
from mesveret.errors import DomainError


@dataclass(frozen=True)
class Job(ABC):
    due_at: datetime

    @property
    @abstractmethod
    def label(self) -> str: ...

    @abstractmethod
    def run(self, ctx: Ctx) -> None: ...


@dataclass(frozen=True)
class _ProposalJob(Job):
    proposal_id: int
    what: str = ""

    @property
    def label(self) -> str:
        return f"#{self.proposal_id}: {self.what}"

    def _transition(self, ctx: Ctx, p: Proposal) -> None:
        raise NotImplementedError

    def run(self, ctx: Ctx) -> None:
        from mesveret.services import proposals

        p = proposals.get_proposal(ctx, self.proposal_id)
        try:
            self._transition(ctx, p)
        except DomainError as exc:
            proposals.reject(ctx, p, f"Uygulanamadı: {exc.message}")


@dataclass(frozen=True)
class EndSilentPeriod(_ProposalJob):
    what: str = "sessiz onay süresi doldu"

    def _transition(self, ctx: Ctx, p: Proposal) -> None:
        from mesveret.services import proposals

        proposals.end_silent_period(ctx, p)


@dataclass(frozen=True)
class EndRivalPeriod(_ProposalJob):
    what: str = "rakip metin süresi doldu"

    def _transition(self, ctx: Ctx, p: Proposal) -> None:
        from mesveret.services import proposals

        proposals.end_rival_period(ctx, p)


@dataclass(frozen=True)
class ExpireDelegation(Job):
    user_id: str
    area_id: str | None
    description: str

    @property
    def label(self) -> str:
        return self.description

    def run(self, ctx: Ctx) -> None:
        from mesveret.services import delegation

        delegation.expire(ctx, self.user_id, self.area_id)


@dataclass(frozen=True)
class ExpireDelegationRequest(Job):
    request_id: int
    description: str

    @property
    def label(self) -> str:
        return self.description

    def run(self, ctx: Ctx) -> None:
        from mesveret.services import delegation

        delegation.expire_request(ctx, self.request_id)


@dataclass(frozen=True)
class CloseDecisionHour(Job):
    session_id: int

    @property
    def label(self) -> str:
        return f"Karar Saati #{self.session_id} kapandı"

    def run(self, ctx: Ctx) -> None:
        from mesveret.services import decision_hour

        decision_hour.close_scheduled(ctx, self.session_id)


@dataclass(frozen=True)
class OpenDecisionHour(Job):
    @property
    def label(self) -> str:
        return "haftalık Karar Saati açıldı"

    def run(self, ctx: Ctx) -> None:
        from mesveret.services import decision_hour

        decision_hour.open_scheduled(ctx, self.due_at)


# --- kaynaklar ------------------------------------------------------------------------------------


def delegation_jobs(ctx: Ctx, until: datetime, last: datetime | None) -> list[Job]:
    from mesveret.services import delegation

    jobs: list[Job] = []
    edge = delegation.next_expiry(ctx, until)
    if edge is not None and edge.expires_at is not None:
        giver, target = delegation.nicknames(ctx, [edge.user_id, edge.target_id])
        area = f" ({edge.area_id})" if edge.area_id else ""
        jobs.append(ExpireDelegation(edge.expires_at, edge.user_id, edge.area_id,
                                     f"havale süresi doldu: {giver} → {target}{area}"))
    req = delegation.next_request_expiry(ctx, until)
    if req is not None:
        giver, target = delegation.nicknames(ctx, [req.giver_id, req.target_id])
        area = f" ({req.area_id})" if req.area_id else ""
        jobs.append(ExpireDelegationRequest(
            req.decide_by, req.id, f"havale kabul süresi doldu: {giver} → {target}{area}"))
    return jobs


def proposal_jobs(ctx: Ctx, until: datetime, last: datetime | None) -> list[Job]:
    jobs: list[Job] = []
    for status, job in (("SILENT", EndSilentPeriod), ("RIVAL_PERIOD", EndRivalPeriod)):
        row = ctx.db.execute(
            select(Proposal).where(Proposal.status == status, Proposal.deadline_at <= until)
            .order_by(Proposal.deadline_at, Proposal.id).limit(1)
        ).scalar_one_or_none()
        if row is not None:
            jobs.append(job(row.deadline_at, row.id))
    return jobs


def decision_hour_jobs(ctx: Ctx, until: datetime, last: datetime | None) -> list[Job]:
    from mesveret.domain.decision_hour import next_occurrence
    from mesveret.services import decision_hour

    jobs: list[Job] = []
    current = decision_hour.open_session_row(ctx)
    if current is not None and current.closes_at <= until:
        jobs.append(CloseDecisionHour(current.closes_at, current.id))
    if last is not None:
        occ = next_occurrence(last, ctx.reg.decision_hour())
        if occ <= until:
            jobs.append(OpenDecisionHour(occ))
    return jobs


# Aynı andaki işlerde liste sırası belirleyicidir (zamanlayıcı ilk en erkeni seçer): havale dolumu
# önce gelir, o anda açılan oturumun anlık görüntüsü bitişi gelmiş havaleyi almaz.
SOURCES: tuple[Callable[[Ctx, datetime, datetime | None], list[Job]], ...] = (
    delegation_jobs, proposal_jobs, decision_hour_jobs,
)


def due(ctx: Ctx, until: datetime, last: datetime | None) -> list[Job]:
    return [job for source in SOURCES for job in source(ctx, until, last)]
