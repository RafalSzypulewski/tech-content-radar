"""CLI entry point: ``python -m radar <command>``."""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from radar.config import load_settings, load_sources, load_topics

COMMANDS = {
    "collect": "Collect items from sources into data/raw/ (GitHub Actions).",
    "enrich": "Score and summarize items with the local claude CLI.",
    "digest": "Write the review digest to review/.",
    "notify": "Send the digest email notification.",
    "draft": "Write blog drafts for items marked 'write'.",
    "run-local": "Run the full local pipeline.",
}

RAW_DIR = Path("data/raw")


def cmd_collect(args: argparse.Namespace) -> int:
    """Collect all sources and print the summary table."""
    from radar.collectors import collect_all, format_summary, make_client

    sources = load_sources(Path("sources.yaml"))
    topics = load_topics(Path("topics.yaml"))
    with make_client() as client:
        stats = collect_all(sources, topics.keywords, RAW_DIR, datetime.now(UTC), client)
    print(format_summary(stats))
    return 0


def cmd_enrich(args: argparse.Namespace) -> int:
    """Pre-rank unscored items and score the top ones with claude -p."""
    from radar import enriched, llm
    from radar.embeddings import SentenceTransformerEmbedder, embed_items
    from radar.ranking import pre_rank
    from radar.store import Store

    try:
        llm.claude_executable()  # fail fast, before loading the embedding model
    except llm.LLMSetupError as exc:
        print(f"enrich: {exc}", file=sys.stderr)
        return 1
    settings = load_settings()
    topics = load_topics(Path("topics.yaml"))
    trust = {s.id: s.trust for s in load_sources(Path("sources.yaml"))}
    now = datetime.now(UTC)

    store = Store()
    store.load_raw(RAW_DIR)
    items = store.items()
    embedder = SentenceTransformerEmbedder()
    vectors = embed_items(store, embedder, items)
    profiles = embedder.embed([p.text for p in topics.profiles])
    store.close()

    done = enriched.scored_ids(enriched.read_scores())
    limit = args.max_items if args.max_items is not None else settings.LLM_MAX_ITEMS
    top = pre_rank(
        items, vectors, profiles, trust, now, settings.FRESHNESS_HALF_LIFE_DAYS, done, limit
    )
    print(f"enrich: {len(items)} items, {len(done)} already scored, scoring {len(top)}")
    results = llm.score_items([r.item for r in top], topics.tags, settings.LLM_BATCH_SIZE, now)
    enriched.append_scores(results)
    failed = sum(1 for r in results if r.error)
    print(f"enrich: scored {len(results) - failed}, failed {failed} -> {enriched.SCORES_PATH}")
    return 0


HANDLERS = {"collect": cmd_collect, "enrich": cmd_enrich}


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with one subcommand per pipeline step."""
    parser = argparse.ArgumentParser(prog="radar", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    commands = {
        name: subparsers.add_parser(name, help=help_text, description=help_text)
        for name, help_text in COMMANDS.items()
    }
    commands["enrich"].add_argument(
        "--max-items", type=int, help="score at most N items (default: LLM_MAX_ITEMS)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the chosen command. Returns the exit code."""
    # Source names may contain non-ASCII characters; don't crash on a cp1252 Windows console.
    sys.stdout.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    handler = HANDLERS.get(args.command)
    if handler is None:
        print(f"{args.command}: not implemented yet", file=sys.stderr)
        return 1
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
