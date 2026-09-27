from mesveret.services.ledger import NodeReport, compare_nodes

L1, L2, L3 = "http://l1", "http://l2", "http://l3"


def ok(length, hashes):
    return NodeReport(reachable=True, ok=True, length=length, reason=None, hash_at=hashes)


def test_all_equal_is_consistent():
    h = {3: "aaa"}
    result = compare_nodes([L1, L2, L3], {L1: ok(3, h), L2: ok(3, h), L3: ok(3, h)})
    assert result["ok"]
    assert [n["status"] for n in result["nodes"]] == ["tutarli"] * 3


def test_shorter_node_with_same_prefix_is_behind():
    result = compare_nodes(
        [L1, L2], {L1: ok(5, {3: "x", 5: "y"}), L2: ok(3, {3: "x"})}
    )
    node = result["nodes"][1]
    assert node["status"] == "geride"
    assert "2 kayıt" in node["message"]
    assert not result["ok"]


def test_same_length_different_hash_is_inconsistent():
    result = compare_nodes([L1, L2], {L1: ok(5, {5: "x"}), L2: ok(5, {5: "z"})})
    assert result["nodes"][1]["status"] == "tutarsiz"
    assert "#5" in result["nodes"][1]["message"]


def test_broken_integrity_is_reported_with_reason():
    bad = NodeReport(True, False, 2, "Kayıt #3: içerik değiştirilmiş.", {})
    result = compare_nodes([L1, L2], {L1: ok(5, {5: "x"}), L2: bad})
    assert result["nodes"][1]["status"] == "butunluk_bozuk"
    assert "#3" in result["nodes"][1]["message"]


def test_unreachable_node():
    down = NodeReport(False, False, 0, "bağlantı yok", {})
    result = compare_nodes([L1, L2], {L1: ok(1, {1: "x"}), L2: down})
    assert result["nodes"][1]["status"] == "erisilemiyor"


def test_reference_falls_back_when_leader_is_broken():
    bad = NodeReport(True, False, 0, "bozuk", {})
    result = compare_nodes([L1, L2, L3], {L1: bad, L2: ok(3, {3: "q"}), L3: ok(3, {3: "q"})})
    assert [n["status"] for n in result["nodes"]] == ["butunluk_bozuk", "tutarli", "tutarli"]
