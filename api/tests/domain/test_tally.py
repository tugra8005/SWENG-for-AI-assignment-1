from mesveret.domain.regulation import Regulation
from mesveret.domain.tally import tally_approval, tally_binary

REG = Regulation.defaults()


def test_chain_a_b_c_gives_c_weight_three():
    resolved = {"a": "c", "b": "c", "c": "c"}
    t = tally_binary({"c": True}, resolved, eligible={"a", "b", "c"})
    assert t.weights == {"c": 3}
    assert (t.yes, t.no) == (3, 0)


def test_chain_ending_in_non_voter_is_abstention():
    resolved = {"a": "c", "b": "c", "c": "c", "d": "d"}
    t = tally_binary({"d": False}, resolved, eligible={"a", "b", "c", "d"})
    assert (t.yes, t.no) == (0, 1)
    assert t.abstained == {"a", "b", "c"}


def test_only_eligible_delegators_add_weight():
    # a (seçmen) → x (seçmen değil) → c (seçmen): x geçirgen, ağırlığa katkı vermez.
    resolved = {"a": "c", "x": "c", "c": "c"}
    t = tally_binary({"c": True}, resolved, eligible={"a", "c"})
    assert t.weights == {"c": 2}


def test_chain_ending_in_ineligible_user_is_abstention():
    resolved = {"a": "x", "c": "c"}
    t = tally_binary({"c": False}, resolved, eligible={"a", "c"})
    assert t.abstained == {"a"}
    assert t.no == 1


def test_votes_from_delegators_or_ineligible_users_are_ignored():
    resolved = {"a": "c", "c": "c"}
    t = tally_binary({"a": True, "z": True, "c": False}, resolved, eligible={"a", "c"})
    assert (t.yes, t.no) == (0, 2)
    assert t.ignored == {"a", "z"}


def test_abstentions_are_outside_the_denominator():
    resolved = {u: u for u in "abcdefghij"}
    votes = {"a": True, "b": True, "c": True, "d": False}  # 6 kişi çekimser
    t = tally_binary(votes, resolved, eligible=set(resolved))
    assert REG.ratio("basit_cogunluk").passes(t.yes, t.cast)
    assert REG.ratio("yonetmelik_esigi").passes(t.yes, t.cast)


def test_sixty_percent_fails_two_thirds_passes_at_regulation_threshold():
    resolved = {f"u{i}": f"u{i}" for i in range(30)}
    sixty = {f"u{i}": i < 18 for i in range(30)}
    two_thirds = {f"u{i}": i < 20 for i in range(30)}
    ratio = REG.ratio("yonetmelik_esigi")
    t60 = tally_binary(sixty, resolved, set(resolved))
    t67 = tally_binary(two_thirds, resolved, set(resolved))
    assert not ratio.passes(t60.yes, t60.cast)
    assert ratio.passes(t67.yes, t67.cast)


def test_approval_winner_is_highest_weighted_score():
    resolved = {"a": "c", "b": "c", "c": "c", "d": "d", "e": "e"}
    votes = {"c": {"m1"}, "d": {"m2", "m3"}, "e": {"m2"}}
    t = tally_approval(votes, resolved, {"a", "b", "c", "d", "e"}, ["m1", "m2", "m3"])
    assert t.scores == {"m1": 3, "m2": 2, "m3": 1}
    assert t.winner == "m1"
    assert not t.tie


def test_approval_tie_gives_no_winner():
    resolved = {"a": "a", "b": "b"}
    t = tally_approval({"a": {"m1"}, "b": {"m2"}}, resolved, {"a", "b"}, ["m1", "m2"])
    assert t.winner is None
    assert t.tie


def test_approval_with_no_approvals_gives_no_winner():
    resolved = {"a": "a"}
    t = tally_approval({"a": set()}, resolved, {"a"}, ["m1", "m2"])
    assert t.winner is None
    assert not t.tie


def test_approval_ignores_unknown_texts():
    resolved = {"a": "a"}
    t = tally_approval({"a": {"m1", "hayali"}}, resolved, {"a"}, ["m1"])
    assert t.scores == {"m1": 1}
