"""Ağırlıklı oy sayımı.

Girdiler Karar Saati anlık görüntüsünden gelir:
- ``resolved``: her kullanıcı → zincirinin son kişisi (havalesi olmayan kendisine eşlenir),
- ``eligible``: bu öneride oy hakkı olanlar (baskın işaretliler çıkarılmış).

Oy veren kişinin ağırlığı = 1 + zinciri kendisinde biten seçmenlerin sayısı. Zinciri
oy vermeyen birinde ya da seçmen olmayan birinde biten seçmenler çekimser sayılır.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field


@dataclass
class BinaryTally:
    yes: int = 0
    no: int = 0
    weights: dict[str, int] = field(default_factory=dict)
    abstained: set[str] = field(default_factory=set)
    ignored: set[str] = field(default_factory=set)

    @property
    def cast(self) -> int:
        return self.yes + self.no


@dataclass
class ApprovalTally:
    scores: dict[str, int] = field(default_factory=dict)
    winner: str | None = None
    tie: bool = False
    weights: dict[str, int] = field(default_factory=dict)
    abstained: set[str] = field(default_factory=set)
    ignored: set[str] = field(default_factory=set)


def _weights(
    voters: Iterable[str], resolved: Mapping[str, str], eligible: set[str]
) -> tuple[dict[str, int], set[str], set[str]]:
    voters = set(voters)
    valid = {v for v in voters if v in eligible and resolved.get(v, v) == v}
    weights = {v: 0 for v in valid}
    abstained: set[str] = set()
    for e in eligible:
        terminal = resolved.get(e, e)
        if terminal in weights:
            weights[terminal] += 1
        else:
            abstained.add(e)
    return weights, abstained, voters - valid


def tally_binary(
    votes: Mapping[str, bool], resolved: Mapping[str, str], eligible: set[str]
) -> BinaryTally:
    weights, abstained, ignored = _weights(votes, resolved, eligible)
    t = BinaryTally(weights=weights, abstained=abstained, ignored=ignored)
    for voter, w in weights.items():
        if votes[voter]:
            t.yes += w
        else:
            t.no += w
    return t


def tally_approval(
    votes: Mapping[str, set[str]],
    resolved: Mapping[str, str],
    eligible: set[str],
    text_ids: Iterable[str],
) -> ApprovalTally:
    weights, abstained, ignored = _weights(votes, resolved, eligible)
    scores = {tid: 0 for tid in text_ids}
    for voter, w in weights.items():
        for tid in votes[voter]:
            if tid in scores:
                scores[tid] += w
    t = ApprovalTally(scores=scores, weights=weights, abstained=abstained, ignored=ignored)
    best = max(scores.values(), default=0)
    if best > 0:
        leaders = [tid for tid, s in scores.items() if s == best]
        if len(leaders) == 1:
            t.winner = leaders[0]
        else:
            t.tie = True
    return t
