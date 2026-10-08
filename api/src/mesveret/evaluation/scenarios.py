"""Baskın tespiti için etiketli senaryolar.

Gerçek veride baskın nadirdir ve etiketi yoktur (tohumdaki tek baskın dışında). Bu yüzden
değerlendirme, üretimdeki ETKILESIM sinyallerini (yakın kayıt, yanıt, ortak başlık) aynı
ağırlıklarla üreten bir benzetimle yapılır. Her senaryo bir Karar Saati anlık görüntüsüdür:
seçmenlerin katılım anları, aralarındaki yönlü etkileşim ağırlıkları ve gerçek baskıncılar.

Senaryolar tohumla belirlenir (aynı tohum aynı senaryoları üretir). Eğitim/sınama ayrımı
senaryo adının hash'iyle yapılır (Repeatable Splitting): ayrım çalıştırmadan çalıştırmaya değişmez.
Sınama kümesi bir kez üretilip dosyaya yazılır ve bir daha değiştirilmez.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

# Üretimdeki ``etkilesim_agirliklari`` maddesinin varsayılanları.
W_REPLY, W_NEAR_SIGNUP, W_SAME_THREAD = 1.0, 1.0, 0.5
NEAR_SIGNUP = timedelta(minutes=60)
SAME_THREAD = timedelta(minutes=30)
T = datetime(2026, 10, 4, 17, 0, tzinfo=UTC)  # Pazar 20:00 İstanbul: Karar Saati açılışı


@dataclass
class Scenario:
    name: str
    at: datetime
    joined: dict[str, datetime]
    interactions: dict[tuple[str, str], float]
    raiders: frozenset[str] = frozenset()
    # Senaryodaki grupların türleri (rapor için): "sinif", "duyuru", "hizli", "sessiz"…
    groups: dict[str, str] = field(default_factory=dict)

    @property
    def accounts(self) -> set[str]:
        return set(self.joined)

    def newcomers(self, window: timedelta = timedelta(days=7)) -> set[str]:
        return {u for u, t in self.joined.items() if self.at - window <= t <= self.at}

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name, "at": self.at.isoformat(),
            "joined": {u: t.isoformat() for u, t in sorted(self.joined.items())},
            "interactions": [[a, b, w] for (a, b), w in sorted(self.interactions.items())],
            "raiders": sorted(self.raiders), "groups": self.groups,
        }

    @staticmethod
    def from_json(d: Mapping[str, Any]) -> Scenario:
        return Scenario(
            name=d["name"], at=datetime.fromisoformat(d["at"]),
            joined={u: datetime.fromisoformat(t) for u, t in d["joined"].items()},
            interactions={(a, b): float(w) for a, b, w in d["interactions"]},
            raiders=frozenset(d["raiders"]), groups=dict(d.get("groups", {})),
        )


def split_of(name: str, test_share: float = 0.3) -> str:
    """Senaryo adının hash'ine göre "egitim" ya da "sinama" (kararlı ayrım)."""
    bucket = int(hashlib.sha256(name.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "sinama" if bucket < test_share else "egitim"


# --- benzetim -------------------------------------------------------------------------------------


class _Builder:
    """Bir senaryoyu sinyal sinyal kurar; ağırlıklar üretimdeki gibi birikir."""

    def __init__(self, name: str, rng: random.Random) -> None:
        self.name, self.rng = name, rng
        self.joined: dict[str, datetime] = {}
        self.inter: dict[tuple[str, str], float] = {}
        self.raiders: set[str] = set()
        self.groups: dict[str, str] = {}
        self._n = 0

    def _add(self, a: str, b: str, w: float) -> None:
        if a != b:
            self.inter[(a, b)] = self.inter.get((a, b), 0.0) + w

    def account(self, at: datetime, group: str, *, raider: bool = False) -> str:
        self._n += 1
        uid = f"{group}-{self._n}"
        for other, t in self.joined.items():  # yakın kayıt: iki yönlü
            if abs(t - at) <= NEAR_SIGNUP:
                self._add(uid, other, W_NEAR_SIGNUP)
                self._add(other, uid, W_NEAR_SIGNUP)
        self.joined[uid] = at
        self.groups[uid] = group
        if raider:
            self.raiders.add(uid)
        return uid

    def reply(self, a: str, b: str, times: int = 1) -> None:
        self._add(a, b, W_REPLY * times)

    def same_thread(self, people: list[str]) -> None:
        for i, a in enumerate(people):
            for b in people[i + 1:]:
                self._add(a, b, W_SAME_THREAD)
                self._add(b, a, W_SAME_THREAD)

    def build(self) -> Scenario:
        return Scenario(self.name, T, dict(self.joined), dict(self.inter),
                        frozenset(self.raiders), dict(self.groups))


def _old_members(b: _Builder, n: int) -> list[str]:
    olds = [b.account(T - timedelta(days=b.rng.uniform(30, 400)), "eski") for _ in range(n)]
    for a in olds:  # seyrek yanıt ağı
        for _ in range(b.rng.randint(0, 3)):
            b.reply(a, b.rng.choice(olds))
    return olds


def _solo_newcomers(b: _Builder, olds: list[str], n: int) -> None:
    """Haftaya dağılmış tek tük yeni üye: eskilere yanıt verir."""
    for _ in range(n):
        u = b.account(T - timedelta(hours=b.rng.uniform(1, 160)), "tekil")
        for _ in range(b.rng.randint(0, 6)):
            b.reply(u, b.rng.choice(olds))


def _class(b: _Builder, olds: list[str]) -> None:
    """Gerçek bir grup: bir sınıf aynı öğleden sonra kaydolur, birbirine yanıt verir."""
    start = T - timedelta(hours=b.rng.uniform(6, 120))
    people = [b.account(start + timedelta(minutes=b.rng.uniform(0, 150)), "sinif")
              for _ in range(b.rng.randint(4, 12))]
    for u in people:
        for _ in range(b.rng.randint(1, 4)):
            b.reply(u, b.rng.choice(people))
        for _ in range(b.rng.randint(0, 5)):
            b.reply(u, b.rng.choice(olds))
    b.same_thread(people[: b.rng.randint(2, len(people))])


def _announcement(b: _Builder, olds: list[str]) -> None:
    """Bir duyurudan sonra iki güne yayılan katılım; yeni gelenler çoğunlukla eskilere yazar."""
    start = T - timedelta(hours=b.rng.uniform(48, 150))
    people = [b.account(start + timedelta(hours=b.rng.uniform(0, 48)), "duyuru")
              for _ in range(b.rng.randint(5, 15))]
    for u in people:
        for _ in range(b.rng.randint(1, 6)):
            b.reply(u, b.rng.choice(olds))
        if b.rng.random() < 0.3:
            b.reply(u, b.rng.choice(people))


def _raid(b: _Builder, olds: list[str], style: str) -> None:
    rng = b.rng
    n = rng.randint(4, 8) if style != "bolunmus" else rng.randint(4, 6)
    if style == "hizli":  # tohumdaki biçim: dakikalar arayla kayıt, ilk mesaja yanıt
        start = T - timedelta(hours=rng.uniform(2, 30))
        times = [start + timedelta(minutes=rng.uniform(0, 45)) for _ in range(n)]
    elif style == "sabirli":  # günlere yayılmış kayıt
        start = T - timedelta(days=rng.uniform(5, 6.5))
        times = [start + timedelta(hours=rng.uniform(0, 110)) for _ in range(n)]
    elif style == "sessiz":  # saatlere yayılmış kayıt, hiç etkileşim yok
        start = T - timedelta(hours=rng.uniform(10, 60))
        times = [start + timedelta(minutes=70 * i + rng.uniform(0, 30)) for i in range(n)]
    else:  # kamufle ya da bölünmüş: bir gün içinde kayıt
        offset = rng.uniform(8, 60)
        start = T - timedelta(hours=offset)
        times = [start + timedelta(hours=rng.uniform(0, min(20, offset - 1))) for _ in range(n)]
    people = [b.account(t, f"baskin_{style}", raider=True) for t in sorted(times)]
    if style == "sessiz":
        return
    if style == "bolunmus":
        half = len(people) // 2
        for part in (people[:half], people[half:]):
            for u in part:
                for v in part:
                    if u != v:
                        b.reply(u, v)
        return
    leader = people[0]
    for u in people[1:]:
        b.reply(u, leader)
        for _ in range(rng.randint(0, 2)):
            b.reply(u, rng.choice(people))
    if style == "kamufle":
        for u in people:
            for _ in range(rng.randint(2, 5)):
                b.reply(u, rng.choice(olds))


RAID_STYLES = ("hizli", "sabirli", "sessiz", "bolunmus", "kamufle")


def generate(count: int, seed: int, *, class_share: float = 0.35,
             styles: tuple[str, ...] = RAID_STYLES) -> list[Scenario]:
    """``count`` senaryo: her birinde eski üyeler ve gerçek yeni gelenler; yaklaşık yarısında bir
    baskın (``styles`` biçimlerinden biri). ``class_share``: birlikte kaydolan gerçek bir grubun
    (sınıf) bulunduğu senaryoların payı. Aynı ``seed`` aynı listeyi üretir."""
    rng = random.Random(seed)
    out = []
    for i in range(count):
        name = f"s{seed}-{i:04d}"
        b = _Builder(name, random.Random(rng.getrandbits(64)))
        olds = _old_members(b, b.rng.randint(25, 120))
        _solo_newcomers(b, olds, b.rng.randint(0, 6))
        if b.rng.random() < class_share:
            _class(b, olds)
        if b.rng.random() < 0.35:
            _announcement(b, olds)
        if b.rng.random() < 0.5:
            _raid(b, olds, b.rng.choice(styles))
        out.append(b.build())
    return out
