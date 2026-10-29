import json
from datetime import UTC, datetime

import httpx
import pytest
import respx

from radar.collectors.devto import API_URL, collect
from tests.conftest import FIXTURES, NOW, make_source


def _articles(name: str) -> list:
    return json.loads((FIXTURES / "api" / name).read_text(encoding="utf-8"))


def _source():
    return make_source(
        id="devto", name="dev.to", kind="devto", type="community", url=None, tags=["testing", "qa"]
    )


@respx.mock
def test_collect_unions_tags_and_parses_articles():
    route = respx.get(API_URL)
    route.side_effect = [
        httpx.Response(200, json=_articles("devto_testing.json")),
        httpx.Response(200, json=_articles("devto_qa.json")),
    ]

    with httpx.Client() as client:
        items = collect(client, _source(), NOW)

    assert [i.title for i in items] == [
        "Contract testing with Pact in 10 minutes",
        "Testy jednostkowe w Pythonie krok po kroku",
        "A QA checklist for releases",
    ]
    first = items[0]
    assert first.canonical_url == "https://dev.to/someone/contract-testing-with-pact-1abc"
    assert first.text == "A hands-on intro to consumer-driven contract testing."
    assert first.engagement == {"reactions": 127, "comments": 49}
    assert first.published_at == datetime(2026, 10, 24, 18, 12, 54, tzinfo=UTC)
    assert first.author == "Some One"
    assert items[2].author is None
    assert items[2].text == ""

    params = [call.request.url.params for call in route.calls]
    assert [(p["tag"], p["top"]) for p in params] == [("testing", "21"), ("qa", "21")]


@respx.mock
def test_retries_once_after_429(mocker):
    sleep = mocker.patch("radar.collectors.devto.time.sleep")
    route = respx.get(API_URL)
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "3"}),
        httpx.Response(200, json=_articles("devto_qa.json")),
    ]

    with httpx.Client() as client:
        items = collect(client, make_source(kind="devto", url=None, tags=["qa"]), NOW)

    sleep.assert_called_once_with(3)
    assert len(items) == 2


@respx.mock
def test_second_429_raises(mocker):
    mocker.patch("radar.collectors.devto.time.sleep")
    respx.get(API_URL).respond(429)

    with httpx.Client() as client, pytest.raises(httpx.HTTPStatusError):
        collect(client, make_source(kind="devto", url=None, tags=["qa"]), NOW)
