import httpx
import pytest
import respx

from radar.extract import extract_text, needs_extraction
from tests.conftest import FIXTURES

URL = "https://example.com/post"


@pytest.mark.parametrize(
    ("item_type", "text", "expected"),
    [
        ("blog", "", True),
        ("blog", "x" * 499, True),
        ("blog", "x" * 500, False),
        ("video", "", False),
        ("community", "", False),
    ],
)
def test_needs_extraction(item_type, text, expected):
    assert needs_extraction(item_type, text) is expected


@respx.mock
def test_extract_text_from_article():
    respx.get(URL).respond(200, html=(FIXTURES / "article.html").read_text(encoding="utf-8"))

    with httpx.Client() as client:
        text = extract_text(client, URL)

    assert "Flaky tests erode trust in the suite." in text
    assert "quarantined the flaky tests" in text
    assert "Copyright" not in text
    assert "\n" not in text


@respx.mock
@pytest.mark.parametrize(
    "response",
    [httpx.Response(404), httpx.ConnectTimeout("timed out"), httpx.Response(200, html="")],
)
def test_extract_text_failures_return_none(response):
    respx.get(URL).mock(side_effect=[response])

    with httpx.Client() as client:
        assert extract_text(client, URL) is None


@respx.mock
def test_extract_uses_10s_timeout():
    route = respx.get(URL).respond(404)

    with httpx.Client() as client:
        extract_text(client, URL)

    assert route.calls[0].request.extensions["timeout"]["read"] == 10
