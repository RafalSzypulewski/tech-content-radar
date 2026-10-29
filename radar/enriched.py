"""data/enriched/: scores.jsonl and state.json (written by the local step only)."""

import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from radar.models import Enrichment

SCORES_PATH = Path("data/enriched/scores.jsonl")


def read_scores(path: Path = SCORES_PATH) -> dict[str, Enrichment]:
    """Latest enrichment per item id (later lines win, so a retried item replaces its error)."""
    if not path.exists():
        return {}
    scores = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            enrichment = Enrichment.model_validate_json(line)
            scores[enrichment.id] = enrichment
    return scores


def append_scores(enrichments: Iterable[Enrichment], path: Path = SCORES_PATH) -> None:
    """Append enrichments, creating the file if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        for enrichment in enrichments:
            f.write(enrichment.model_dump_json() + "\n")


def scored_ids(scores: dict[str, Enrichment]) -> set[str]:
    """Ids that have a successful score; failed items are tried again on the next run."""
    return {item_id for item_id, e in scores.items() if e.error is None}


STATE_PATH = Path("data/enriched/state.json")


def read_state(path: Path = STATE_PATH) -> dict:
    """{"last_processed_at": ISO timestamp, "last_digest": path}, or {} before the first run."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_state(
    last_processed_at: datetime, last_digest: str | None, path: Path = STATE_PATH
) -> None:
    """Record when the local step last ran (read by the backlog reminder in GitHub Actions)."""
    state = read_state(path)
    state["last_processed_at"] = last_processed_at.isoformat()
    if last_digest is not None:
        state["last_digest"] = last_digest
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8", newline="\n")
