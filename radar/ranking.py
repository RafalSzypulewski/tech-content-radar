"""Ranking: pre-rank before the LLM step, final score + clustering for the digest."""

import math
from dataclasses import dataclass, field
from datetime import datetime

from radar.embeddings import cosine, relevance
from radar.models import Enrichment, RawItem

DEFAULT_TRUST = 0.5  # for items whose source is no longer in sources.yaml
ENGAGEMENT_CAP = 1000  # points + comments (or reactions + comments) that count as "max"
NOVELTY_BEST = 1.0
NOVELTY_RELATED = 0.3


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


def engagement_norm(engagement: dict[str, int]) -> float:
    """Sum of engagement counts, log-scaled to 0..1 (1000+ = 1.0, none = 0)."""
    total = sum(engagement.values())
    return min(1.0, math.log1p(max(0, total)) / math.log1p(ENGAGEMENT_CAP))


def quality_mix(quality: int, trust: float, engagement: float) -> float:
    """quality_mix = 0.5·(quality/10) + 0.3·trust + 0.2·engagement_norm."""
    return 0.5 * (quality / 10) + 0.3 * trust + 0.2 * engagement


def final_score(
    relevance: int, quality_mix: float, freshness: float, novelty: float, boost: float = 0.0
) -> float:
    """final = 0.45·(relevance/10) + 0.25·quality_mix + 0.15·freshness + 0.15·novelty + boost."""
    return (
        0.45 * (relevance / 10) + 0.25 * quality_mix + 0.15 * freshness + 0.15 * novelty + boost
    )


@dataclass
class Final:
    """A digest entry: the best item of a cluster plus the related items under it."""

    item: RawItem
    enrichment: Enrichment
    score: float
    related: list["Final"] = field(default_factory=list)


def cluster(
    ordered_ids: list[str], vectors: dict[str, list[float]], threshold: float
) -> dict[str, list[str]]:
    """Greedy clustering: walk ids best-first; each joins the first leader it is similar to.

    Returns leader id -> member ids (leader not included), leaders in input order.
    """
    clusters: dict[str, list[str]] = {}
    for item_id in ordered_ids:
        leader = next(
            (lead for lead in clusters if cosine(vectors[item_id], vectors[lead]) >= threshold),
            None,
        )
        if leader is None:
            clusters[item_id] = []
        else:
            clusters[leader].append(item_id)
    return clusters


def feedback_boost(
    vector: list[float],
    liked_vectors: list[list[float]],
    skipped_vectors: list[list[float]],
) -> float:
    """+0.1·max_sim(kept/written) − 0.1·max_sim(skipped); 0 without feedback.

    Similarities are clamped to 0..1 so dissimilar feedback never flips the sign.
    """
    return 0.1 * relevance(vector, liked_vectors) - 0.1 * relevance(vector, skipped_vectors)


def final_rank(
    items: list[RawItem],
    scores: dict[str, Enrichment],
    vectors: dict[str, list[float]],
    trust_by_source: dict[str, float],
    now: datetime,
    half_life_days: float,
    cluster_threshold: float,
    liked_vectors: list[list[float]] = (),
    skipped_vectors: list[list[float]] = (),
) -> list[Final]:
    """Score items, cluster near-duplicates and return the cluster leaders, best first.

    The best item of a cluster gets novelty 1.0, the others 0.3 and appear only as
    `related` under it. `liked_vectors` / `skipped_vectors` are the embeddings of items
    marked keep or write / skip in earlier digests.
    """
    base: dict[str, float] = {}
    for item in items:
        e = scores[item.id]
        mix = quality_mix(
            e.quality,
            trust_by_source.get(item.source_id, DEFAULT_TRUST),
            engagement_norm(item.engagement),
        )
        fresh = freshness(item.published_at, now, half_life_days)
        boost = feedback_boost(vectors[item.id], list(liked_vectors), list(skipped_vectors))
        base[item.id] = final_score(e.relevance, mix, fresh, novelty=0.0, boost=boost)

    by_id = {item.id: item for item in items}
    ordered = sorted(base, key=lambda i: (-base[i], i))
    entries = []
    for leader, members in cluster(ordered, vectors, cluster_threshold).items():
        entry = Final(by_id[leader], scores[leader], base[leader] + 0.15 * NOVELTY_BEST)
        entry.related = [
            Final(by_id[m], scores[m], base[m] + 0.15 * NOVELTY_RELATED) for m in members
        ]
        entries.append(entry)
    entries.sort(key=lambda e: (-e.score, e.item.id))
    return entries
