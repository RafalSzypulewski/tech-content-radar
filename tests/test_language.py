import pytest

from radar.language import detect_lang


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Taming flaky tests in CI. Flaky tests erode trust in the test suite.", "en"),
        ("Show HN: A tool for running flaky tests", "en"),
        ("Automatyzacja testów z Playwright", "pl"),
        ("Testy jednostkowe w Pythonie. Jak pisać czytelne testy w pytest.", "pl"),
        ("Wie man gute Tests schreibt und warum das wichtig ist.", "other"),
    ],
)
def test_detect_lang(text, expected):
    assert detect_lang(text, fallback="en") == expected


@pytest.mark.parametrize("text", ["LLM agents", "v1.56.1", ""])
def test_ambiguous_text_uses_fallback(text):
    assert detect_lang(text, fallback="pl") == "pl"
    assert detect_lang(text, fallback="en") == "en"
