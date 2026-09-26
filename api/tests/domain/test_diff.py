from mesveret.domain.diff import word_diff


def test_identical_texts_are_one_equal_chunk():
    assert word_diff("aynı metin", "aynı metin") == [("equal", "aynı metin")]


def test_replaced_word():
    assert word_diff("kırmızı elma", "yeşil elma") == [
        ("delete", "kırmızı"),
        ("insert", "yeşil"),
        ("equal", " elma"),
    ]


def test_appended_sentence():
    assert word_diff("Merhaba.", "Merhaba. Yeni cümle.") == [
        ("equal", "Merhaba."),
        ("insert", " Yeni cümle."),
    ]


def test_chunks_reconstruct_both_texts():
    old, new = "Bir iki üç dört", "Bir üç beş dört altı"
    chunks = word_diff(old, new)
    assert "".join(t for op, t in chunks if op != "insert") == old
    assert "".join(t for op, t in chunks if op != "delete") == new
