from datetime import timedelta

import pytest

from radar.models import Enrichment
from radar.ranking import (
    cluster,
    engagement_norm,
    feedback_boost,
    final_rank,
    final_score,
    freshness,
    pre_rank,
    pre_score,
    quality_mix,
)
from tests.conftest import NOW
from tests.test_store import _item


@pytest.mark.parametrize(
    ("age_days", "expected"),
    [(0, 1.0), (7, 0.5), (14, 0.25), (3.5, 0.7071), (-1, 1.0)],
)
def test_freshness(age_days, expected):
    published = NOW - timedelta(days=age_days)
    assert freshness(published, NOW, half_life_days=7) == pytest.approx(expected, abs=1e-4)


def test_pre_score_weights():
    assert pre_score(1, 0, 0) == pytest.approx(0.6)
    assert pre_score(0, 1, 0) == pytest.approx(0.25)
    assert pre_score(0, 0, 1) == pytest.approx(0.15)
    assert pre_score(0.5, 0.5, 0.5) == pytest.approx(0.5)


def _aged(item_id: str, age_days: float, source_id: str = "example"):
    return _item(item_id).model_copy(
        update={"published_at": NOW - timedelta(days=age_days), "source_id": source_id}
    )


def _rank(items, vectors, exclude=(), limit=10, trust=None):
    return pre_rank(
        items,
        vectors,
        profile_vectors=[[1.0, 0.0]],
        trust_by_source=trust or {},
        now=NOW,
        half_life_days=7,
        exclude_ids=set(exclude),
        limit=limit,
    )


def test_relevant_item_beats_fresh_irrelevant_item():
    items = [_aged("fresh-off-topic", 0), _aged("old-on-topic", 14)]
    vectors = {"fresh-off-topic": [0.0, 1.0], "old-on-topic": [1.0, 0.0]}

    ranked = _rank(items, vectors)

    assert [r.item.id for r in ranked] == ["old-on-topic", "fresh-off-topic"]
    top = ranked[0]
    assert (top.relevance, top.freshness, top.trust) == pytest.approx((1.0, 0.25, 0.5))
    assert top.score == pytest.approx(0.6 + 0.25 * 0.25 + 0.15 * 0.5)


def test_trust_from_source_with_default_for_unknown():
    items = [_aged("a", 0, "trusted"), _aged("b", 0, "removed-source")]
    vectors = {"a": [1.0, 0.0], "b": [1.0, 0.0]}

    ranked = _rank(items, vectors, trust={"trusted": 0.9})

    assert [(r.item.id, r.trust) for r in ranked] == [("a", 0.9), ("b", 0.5)]


def test_excluded_items_and_limit():
    items = [_aged(i, n) for n, i in enumerate(["a", "b", "c", "d"])]
    vectors = {i.id: [1.0, 0.0] for i in items}

    ranked = _rank(items, vectors, exclude={"a"}, limit=2)

    assert [r.item.id for r in ranked] == ["b", "c"]


# --- final score -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("engagement", "expected"),
    [({}, 0.0), ({"points": 0}, 0.0), ({"points": 1000}, 1.0), ({"points": 5000}, 1.0),
     ({"points": 30, "comments": 1}, 0.5016)],
)
def test_engagement_norm(engagement, expected):
    assert engagement_norm(engagement) == pytest.approx(expected, abs=1e-4)


def test_quality_mix_weights():
    assert quality_mix(10, 0, 0) == pytest.approx(0.5)
    assert quality_mix(0, 1, 0) == pytest.approx(0.3)
    assert quality_mix(0, 0, 1) == pytest.approx(0.2)


def test_final_score_weights():
    assert final_score(10, 0, 0, 0) == pytest.approx(0.45)
    assert final_score(0, 1, 0, 0) == pytest.approx(0.25)
    assert final_score(0, 0, 1, 0) == pytest.approx(0.15)
    assert final_score(0, 0, 0, 1) == pytest.approx(0.15)
    assert final_score(0, 0, 0, 0, boost=0.1) == pytest.approx(0.1)
    assert final_score(10, 1, 1, 1) == pytest.approx(1.0)


def test_cluster_groups_similar_items_under_first_leader():
    vectors = {"a": [1.0, 0.0], "b": [0.99, 0.1], "c": [0.0, 1.0], "d": [0.1, 0.99]}
    assert cluster(["a", "c", "b", "d"], vectors, threshold=0.85) == {"a": ["b"], "c": ["d"]}
    assert cluster(["a", "b"], vectors, threshold=0.999) == {"a": [], "b": []}


def _scored(item_id, relevance, quality=5):
    return Enrichment(id=item_id, scored_at=NOW, relevance=relevance, quality=quality)


def test_final_rank_novelty_and_related():
    items = [_aged("best", 1), _aged("dupe", 1), _aged("other", 1)]
    scores = {"best": _scored("best", 9), "dupe": _scored("dupe", 8), "other": _scored("other", 7)}
    vectors = {"best": [1.0, 0.0], "dupe": [0.99, 0.05], "other": [0.0, 1.0]}

    entries = final_rank(items, scores, vectors, {}, NOW, half_life_days=7, cluster_threshold=0.85)

    assert [e.item.id for e in entries] == ["best", "other"]
    assert [r.item.id for r in entries[0].related] == ["dupe"]
    fresh = freshness(NOW - timedelta(days=1), NOW, 7)
    mix = quality_mix(5, 0.5, 0.0)
    assert entries[0].score == pytest.approx(final_score(9, mix, fresh, 1.0))
    assert entries[0].related[0].score == pytest.approx(final_score(8, mix, fresh, 0.3))


def test_final_rank_uses_trust_and_engagement():
    popular = _aged("b", 1).model_copy(update={"engagement": {"points": 999}})
    items = [_aged("a", 1, "trusted"), popular]
    scores = {"a": _scored("a", 5), "b": _scored("b", 5)}
    vectors = {"a": [1.0, 0.0], "b": [0.0, 1.0]}

    entries = final_rank(items, scores, vectors, {"trusted": 1.0}, NOW, 7, 0.85)

    by_id = {e.item.id: e.score for e in entries}
    # trust 1.0 vs default 0.5 -> +0.25*0.3*0.5; engagement ~1.0 -> +0.25*0.2*1.0
    assert by_id["a"] - by_id["b"] == pytest.approx(0.25 * 0.3 * 0.5 - 0.25 * 0.2 * 1.0, abs=1e-3)


# --- feedback boost ----------------------------------------------------------------------


def test_feedback_boost():
    assert feedback_boost([1.0, 0.0], [], []) == 0.0
    assert feedback_boost([1.0, 0.0], [[1.0, 0.0]], []) == pytest.approx(0.1)
    assert feedback_boost([1.0, 0.0], [], [[1.0, 0.0]]) == pytest.approx(-0.1)
    assert feedback_boost([1.0, 0.0], [[0.0, 1.0]], [[-1.0, 0.0]]) == pytest.approx(0.0)
    assert feedback_boost([1.0, 0.0], [[1.0, 0.0]], [[0.6, 0.8]]) == pytest.approx(0.1 - 0.06)


def test_boost_changes_ranking_as_expected():
    items = [_aged("ai", 1), _aged("testing", 1)]
    scores = {"ai": _scored("ai", 8), "testing": _scored("testing", 7)}
    vectors = {"ai": [1.0, 0.0], "testing": [0.0, 1.0]}

    def order(liked, skipped):
        entries = final_rank(items, scores, vectors, {}, NOW, 7, 0.85, liked, skipped)
        return [e.item.id for e in entries]

    assert order([], []) == ["ai", "testing"]  # 0.045 ahead on relevance
    # kept a testing post, skipped an AI post -> testing gets +0.1, ai -0.1
    assert order([[0.0, 1.0]], [[1.0, 0.0]]) == ["testing", "ai"]
    # liking something unrelated to both changes nothing
    assert order([[-1.0, -1.0]], []) == ["ai", "testing"]
