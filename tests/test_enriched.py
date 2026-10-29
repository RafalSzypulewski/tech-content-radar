from datetime import timedelta

from radar.enriched import append_scores, read_scores, read_state, scored_ids, write_state
from radar.models import Enrichment
from tests.conftest import NOW


def test_round_trip_latest_line_wins(tmp_path):
    path = tmp_path / "enriched" / "scores.jsonl"
    append_scores([Enrichment(id="a", scored_at=NOW, error="timeout")], path)
    append_scores(
        [
            Enrichment(id="a", scored_at=NOW, relevance=9, quality=8, title_en="A"),
            Enrichment(id="b", scored_at=NOW, error="missing"),
        ],
        path,
    )

    scores = read_scores(path)

    assert scores["a"].relevance == 9 and scores["a"].error is None
    assert scored_ids(scores) == {"a"}  # "b" failed and will be retried


def test_read_missing_file(tmp_path):
    assert read_scores(tmp_path / "nope.jsonl") == {}


def test_state_round_trip_keeps_last_digest(tmp_path):
    path = tmp_path / "enriched" / "state.json"
    assert read_state(path) == {}

    write_state(NOW, "review/2026-10-29.md", path)
    later = NOW + timedelta(hours=6)
    write_state(later, None, path)  # a run without a new digest

    assert read_state(path) == {
        "last_processed_at": later.isoformat(),
        "last_digest": "review/2026-10-29.md",
    }
