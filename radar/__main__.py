"""CLI entry point: ``python -m radar <command>``."""

import argparse
import os
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


def cmd_digest(args: argparse.Namespace) -> int:
    """Rank scored items not shown before and write review/YYYY-MM-DD.md."""
    from radar import digest, enriched
    from radar.embeddings import SentenceTransformerEmbedder, embed_items
    from radar.ranking import final_rank
    from radar.store import Store

    settings = load_settings()
    trust = {s.id: s.trust for s in load_sources(Path("sources.yaml"))}
    now = datetime.now(UTC)
    scores = enriched.read_scores()
    done = enriched.scored_ids(scores)
    shown = digest.shown_ids()

    store = Store()
    store.load_raw(RAW_DIR)
    candidates = [i for i in store.items() if i.id in done and i.id not in shown]
    if not candidates:
        store.close()
        print("digest: no new scored items; nothing written")
        return 0
    vectors = embed_items(store, SentenceTransformerEmbedder(), candidates)
    store.close()

    entries = final_rank(
        candidates,
        scores,
        vectors,
        trust,
        now,
        settings.FRESHNESS_HALF_LIFE_DAYS,
        settings.CLUSTER_THRESHOLD,
    )[: settings.DIGEST_SIZE]
    path = digest.write_digest(now.date(), digest.render_digest(now.date(), entries))
    print(f"digest: {len(entries)} items -> {path.as_posix()}")
    return 0


def cmd_notify(args: argparse.Namespace) -> int:
    """Email a summary of the latest digest (or print it with --dry-run)."""
    from radar import notify

    load_settings()  # loads .env into the environment
    try:
        summary = notify.read_digest(notify.latest_digest(Path("review")))
        drafts = notify.count_drafts(summary.day)
        if args.dry_run:
            sender = os.environ.get("SMTP_USER") or "SMTP_USER not set"
            to = os.environ.get("NOTIFY_TO") or "NOTIFY_TO not set"
            msg = notify.build_email(summary, drafts, sender, to)
            # Not msg.as_string(): non-ASCII bodies would print as base64.
            print(f"Subject: {msg['Subject']}\nFrom: {sender}\nTo: {to}\n\n{msg.get_content()}")
            return 0
        config = notify.smtp_config()
        to = config["NOTIFY_TO"]
        msg = notify.build_email(summary, drafts, config["SMTP_USER"], to)
        notify.send(msg, config)
    except (notify.NotifyError, OSError) as exc:  # smtplib errors are OSError subclasses
        print(f"notify: {exc}", file=sys.stderr)
        return 1
    print(f"notify: sent '{msg['Subject']}' to {to}")
    return 0


HANDLERS = {
    "collect": cmd_collect,
    "enrich": cmd_enrich,
    "digest": cmd_digest,
    "notify": cmd_notify,
}


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
    commands["notify"].add_argument(
        "--dry-run", action="store_true", help="print the email instead of sending it"
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
