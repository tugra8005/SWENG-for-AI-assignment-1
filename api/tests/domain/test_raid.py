from datetime import UTC, datetime, timedelta
from itertools import combinations

from mesveret.domain.raid import detect_raids
from mesveret.domain.regulation import Regulation

AT = datetime(2026, 10, 4, 17, 0, tzinfo=UTC)
REG = Regulation.defaults()


def clique(users, w=1.0):
    return {(a, b): w for a, b in combinations(users, 2)}


def joined(users, start, step=timedelta(minutes=20)):
    return {u: start + i * step for i, u in enumerate(users)}


RAIDERS = ["r1", "r2", "r3", "r4", "r5"]


def test_new_dense_cluster_joined_in_quick_succession_is_flagged():
    j = joined(RAIDERS, AT - timedelta(hours=10))
    [cluster] = detect_raids(j, clique(RAIDERS), AT, REG)
    assert cluster.members == frozenset(RAIDERS)
    assert cluster.density == 1
    assert "baskın" in cluster.reason


def test_old_accounts_are_not_candidates_even_if_dense():
    j = joined(RAIDERS, AT - timedelta(days=30))
    assert detect_raids(j, clique(RAIDERS), AT, REG) == []


def test_sparse_new_accounts_are_not_flagged():
    path = {(RAIDERS[i], RAIDERS[i + 1]): 1.0 for i in range(4)}  # yoğunluk 4/10
    assert detect_raids(joined(RAIDERS, AT - timedelta(hours=10)), path, AT, REG) == []


def test_small_clusters_are_not_flagged():
    three = RAIDERS[:3]
    assert detect_raids(joined(three, AT - timedelta(hours=5)), clique(three), AT, REG) == []


def test_joins_spread_over_more_than_the_interval_are_not_flagged():
    j = joined(RAIDERS, AT - timedelta(days=6), step=timedelta(hours=10))  # 40 saat yayılım
    assert detect_raids(j, clique(RAIDERS), AT, REG) == []


def test_weak_interactions_are_not_edges_but_both_directions_add_up():
    j = joined(RAIDERS, AT - timedelta(hours=10))
    weak = clique(RAIDERS, w=0.5)
    assert detect_raids(j, weak, AT, REG) == []
    both = {**weak, **{(b, a): 0.5 for a, b in weak}}
    assert len(detect_raids(j, both, AT, REG)) == 1


def test_interactions_with_established_members_do_not_join_the_cluster():
    j = {**joined(RAIDERS, AT - timedelta(hours=10)), "eski": AT - timedelta(days=200)}
    edges = {**clique(RAIDERS), ("r1", "eski"): 5.0}
    [cluster] = detect_raids(j, edges, AT, REG)
    assert "eski" not in cluster.members


def test_two_separate_clusters_are_both_flagged():
    other = ["s1", "s2", "s3", "s4"]
    j = {**joined(RAIDERS, AT - timedelta(hours=10)), **joined(other, AT - timedelta(hours=3))}
    clusters = detect_raids(j, {**clique(RAIDERS), **clique(other)}, AT, REG)
    assert {c.members for c in clusters} == {frozenset(RAIDERS), frozenset(other)}


def test_thresholds_come_from_regulation():
    reg = Regulation({**REG.values, "baskin_min_kume": {"deger": 6}})
    j = joined(RAIDERS, AT - timedelta(hours=10))
    assert detect_raids(j, clique(RAIDERS), AT, reg) == []


def test_accounts_joining_after_snapshot_are_ignored():
    j = joined(RAIDERS, AT + timedelta(hours=1))
    assert detect_raids(j, clique(RAIDERS), AT, REG) == []
