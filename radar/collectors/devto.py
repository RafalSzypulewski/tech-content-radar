"""dev.to collector using the public articles API."""

import time
from datetime import datetime

import httpx

from radar.canonical import canonicalize, item_id
from radar.config import Source
from radar.models import RawItem

API_URL = "https://dev.to/api/articles"
PER_TAG = 30
MAX_RETRY_WAIT = 10


def parse_article(article: dict, source: Source, fetched_at: datetime) -> RawItem:
    """Turn one dev.to article into a raw item."""
    canonical = canonicalize(article["url"])
    return RawItem(
        id=item_id(canonical),
        url=article["url"],
        canonical_url=canonical,
        title=article["title"],
        source_id=source.id,
        source_name=source.name,
        type=source.type,
        lang=source.lang,
        published_at=datetime.fromisoformat(article["published_at"]),
        fetched_at=fetched_at,
        author=(article.get("user") or {}).get("name"),
        text=article.get("description") or "",
        engagement={
            "reactions": article.get("public_reactions_count") or 0,
            "comments": article.get("comments_count") or 0,
        },
    )


def _get(client: httpx.Client, params: dict) -> httpx.Response:
    """GET the API, retrying once after a 429 (dev.to rate-limits quick bursts)."""
    response = client.get(API_URL, params=params)
    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After", "")
        time.sleep(min(int(retry_after), MAX_RETRY_WAIT) if retry_after.isdigit() else 2)
        response = client.get(API_URL, params=params)
    response.raise_for_status()
    return response


def collect(client: httpx.Client, source: Source, fetched_at: datetime) -> list[RawItem]:
    """Fetch the most popular articles per tag within `max_age_days`."""
    items: dict[str, RawItem] = {}
    for tag in source.tags:
        response = _get(client, {"tag": tag, "top": source.max_age_days, "per_page": PER_TAG})
        for article in response.json():
            item = parse_article(article, source, fetched_at)
            items.setdefault(item.id, item)
    return list(items.values())
