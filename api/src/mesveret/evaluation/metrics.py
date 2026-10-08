"""Sınıflandırma metrikleri: karışıklık matrisi, kesinlik, duyarlılık, Fβ ve hata maliyeti.

Birim hesaptır: her seçmen için "baskıncı mı?" sorusu. Pozitif sınıf baskıncıdır.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Confusion:
    tp: int = 0  # baskıncı, işaretlendi
    fn: int = 0  # baskıncı, kaçtı
    fp: int = 0  # gerçek üye, yanlışlıkla işaretlendi (oy hakkını o oturumda kaybetti)
    tn: int = 0  # gerçek üye, işaretlenmedi

    def __add__(self, other: Confusion) -> Confusion:
        return Confusion(self.tp + other.tp, self.fn + other.fn, self.fp + other.fp,
                         self.tn + other.tn)

    @property
    def total(self) -> int:
        return self.tp + self.fn + self.fp + self.tn

    @property
    def accuracy(self) -> float:
        return (self.tp + self.tn) / self.total if self.total else 0.0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    def f_beta(self, beta: float = 1.0) -> float:
        p, r = self.precision, self.recall
        b2 = beta * beta
        return (1 + b2) * p * r / (b2 * p + r) if p + r else 0.0

    @property
    def f1(self) -> float:
        return self.f_beta(1.0)

    def cost(self, c_fn: float, c_fp: float) -> float:
        return c_fn * self.fn + c_fp * self.fp


def confusion(flagged: set[str], truth: set[str], population: set[str]) -> Confusion:
    return Confusion(
        tp=len(flagged & truth), fn=len(truth - flagged), fp=len(flagged - truth),
        tn=len(population - flagged - truth),
    )


def report(c: Confusion, *, c_fn: float, c_fp: float) -> dict[str, float | int]:
    return {"dp": c.tp, "yn": c.fn, "yp": c.fp, "dn": c.tn,
            "dogruluk": round(c.accuracy, 4), "kesinlik": round(c.precision, 4),
            "duyarlilik": round(c.recall, 4), "f1": round(c.f1, 4),
            "f2": round(c.f_beta(2), 4), "f05": round(c.f_beta(0.5), 4),
            "maliyet": round(c.cost(c_fn, c_fp), 2)}
