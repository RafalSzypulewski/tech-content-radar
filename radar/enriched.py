"""Read and append data/enriched/scores.jsonl (written by the local step only)."""

from collections.abc import Iterable
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
