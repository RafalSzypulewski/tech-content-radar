from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from radar.config import KeywordGroup, load_topics
from radar.models import RawItem
from radar.prefilter import build_terms, keep, keyword_score
from tests.conftest import NOW, make_source

GROUPS = [
    KeywordGroup(id="core", weight=10, keywords=["QA", "OWASP Top 10", "playwright"]),
    KeywordGroup(id="security", weight=9, keywords=["OWASP", "Playwright"]),
    KeywordGroup(id="general", weight=6, keywords=["testing", "testowanie", "testy", "CI/CD"]),
    KeywordGroup(id="ai", weight=3, keywords=["AI", "sztuczna inteligencja"]),
    KeywordGroup(id="lang", weight=6, requires_anchor=True, keywords=["Python", "Rust"]),
]
TERMS = build_terms(GROUPS)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Unit Testing in practice", (6, ["testing"])),
        ("TESTING everything", (6, ["testing"])),
        ("Contesting the results", (0, [])),  # no match inside a word
        ("Testowanie aplikacji mobilnych", (6, ["testowanie"])),
        ("Testy jednostkowe w Pythonie", (6, ["testy"])),
        ("Testowania nie lubimy", (0, [])),  # exact matching: inflected forms don't match
        ("Sztuczna inteligencja w QA", (13, ["sztuczna inteligencja", "QA"])),
        ("Building CI/CD pipelines", (6, ["CI/CD"])),
        ("New AI tools", (3, ["AI"])),
        ("She said hello", (0, [])),  # "ai" inside "said"
        ("AI, testing.", (9, ["AI", "testing"])),  # punctuation is a boundary
        ("", (0, [])),
    ],
)
def test_keyword_score_matching(text, expected):
    assert keyword_score(text, TERMS) == expected


def test_keyword_counts_once_at_highest_weight():
    # "Playwright" is in core (10) and security (9); repeated mentions count once.
    assert keyword_score("Playwright tips: more Playwright", TERMS) == (10, ["playwright"])


def test_longest_overlapping_keyword_wins():
    assert keyword_score("The OWASP Top 10 list", TERMS) == (10, ["OWASP Top 10"])
    # a separate mention of the shorter keyword still counts
    assert keyword_score("OWASP Top 10 by OWASP", TERMS) == (19, ["OWASP Top 10", "OWASP"])


def test_anchored_keywords_need_a_non_anchored_match():
    assert keyword_score("Python and Rust", TERMS) == (0, [])
    assert keyword_score("testing in Python", TERMS) == (12, ["testing", "Python"])


def test_real_topics_file_scores():
    topics = load_topics(Path(__file__).resolve().parent.parent / "topics.yaml")
    terms = build_terms(topics.keyword_groups)
    assert keyword_score("Visual regression testing with Playwright", terms)[0] >= 10
    assert keyword_score("New AI model released", terms)[0] < 4  # below KEYWORD_MIN_SCORE
    assert keyword_score("AI agents wrote my tests", terms)[0] >= 4
    assert keyword_score("Rust 2.0 is out", terms)[0] == 0


def test_invalid_groups_are_rejected():
    with pytest.raises(ValidationError):
        KeywordGroup(id="x", weight=0, keywords=["a"])
    with pytest.raises(ValidationError):
        KeywordGroup(id="x", weight=5, keywords=[])


def _item(age_days: float, points: int | None = None) -> RawItem:
    return RawItem(
        id="x",
        url="https://example.com/x",
        canonical_url="https://example.com/x",
        title="t",
        source_id="example",
        source_name="Example",
        type="blog",
        lang="en",
        published_at=NOW - timedelta(days=age_days),
        fetched_at=NOW,
        engagement={} if points is None else {"points": points},
    )


def test_keep_fresh_item_at_min_score():
    assert keep(_item(1), make_source(), NOW, score=4, min_score=4)


def test_drop_item_below_min_score():
    assert not keep(_item(1), make_source(), NOW, score=3, min_score=4)


def test_drop_old_item_even_with_score():
    assert not keep(_item(22), make_source(max_age_days=21), NOW, score=10, min_score=4)


def test_always_include_skips_keyword_filter_but_not_age():
    source = make_source(always_include=True)
    assert keep(_item(1), source, NOW, score=0, min_score=4)
    assert not keep(_item(30), source, NOW, score=0, min_score=4)


def test_hackernews_requires_min_points():
    source = make_source(kind="hackernews", type="community", url=None, min_points=30)
    assert keep(_item(1, points=30), source, NOW, score=10, min_score=4)
    assert not keep(_item(1, points=29), source, NOW, score=10, min_score=4)
    assert not keep(_item(1), source, NOW, score=10, min_score=4)


def test_min_points_ignored_for_other_kinds():
    assert keep(_item(1, points=0), make_source(min_points=30), NOW, score=10, min_score=4)
