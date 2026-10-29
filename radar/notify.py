"""Email notification via SMTP with STARTTLS (credentials from .env)."""

import json
import os
import re
import smtplib
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

from radar import rawstore

DRAFTS_DIR = Path("drafts")
_HEADER = re.compile(r"^# Review — (\S+) \((\d+) items\)", re.MULTILINE)
_HEADING = re.compile(r"^### \d+\. (.+) — score ([0-9.]+)$", re.MULTILINE)
SMTP_VARS = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "NOTIFY_TO")


class NotifyError(Exception):
    """Email cannot be built or sent."""


@dataclass
class DigestSummary:
    """What the email needs to know about a digest file."""

    path: Path
    day: str
    count: int
    top: list[tuple[str, float]]  # (title, score), best first


def _digest_order(path: Path) -> tuple[str, int]:
    """Sort key: date, then the -2, -3… suffix of later digests on the same day."""
    day, number = path.stem[:10], path.stem[11:]
    return day, int(number) if number.isdigit() else 1


def latest_digest(review_dir: Path) -> Path:
    """The newest digest file, by the date (and same-day number) in its name."""
    digests = sorted(review_dir.glob("*.md"), key=_digest_order)
    if not digests:
        raise NotifyError(f"no digest found in {review_dir}/")
    return digests[-1]


def read_digest(path: Path) -> DigestSummary:
    """Parse the header and the first three item headings of a digest."""
    text = path.read_text(encoding="utf-8")
    header = _HEADER.search(text)
    if header is None:
        raise NotifyError(f"{path} does not look like a digest")
    top = [(title, float(score)) for title, score in _HEADING.findall(text)[:3]]
    return DigestSummary(path, header.group(1), int(header.group(2)), top)


def count_drafts(day: str, drafts_dir: Path = DRAFTS_DIR) -> int:
    """Draft files created for `day` (drafts/YYYY-MM-DD-*.md)."""
    return len(list(drafts_dir.glob(f"{day}-*.md")))


def build_email(summary: DigestSummary, drafts: int, sender: str, to: str) -> EmailMessage:
    """Subject: 'Radar: N new items to review (DATE)'; body: top 3, digest path, draft count."""
    msg = EmailMessage()
    msg["Subject"] = f"Radar: {summary.count} new items to review ({summary.day})"
    msg["From"] = sender
    msg["To"] = to
    top = "\n".join(
        f"  {n}. {title} ({score:.2f})" for n, (title, score) in enumerate(summary.top, start=1)
    )
    msg.set_content(
        f"Top items:\n{top}\n\n"
        f"Digest: {summary.path.as_posix()}\n"
        f"Drafts created: {drafts}\n"
    )
    return msg


def smtp_config() -> dict[str, str]:
    """SMTP settings from the environment (.env). Raises NotifyError listing missing ones."""
    missing = [name for name in SMTP_VARS if not os.environ.get(name)]
    if missing:
        raise NotifyError(f"missing in .env: {', '.join(missing)}")
    return {name: os.environ[name] for name in SMTP_VARS}


def send(msg: EmailMessage, config: dict[str, str]) -> None:
    """Send via SMTP + STARTTLS."""
    with smtplib.SMTP(config["SMTP_HOST"], int(config["SMTP_PORT"]), timeout=30) as smtp:
        smtp.starttls()
        smtp.login(config["SMTP_USER"], config["SMTP_PASSWORD"])
        smtp.send_message(msg)


# --- backlog reminder (GitHub Actions) ---------------------------------------------------

META_PATH = Path("data/raw/_meta.json")
REMINDER_INTERVAL = timedelta(hours=24)


def count_backlog(raw_dir: Path, since: datetime | None) -> int:
    """Raw items fetched after `since` (all items when the local step never ran)."""
    return sum(
        1
        for path in raw_dir.glob("*.jsonl")
        for item in rawstore.read_items(path)
        if since is None or item.fetched_at > since
    )


def reminder_due(now: datetime, meta_path: Path = META_PATH) -> bool:
    """At most one reminder per 24 h."""
    if not meta_path.exists():
        return True
    last = json.loads(meta_path.read_text(encoding="utf-8")).get("last_reminder_at")
    return last is None or now - datetime.fromisoformat(last) >= REMINDER_INTERVAL


def record_reminder(now: datetime, meta_path: Path = META_PATH) -> None:
    """Store the reminder time in data/raw/_meta.json (committed with the raw data)."""
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    meta["last_reminder_at"] = now.isoformat()
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8", newline="\n")


def build_backlog_email(waiting: int, sender: str, to: str) -> EmailMessage:
    """Short reminder: 'N items waiting — run the local step'."""
    msg = EmailMessage()
    msg["Subject"] = f"Radar: {waiting} items waiting — run the local step"
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(
        f"{waiting} collected items have not been processed yet.\n\n"
        "Run the local step: python -m radar run-local\n"
    )
    return msg
