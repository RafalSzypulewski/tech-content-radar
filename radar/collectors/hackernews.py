"""Hacker News collector using the Algolia search API."""

from datetime import datetime, timedelta

import httpx

from radar.canonical import canonicalize, item_id
from radar.collectors.rss import MAX_TEXT_CHARS, html_to_text
from radar.config import Source
from radar.models import RawItem

API_URL = "https://hn.algolia.com/api/v1/search_by_date"
HITS_PER_QUERY = 100


def parse_hit(hit: dict, source: Source, fetched_at: datetime) -> RawItem:
    """Turn one Algolia hit into a raw item. Ask HN posts link to the HN thread."""
    url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}"
    canonical = canonicalize(url)
    return RawItem(
        id=item_id(canonical),
        url=url,
        canonical_url=canonical,
        title=hit["title"],
        source_id=source.id,
        source_name=source.name,
        type=source.type,
        lang=source.lang,
        published_at=datetime.fromisoformat(hit["created_at"]),
        fetched_at=fetched_at,
        author=hit.get("author"),
        text=html_to_text(hit.get("story_text") or "")[:MAX_TEXT_CHARS],
        engagement={"points": hit.get("points") or 0, "comments": hit.get("num_comments") or 0},
    )


def collect(client: httpx.Client, source: Source, fetched_at: datetime) -> list[RawItem]:
    """Run each query and return the union of matching stories."""
    cutoff = int((fetched_at - timedelta(days=source.max_age_days)).timestamp())
    items: dict[str, RawItem] = {}
    for query in source.query:
        response = client.get(
            API_URL,
            params={
                "query": query,
                "tags": "story",
                "numericFilters": f"created_at_i>{cutoff},points>={source.min_points}",
                "hitsPerPage": HITS_PER_QUERY,
            },
        )
        response.raise_for_status()
        for hit in response.json()["hits"]:
            if hit.get("title"):
                item = parse_hit(hit, source, fetched_at)
                items.setdefault(item.id, item)
    return list(items.values())
