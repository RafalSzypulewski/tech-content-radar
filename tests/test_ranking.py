from datetime import timedelta

import pytest

from radar.ranking import freshness, pre_rank, pre_score
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
