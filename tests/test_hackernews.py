import json
from datetime import UTC, datetime

import httpx
import respx

from radar.collectors.hackernews import API_URL, collect
from tests.conftest import FIXTURES, NOW, make_source


def _hits(name: str) -> dict:
    return json.loads((FIXTURES / "api" / name).read_text(encoding="utf-8"))


def _source():
    return make_source(
        id="hn",
        name="Hacker News",
        kind="hackernews",
        type="community",
        url=None,
        query=["testing", "LLM"],
        min_points=30,
    )


@respx.mock
def test_collect_unions_queries_and_parses_hits():
    route = respx.get(API_URL)
    route.side_effect = [
        httpx.Response(200, json=_hits("hn_testing.json")),
        httpx.Response(200, json=_hits("hn_llm.json")),
    ]

    with httpx.Client() as client:
        items = collect(client, _source(), NOW)

    # 50000001 is returned by both queries; the hit without a title is skipped
    assert [i.title for i in items] == [
        "Why our test suite got 10x faster",
        "Ask HN: How do you deal with flaky end-to-end testing?",
        "Using an LLM to generate test cases",
    ]
    story, ask, _ = items
    assert story.canonical_url == "https://engineering.example.com/faster-tests"
    assert story.engagement == {"points": 120, "comments": 45}
    assert story.published_at == datetime(2026, 10, 28, 9, 15, tzinfo=UTC)
    assert story.author == "alice"
    assert (story.source_id, story.type) == ("hn", "community")
    assert ask.url == "https://news.ycombinator.com/item?id=50000002"
    assert ask.text == 'Our Playwright suite fails "randomly" about 5% of the time.'


@respx.mock
def test_collect_sends_query_params():
    route = respx.get(API_URL).respond(200, json={"hits": []})

    with httpx.Client() as client:
        collect(client, _source(), NOW)

    params = [call.request.url.params for call in route.calls]
    assert [p["query"] for p in params] == ["testing", "LLM"]
    cutoff = int(NOW.timestamp()) - 21 * 86400
    assert params[0]["numericFilters"] == f"created_at_i>{cutoff},points>=30"
    assert params[0]["tags"] == "story"
