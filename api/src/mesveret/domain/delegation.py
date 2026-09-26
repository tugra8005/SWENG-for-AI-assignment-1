"""Havale: çözümleme, miras, zincir ve döngü kontrolü (R4).

Havaleler ``{(kullanıcı, alan_id | None): temsilci}`` sözlüğüyle temsil edilir; her
kullanıcının alan başına (ve genel olarak) en fazla bir çıkan havalesi vardır.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from mesveret.domain.ontology import AreaTree

Delegations = Mapping[tuple[str, str | None], str]


class DelegationError(ValueError):
    pass


class SelfDelegationError(DelegationError):
    def __init__(self) -> None:
        super().__init__("Kendinize havale veremezsiniz.")


class DelegationCycleError(DelegationError):
    def __init__(self, area_id: str | None, path: list[str]):
        self.area_id = area_id
        self.path = path
        super().__init__("Bu havale bir döngü oluşturur.")


def effective_delegate(
    delegations: Delegations, user: str, area_id: str | None, tree: AreaTree
) -> str | None:
    """Kullanıcının bu alandaki etkin temsilcisi.

    Alan havalesi alandan köke doğru aranır (alt alanlar üst alanın havalesini miras
    alır, daha özeli varsa o geçerlidir); alan havalesi yoksa genel havale uygulanır.
    Alansız öneriler (YONETMELIK) yalnızca genel havaleye bakar.
    """
    if area_id is not None:
        for a in tree.area_ancestors(area_id):
            target = delegations.get((user, a))
            if target is not None:
                return target
    return delegations.get((user, None))


def can_vote(delegations: Delegations, user: str, area_id: str | None, tree: AreaTree) -> bool:
    """Havale eden kişi o alanda oy kullanamaz."""
    return effective_delegate(delegations, user, area_id, tree) is None


def _walk(
    delegations: Delegations, start: str, area_id: str | None, tree: AreaTree
) -> tuple[str, list[str], bool]:
    """Zinciri izler: (son kişi, yol, döngü var mı)."""
    path = [start]
    seen = {start}
    current = start
    while True:
        nxt = effective_delegate(delegations, current, area_id, tree)
        if nxt is None:
            return current, path, False
        path.append(nxt)
        if nxt in seen:
            return nxt, path, True
        seen.add(nxt)
        current = nxt


def resolve_terminal(
    delegations: Delegations, user: str, area_id: str | None, tree: AreaTree
) -> tuple[str, list[str]]:
    terminal, path, cyclic = _walk(delegations, user, area_id, tree)
    if cyclic:
        raise DelegationCycleError(area_id, path)
    return terminal, path


def check_new_delegation(
    delegations: Delegations,
    user: str,
    target: str,
    area_id: str | None,
    tree: AreaTree,
) -> None:
    """Yeni havaleyi kaydetmeden önce döngü kontrolü.

    Kullanıcının etkin temsilcisi yalnızca verilen alanda değil, mirasla o alanın tüm
    alt ağacında (genel havalede tüm alanlarda ve alansız durumda) değişebilir. Bu
    yüzden her etkilenen alan için zincir yeni duruma göre izlenir.
    """
    if user == target:
        raise SelfDelegationError()
    proposed = dict(delegations)
    proposed[(user, area_id)] = target

    affected: list[str | None]
    if area_id is None:
        affected = [None, *tree.all_area_ids_bfs()]
    else:
        affected = list(tree.area_descendants_bfs(area_id))

    for a in affected:
        _, path, cyclic = _walk(proposed, user, a, tree)
        if cyclic and path[-1] == user:
            raise DelegationCycleError(a, path)


def resolve_all(
    delegations: Delegations, area_id: str | None, tree: AreaTree, users: Iterable[str]
) -> dict[str, str]:
    """Anlık görüntü için: her kullanıcıyı zincirinin son kişisine eşler.

    Zincir listede olmayan (ör. o öneride seçmen olmayan) kişilerin üzerinden de geçer.
    """
    return {u: resolve_terminal(delegations, u, area_id, tree)[0] for u in users}
