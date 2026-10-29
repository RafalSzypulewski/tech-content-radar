"""Keyword + age pre-filter applied during collection."""

import re
from datetime import datetime, timedelta

from radar.config import Source
from radar.models import RawItem


def match_keywords(text: str, keywords: list[str]) -> list[str]:
    """Keywords found in `text`, whole-word and case-insensitive."""
    # Lookarounds instead of \b so keywords like "CI/CD" or "C++" work too.
    return [
        kw
        for kw in keywords
        if re.search(rf"(?<!\w){re.escape(kw)}(?!\w)", text, flags=re.IGNORECASE)
    ]


def is_fresh(item: RawItem, max_age_days: int, now: datetime) -> bool:
    """True if the item was published less than `max_age_days` ago."""
    return now - item.published_at < timedelta(days=max_age_days)


def keep(item: RawItem, source: Source, now: datetime) -> bool:
    """Apply the pre-filter: fresh AND (always_include source OR a keyword matched).

    Hacker News items must also have at least `min_points`.
    """
    if source.kind == "hackernews" and item.engagement.get("points", 0) < source.min_points:
        return False
    return is_fresh(item, source.max_age_days, now) and (
        source.always_include or bool(item.matched_keywords)
    )
