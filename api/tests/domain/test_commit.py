import hashlib

from mesveret.domain.commit import canonical_json, make_commit, new_salt, verify_commit

VOTE = {"oturum": 3, "oneri": 17, "secmen": "u-1", "secim": "EVET"}


def test_canonical_json_ignores_key_order_and_keeps_turkish_characters():
    a = canonical_json({"b": 1, "a": "ş"})
    b = canonical_json({"a": "ş", "b": 1})
    assert a == b == '{"a":"ş","b":1}'.encode()


def test_commit_is_sha256_of_vote_and_salt():
    salt = "00ff"
    expected = hashlib.sha256(canonical_json(VOTE) + salt.encode()).hexdigest()
    assert make_commit(VOTE, salt) == expected


def test_commit_verifies_only_with_same_vote_and_salt():
    salt = new_salt()
    c = make_commit(VOTE, salt)
    assert verify_commit(c, VOTE, salt)
    assert not verify_commit(c, {**VOTE, "secim": "HAYIR"}, salt)
    assert not verify_commit(c, VOTE, new_salt())


def test_salts_are_random_and_long():
    salts = {new_salt() for _ in range(100)}
    assert len(salts) == 100
    assert all(len(s) == 64 for s in salts)
