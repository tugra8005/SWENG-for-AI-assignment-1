"""Tohumdaki gündelik tartışmanın kendi kuralları (veritabanı gerekmez)."""

import re

from mesveret.domain.oracle import content_check
from mesveret.domain.regulation import Regulation
from mesveret.services import seed, seed_posts


def test_meydan_posts_hit_no_content_rule_keyword():
    """Sert görüş var, kural ihlali yok: Hâtif hiçbir paylaşımda IK-1..3 kelimesi bulmaz."""
    rules = Regulation.defaults().content_rules()
    for posts in seed_posts.MEYDAN_POSTS.values():
        for key, _, _, text, _ in posts:
            check = content_check(list(rules), text, rules)
            assert not any(m.hits for m in check.matches), (key, [m.hits for m in check.matches])


def test_meydan_post_keys_are_unique_and_replies_come_later():
    when: dict[str, tuple[str, float]] = {}
    for topic, posts in seed_posts.MEYDAN_POSTS.items():
        for key, who, days, _, reply_to in posts:
            assert key not in when and who in seed.POOL_NAMES + [n[0] for n in seed.NAMED]
            if reply_to in when:
                assert when[reply_to][0] == topic and when[reply_to][1] > days, key
            when[key] = (topic, days)


def test_mahzen_discussions_fit_between_fillers():
    for question, replies in seed_posts.MAHZEN_MORE.items():
        i = seed.MAHZEN_PROMPTS.index(question)
        author = seed.POOL_NAMES[(i * 7) % len(seed.POOL_NAMES)]
        assert seed.MAHZEN_DISCUSSIONS[i] is replies
        # 10 + 12·6 = 82 dakika: bir sonraki dolgu başlık (90 dakika) açılmadan biter.
        assert len(replies) <= 7, question
        for j, (nick, text) in enumerate(replies, start=1):
            assert nick != author, (question, nick)  # açanın sesi yalnızca "op"
            assert all(int(n) < j for n in re.findall(r"\{(\d+)\}", text)), (question, j)
