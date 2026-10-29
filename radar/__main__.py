"""CLI entry point: ``python -m radar <command>``."""

import argparse
import sys

COMMANDS = {
    "collect": "Collect items from sources into data/raw/ (GitHub Actions).",
    "enrich": "Score and summarize items with the local claude CLI.",
    "digest": "Write the review digest to review/.",
    "notify": "Send the digest email notification.",
    "draft": "Write blog drafts for items marked 'write'.",
    "run-local": "Run the full local pipeline.",
}


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with one subcommand per pipeline step."""
    parser = argparse.ArgumentParser(prog="radar", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, help_text in COMMANDS.items():
        subparsers.add_parser(name, help=help_text, description=help_text)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the chosen command. Returns the exit code."""
    args = build_parser().parse_args(argv)
    print(f"{args.command}: not implemented yet", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
