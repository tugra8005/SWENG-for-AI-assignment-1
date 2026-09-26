from mesveret.domain.shade import shade_id

KEY = b"sunucu-anahtari"


def test_shade_id_is_eight_hex_characters():
    sid = shade_id(KEY, "user-1", "thread-1")
    assert len(sid) == 8
    int(sid, 16)


def test_same_user_same_thread_is_stable():
    assert shade_id(KEY, "user-1", "thread-1") == shade_id(KEY, "user-1", "thread-1")


def test_different_users_in_same_thread_differ():
    assert shade_id(KEY, "user-1", "thread-1") != shade_id(KEY, "user-2", "thread-1")


def test_shade_ids_do_not_match_across_threads():
    users = [f"user-{i}" for i in range(200)]
    first = {u: shade_id(KEY, u, "thread-1") for u in users}
    second = {u: shade_id(KEY, u, "thread-2") for u in users}
    assert all(first[u] != second[u] for u in users)
    assert not set(first.values()) & set(second.values())


def test_ids_depend_on_the_server_key():
    assert shade_id(KEY, "user-1", "thread-1") != shade_id(b"baska", "user-1", "thread-1")


def test_concatenation_is_unambiguous():
    # "user-1" + "1:x" ile "user-11" + ":x" aynı birleşimi üretmemeli.
    assert shade_id(KEY, "ab", "c") != shade_id(KEY, "a", "bc")
