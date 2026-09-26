from enum import StrEnum


class ProposalType(StrEnum):
    KONU = "KONU"
    ALT_KONU = "ALT_KONU"
    DUZENLEME = "DUZENLEME"
    SILME = "SILME"
    YONETMELIK = "YONETMELIK"
    KAPANIS = "KAPANIS"


class ProposalStatus(StrEnum):
    DRAFT = "DRAFT"  # Mahzen ifşasından gelen taslak
    SILENT = "SILENT"  # hızlı şerit, sessiz onay süresi işliyor
    RIVAL_PERIOD = "RIVAL_PERIOD"  # KAPANIS, rakip metin süresi işliyor
    QUEUED = "QUEUED"  # bir sonraki Karar Saati'ni bekliyor
    VOTING = "VOTING"  # Karar Saati penceresi açık
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class Lane(StrEnum):
    FAST = "FAST"
    SLOW = "SLOW"


FAST_LANE_TYPES = frozenset({ProposalType.KONU, ProposalType.ALT_KONU, ProposalType.DUZENLEME})


def initial_lane(t: ProposalType) -> Lane:
    return Lane.FAST if t in FAST_LANE_TYPES else Lane.SLOW


PROPOSAL_TYPE_LABELS = {
    ProposalType.KONU: "Konu",
    ProposalType.ALT_KONU: "Alt konu",
    ProposalType.DUZENLEME: "Düzenleme",
    ProposalType.SILME: "Silme",
    ProposalType.YONETMELIK: "Yönetmelik",
    ProposalType.KAPANIS: "Kapanış",
}
