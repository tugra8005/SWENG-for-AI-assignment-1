from datetime import UTC, datetime, timedelta

from mesveret.domain.cellar import (
    ThreadState,
    cellar_thread_refs,
    lifetime_remaining,
    post_refs,
    reveal_passes,
    should_bump,
    threads_to_prune,
)
from mesveret.domain.regulation import Regulation

REG = Regulation.defaults()
T = datetime(2026, 9, 29, tzinfo=UTC)


def test_reveal_needs_more_than_half_of_the_electorate():
    ratio = REG.ratio("mahzen_ifsa_esigi")
    assert reveal_passes(3, 5, ratio)
    assert not reveal_passes(2, 4, ratio)
    assert reveal_passes(3, 4, ratio)
    assert not reveal_passes(0, 0, ratio)


def test_reply_bumps_until_the_bump_limit_is_reached():
    assert should_bump(replies_before=298, limit=300)
    assert should_bump(replies_before=299, limit=300)  # 300. yanıt yükseltir
    assert not should_bump(replies_before=300, limit=300)


def test_oldest_living_threads_beyond_capacity_are_pruned():
    threads = [ThreadState(i, T + timedelta(minutes=i), frozen=False) for i in range(5)]
    assert threads_to_prune(threads, capacity=3) == [1, 0]


def test_frozen_threads_are_outside_the_capacity_pool():
    threads = [
        ThreadState(1, T, frozen=True),
        ThreadState(2, T + timedelta(minutes=1), frozen=False),
        ThreadState(3, T + timedelta(minutes=2), frozen=False),
    ]
    assert threads_to_prune(threads, capacity=2) == []


def test_lifetime_decreases_towards_the_bottom():
    assert lifetime_remaining(rank=0, capacity=100) == 1.0
    assert lifetime_remaining(rank=50, capacity=100) == 0.5
    assert lifetime_remaining(rank=99, capacity=100) == 0.01
    assert lifetime_remaining(rank=150, capacity=100) == 0.0


def test_cellar_links_are_detected():
    assert cellar_thread_refs("bkz. /mahzen/42 ve mahzen/7") == {42, 7}
    assert cellar_thread_refs("http://localhost:8081/mahzen/13?x=1") == {13}
    assert cellar_thread_refs("mahzende konuştuk") == set()


def test_post_references():
    assert post_refs(">>12 katılıyorum, >>13") == {12, 13}
    assert post_refs("a >> b") == set()
