"""Keyword score + age pre-filter applied during collection."""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from radar.config import KeywordGroup, Source
from radar.models import RawItem


@dataclass(frozen=True)
class Term:
    """One keyword with the weight it scores and its compiled pattern."""

    keyword: str
    weight: int
    anchored: bool
    pattern: re.Pattern


def build_terms(groups: list[KeywordGroup]) -> list[Term]:
    """Compile keyword groups into terms, longest first.

    A keyword listed in several groups keeps only its highest-weight entry.
    """
    best: dict[str, Term] = {}
    for group in groups:
        for kw in group.keywords:
            key = kw.lower()
            if key in best and best[key].weight >= group.weight:
                continue
            # Lookarounds instead of \b so keywords like "CI/CD" or "C++" work too.
            pattern = re.compile(rf"(?<!\w){re.escape(kw)}(?!\w)", re.IGNORECASE)
            best[key] = Term(kw, group.weight, group.requires_anchor, pattern)
    return sorted(best.values(), key=lambda t: -len(t.keyword))


def keyword_score(text: str, terms: list[Term]) -> tuple[int, list[str]]:
    """Sum of the weights of terms found in `text`, and those keywords in text order.

    Each term counts once. Terms are tried longest first and a match may not overlap an
    earlier one, so "OWASP Top 10" hides "OWASP" there. Anchored terms only count when
    a non-anchored term matched too.
    """
    taken: list[tuple[int, int]] = []
    hits: list[tuple[int, Term]] = []
    for term in terms:
        for m in term.pattern.finditer(text):
            if all(m.end() <= start or m.start() >= end for start, end in taken):
                taken.append(m.span())
                hits.append((m.start(), term))
                break
    if not any(not term.anchored for _, term in hits):
        return 0, []
    hits.sort(key=lambda hit: hit[0])
    return sum(term.weight for _, term in hits), [term.keyword for _, term in hits]


def is_fresh(item: RawItem, max_age_days: int, now: datetime) -> bool:
    """True if the item was published less than `max_age_days` ago."""
    return now - item.published_at < timedelta(days=max_age_days)


def keep(item: RawItem, source: Source, now: datetime, score: int, min_score: int) -> bool:
    """Apply the pre-filter: fresh AND (always_include source OR score >= min_score).

    Hacker News items must also have at least `min_points`.
    """
    if source.kind == "hackernews" and item.engagement.get("points", 0) < source.min_points:
        return False
    return is_fresh(item, source.max_age_days, now) and (
        source.always_include or score >= min_score
    )
