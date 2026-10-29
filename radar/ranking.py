"""Ranking. M3: pre-rank before the LLM step."""

from dataclasses import dataclass
from datetime import datetime

from radar.embeddings import relevance
from radar.models import RawItem

DEFAULT_TRUST = 0.5  # for items whose source is no longer in sources.yaml


@dataclass
class Ranked:
    """An item with its pre-rank score and the parts it is made of."""

    item: RawItem
    score: float
    relevance: float
    freshness: float
    trust: float


def freshness(published_at: datetime, now: datetime, half_life_days: float) -> float:
    """0.5 ** (age_days / half_life); 1.0 for items dated in the future."""
    age_days = max(0.0, (now - published_at).total_seconds() / 86400)
    return 0.5 ** (age_days / half_life_days)


def pre_score(relevance: float, freshness: float, trust: float) -> float:
    """pre = 0.6·relevance + 0.25·freshness + 0.15·trust."""
    return 0.6 * relevance + 0.25 * freshness + 0.15 * trust


def pre_rank(
    items: list[RawItem],
    vectors: dict[str, list[float]],
    profile_vectors: list[list[float]],
    trust_by_source: dict[str, float],
    now: datetime,
    half_life_days: float,
    exclude_ids: set[str],
    limit: int,
) -> list[Ranked]:
    """The top `limit` items not in `exclude_ids` (e.g. already scored), best first."""
    ranked = []
    for item in items:
        if item.id in exclude_ids:
            continue
        rel = relevance(vectors[item.id], profile_vectors)
        fresh = freshness(item.published_at, now, half_life_days)
        trust = trust_by_source.get(item.source_id, DEFAULT_TRUST)
        ranked.append(Ranked(item, pre_score(rel, fresh, trust), rel, fresh, trust))
    ranked.sort(key=lambda r: (-r.score, r.item.id))
    return ranked[:limit]
