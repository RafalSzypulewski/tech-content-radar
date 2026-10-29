"""CLI entry point: ``python -m radar <command>``."""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from radar.config import load_sources, load_topics

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


HANDLERS = {"collect": cmd_collect}


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with one subcommand per pipeline step."""
    parser = argparse.ArgumentParser(prog="radar", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, help_text in COMMANDS.items():
        subparsers.add_parser(name, help=help_text, description=help_text)
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
