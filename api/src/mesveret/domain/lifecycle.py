"""Önerinin yaşam döngüsü (State deseni).

Her durum bir sınıftır; durumda geçerli olmayan bir işlem, durumun kendi Türkçe gerekçesiyle
``InvalidTransition`` yükseltir. Servisler ``if p.status == "SILENT"`` gibi denetimleri dağıtmak
yerine durumdan izin ister ya da ondan sonraki durumu alır:

    p.status = state_of(p.status).escalate().status

Geçişler::

    TASLAK ──gönder──▶ (şerit) ─┬─▶ SESSIZ ───────itiraz eşiği──▶ KUYRUK
                                ├─▶ RAKIP_SURESI ──süre doldu───▶ KUYRUK
                                └─▶ KUYRUK ───Karar Saati açıldı─▶ OYLAMA
    SESSIZ, OYLAMA (ve doğrudan karar veren geliştirme/test yolu: KUYRUK, RAKIP_SURESI)
        ──▶ KABUL | RET | CAKISMA   (üçü de son durumdur)

Bu modül saf mantıktır: veritabanı ya da ``Proposal`` nesnesi bilmez, durum adlarıyla çalışır.
"""

from __future__ import annotations

from typing import ClassVar, NoReturn

from mesveret.domain.types import Lane, ProposalStatus, ProposalType


class InvalidTransition(Exception):
    def __init__(self, status: ProposalStatus, action: str, message: str) -> None:
        super().__init__(message)
        self.status, self.action, self.message = status, action, message


class ProposalState:
    status: ClassVar[ProposalStatus]
    # Karar bekliyor mu (açık öneri listesi, R6'nın "açık kapanış" denetimi)
    pending: ClassVar[bool] = False
    decided_message: ClassVar[str] = "Öneri zaten karara bağlandı."

    def _refuse(self, action: str, message: str) -> NoReturn:
        raise InvalidTransition(self.status, action, message)

    # --- durumu değiştirmeyen izinler -----------------------------------------------------------
    def submit(self) -> None:
        self._refuse("gönder", "Bu öneri taslak değil.")

    def object(self) -> None:
        self._refuse("itiraz", "Bu öneri itiraza açık değil.")

    def add_rival(self) -> None:
        self._refuse("rakip metin", "Rakip metin süresi doldu.")

    # --- geçişler -------------------------------------------------------------------------------
    def escalate(self) -> ProposalState:
        """İtiraz eşiği aşıldı: yavaş şeride geç."""
        self._refuse("yavaş şerit", "Yalnızca sessiz onaydaki öneri yavaş şeride geçer.")

    def end_rival_period(self) -> ProposalState:
        self._refuse("rakip süresi", "Rakip metin süresi yalnızca kapanış önerisinde işler.")

    def enter_session(self) -> ProposalState:
        self._refuse("oylama", "Yalnızca kuyruktaki öneri Karar Saati'ne alınır.")

    def accept(self) -> ProposalState:
        self._refuse("kabul", self.decided_message)

    def reject(self) -> ProposalState:
        self._refuse("ret", self.decided_message)

    def conflict(self) -> ProposalState:
        self._refuse("çakışma", self.decided_message)


class _Pending(ProposalState):
    """Karar bekleyen durumların ortak sonuçları."""

    pending = True

    def accept(self) -> ProposalState:
        return Accepted()

    def reject(self) -> ProposalState:
        return Rejected()

    def conflict(self) -> ProposalState:
        return Conflicted()


class Draft(ProposalState):
    status = ProposalStatus.DRAFT

    def submit(self) -> None:
        return None


class Silent(_Pending):
    status = ProposalStatus.SILENT

    def object(self) -> None:
        return None

    def escalate(self) -> ProposalState:
        return Queued()


class RivalPeriod(_Pending):
    status = ProposalStatus.RIVAL_PERIOD

    def add_rival(self) -> None:
        return None

    def end_rival_period(self) -> ProposalState:
        return Queued()


class Queued(_Pending):
    status = ProposalStatus.QUEUED

    def enter_session(self) -> ProposalState:
        return Voting()


class Voting(_Pending):
    status = ProposalStatus.VOTING


class Accepted(ProposalState):
    status = ProposalStatus.ACCEPTED


class Rejected(ProposalState):
    status = ProposalStatus.REJECTED


class Conflicted(ProposalState):
    status = ProposalStatus.CONFLICT


_STATES: dict[ProposalStatus, type[ProposalState]] = {
    s.status: s for s in (Draft, Silent, RivalPeriod, Queued, Voting, Accepted, Rejected, Conflicted)
}

PENDING_STATUSES: tuple[str, ...] = tuple(str(s) for s, cls in _STATES.items() if cls.pending)
DECIDED_STATUSES: tuple[str, ...] = (ProposalStatus.ACCEPTED, ProposalStatus.REJECTED,
                                     ProposalStatus.CONFLICT)


def state_of(status: str) -> ProposalState:
    return _STATES[ProposalStatus(status)]()


def opening_state(t: ProposalType, lane: Lane) -> ProposalState:
    """Açılışta (ya da taslak gönderilince) girilen ilk durum: kapanış rakip metin süresine,
    hızlı şerit sessiz onaya, yavaş şerit kuyruğa."""
    if t is ProposalType.KAPANIS:
        return RivalPeriod()
    return Silent() if lane is Lane.FAST else Queued()
