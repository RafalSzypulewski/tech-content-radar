from datetime import timedelta

import pytest

from radar.models import RawItem
from radar.prefilter import keep, match_keywords
from tests.conftest import NOW, make_source

KEYWORDS = ["testing", "testowanie", "testy", "QA", "CI/CD", "AI", "sztuczna inteligencja"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Unit Testing in practice", ["testing"]),
        ("TESTING everything", ["testing"]),
        ("Contesting the results", []),  # no match inside a word
        ("Testowanie aplikacji mobilnych", ["testowanie"]),
        ("Testy jednostkowe w Pythonie", ["testy"]),
        ("Testowania nie lubimy", []),  # exact matching: inflected forms don't match
        ("Sztuczna inteligencja w QA", ["QA", "sztuczna inteligencja"]),
        ("Building CI/CD pipelines", ["CI/CD"]),
        ("New AI tools", ["AI"]),
        ("She said hello", []),  # "ai" inside "said"
        ("AI, testing.", ["testing", "AI"]),  # punctuation is a boundary
        ("", []),
    ],
)
def test_match_keywords(text, expected):
    assert match_keywords(text, KEYWORDS) == expected


def _item(age_days: float, matched: list[str]) -> RawItem:
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
        matched_keywords=matched,
    )


def test_keep_fresh_item_with_keyword():
    assert keep(_item(1, ["testing"]), make_source(), NOW)


def test_drop_item_without_keyword():
    assert not keep(_item(1, []), make_source(), NOW)


def test_drop_old_item_even_with_keyword():
    assert not keep(_item(22, ["testing"]), make_source(max_age_days=21), NOW)


def test_always_include_skips_keyword_filter_but_not_age():
    source = make_source(always_include=True)
    assert keep(_item(1, []), source, NOW)
    assert not keep(_item(30, []), source, NOW)
