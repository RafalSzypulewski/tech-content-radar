"""CLI entry point: ``python -m radar <command>``."""

import argparse
import os
import subprocess
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
    from radar.feedback import parse_all
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
    store.replace_feedback(parse_all())
    feedback = store.feedback()
    items = store.items()
    candidates = [i for i in items if i.id in done and i.id not in shown]
    if not candidates:
        store.close()
        enriched.write_state(now, None)
        print("digest: no new scored items; nothing written")
        return 0
    with_feedback = [i for i in items if i.id in feedback]
    vectors = embed_items(store, SentenceTransformerEmbedder(), candidates + with_feedback)
    store.close()

    # Feedback on items no longer in data/raw has no vector and is ignored.
    known = {i: label for i, label in feedback.items() if i in vectors}
    liked = [vectors[i] for i, label in known.items() if label in ("keep", "write")]
    skipped = [vectors[i] for i, label in known.items() if label == "skip"]
    entries = final_rank(
        candidates,
        scores,
        vectors,
        trust,
        now,
        settings.FRESHNESS_HALF_LIFE_DAYS,
        settings.CLUSTER_THRESHOLD,
        liked,
        skipped,
    )[: settings.DIGEST_SIZE]
    path = digest.write_digest(now.date(), digest.render_digest(now.date(), entries))
    enriched.write_state(now, path.as_posix())
    print(
        f"digest: {len(entries)} items -> {path.as_posix()} "
        f"(feedback: {len(liked)} kept/written, {len(skipped)} skipped)"
    )
    return 0


def _deliver(build, dry_run: bool) -> None:
    """Build an email with `build(sender, to)` and send it, or print it on a dry run.

    Raises NotifyError / OSError (smtplib errors are OSError subclasses).
    """
    from radar import notify

    if dry_run:
        sender = os.environ.get("SMTP_USER") or "SMTP_USER not set"
        to = os.environ.get("NOTIFY_TO") or "NOTIFY_TO not set"
        msg = build(sender, to)
        # Not msg.as_string(): non-ASCII bodies would print as base64.
        print(f"Subject: {msg['Subject']}\nFrom: {sender}\nTo: {to}\n\n{msg.get_content()}")
        return
    config = notify.smtp_config()
    msg = build(config["SMTP_USER"], config["NOTIFY_TO"])
    notify.send(msg, config)
    print(f"notify: sent '{msg['Subject']}' to {config['NOTIFY_TO']}")


def _notify_backlog(dry_run: bool) -> int:
    """Remind by email when many collected items wait for the local step (GitHub Actions).

    Never fails: a missing secret or SMTP error must not stop the collect workflow.
    """
    from radar import enriched, notify

    settings = load_settings()
    now = datetime.now(UTC)
    last = enriched.read_state().get("last_processed_at")
    waiting = notify.count_backlog(RAW_DIR, datetime.fromisoformat(last) if last else None)
    print(f"backlog: {waiting} items waiting (alert at {settings.BACKLOG_ALERT})")
    if waiting < settings.BACKLOG_ALERT:
        return 0
    if not notify.reminder_due(now):
        print("backlog: reminder already sent in the last 24 h")
        return 0
    try:
        _deliver(lambda sender, to: notify.build_backlog_email(waiting, sender, to), dry_run)
    except (notify.NotifyError, OSError) as exc:
        print(f"::warning::backlog reminder not sent: {exc}")
        return 0
    if not dry_run:
        notify.record_reminder(now)
    return 0


def cmd_notify(args: argparse.Namespace) -> int:
    """Email a summary of the latest digest (or print it with --dry-run)."""
    from radar import notify

    load_settings()  # loads .env into the environment
    if args.backlog:
        return _notify_backlog(args.dry_run)
    try:
        summary = notify.read_digest(notify.latest_digest(Path("review")))
        drafts = notify.count_drafts(summary.day)
        _deliver(lambda sender, to: notify.build_email(summary, drafts, sender, to), args.dry_run)
    except (notify.NotifyError, OSError) as exc:
        print(f"notify: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_draft(args: argparse.Namespace) -> int:
    """Write one roundup draft from items marked `write` that have no draft yet."""
    from radar import draft, enriched, llm
    from radar.feedback import parse_all
    from radar.store import Store

    marked = {i for i, label in parse_all().items() if label == "write"}
    wanted = marked - draft.read_drafted()
    if not wanted:
        print("draft: no new items marked 'write'")
        return 0
    scores = enriched.read_scores()
    store = Store()
    store.load_raw(RAW_DIR)
    pairs = [(i, scores[i.id]) for i in store.items() if i.id in wanted and i.id in scores]
    store.close()
    try:
        path = draft.make_roundup(datetime.now(UTC).date(), pairs)
    except (llm.LLMSetupError, llm.LLMCallError) as exc:
        print(f"draft: {exc}", file=sys.stderr)
        return 1
    print(f"draft: {len(pairs)} items -> {path.as_posix()}")
    return 0


LOCAL_OUTPUTS = ("data/enriched", "review", "drafts")  # the only paths the local step commits


def _git(*args: str) -> None:
    """Run git with an argument list (works the same on Windows, macOS and Linux)."""
    subprocess.run(["git", *args], check=True)


def _commit_and_push(push: bool) -> None:
    """Commit data/enriched/, review/ and drafts/ (only those paths) and optionally push."""
    paths = [p for p in LOCAL_OUTPUTS if Path(p).exists()]
    _git("add", "--", *paths)
    # Commit the staged files by name: a pathspec like an empty drafts/ folder that git
    # knows no files in would make `git commit -- <paths>` fail.
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", *paths],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.splitlines()
    if not staged:
        print("run-local: nothing to commit")
        return
    _git("commit", "-m", f"local: {datetime.now(UTC):%Y-%m-%dT%H:%MZ}", "--", *staged)
    if push:
        _git("pull", "--rebase", "--autostash")
        _git("push")


def cmd_run_local(args: argparse.Namespace) -> int:
    """pull -> enrich -> digest -> draft -> notify -> commit & push."""
    from radar import enriched

    try:
        _git("pull", "--rebase", "--autostash")
    except subprocess.CalledProcessError as exc:
        print(f"run-local: git pull failed ({exc}); stopping", file=sys.stderr)
        return 1
    if cmd_enrich(argparse.Namespace(max_items=args.max_items)) != 0:
        return 1
    digest_before = enriched.read_state().get("last_digest")
    if cmd_digest(argparse.Namespace()) != 0:
        return 1
    new_digest = enriched.read_state().get("last_digest") != digest_before
    # Drafts before the email, so the email can report how many were created.
    if cmd_draft(argparse.Namespace()) != 0:
        print("run-local: drafts failed; continuing", file=sys.stderr)
    if new_digest and not args.no_email:
        if cmd_notify(argparse.Namespace(dry_run=False, backlog=False)) != 0:
            print("run-local: email not sent; continuing", file=sys.stderr)
    try:
        _commit_and_push(push=not args.no_push)
    except subprocess.CalledProcessError as exc:
        print(f"run-local: git failed ({exc})", file=sys.stderr)
        return 1
    return 0


HANDLERS = {
    "collect": cmd_collect,
    "enrich": cmd_enrich,
    "digest": cmd_digest,
    "notify": cmd_notify,
    "draft": cmd_draft,
    "run-local": cmd_run_local,
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
    commands["notify"].add_argument(
        "--backlog",
        action="store_true",
        help="remind when BACKLOG_ALERT+ collected items wait for the local step",
    )
    run_local = commands["run-local"]
    run_local.add_argument("--no-push", action="store_true", help="commit but do not push")
    run_local.add_argument("--no-email", action="store_true", help="do not send the email")
    run_local.add_argument(
        "--max-items", type=int, help="score at most N items (default: LLM_MAX_ITEMS)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the chosen command. Returns the exit code."""
    # Source names may contain non-ASCII characters; don't crash on a cp1252 Windows console.
    sys.stdout.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    return HANDLERS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
