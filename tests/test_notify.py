import shutil
from pathlib import Path

import pytest

from radar.__main__ import main
from radar.notify import (
    DigestSummary,
    NotifyError,
    build_email,
    count_drafts,
    latest_digest,
    read_digest,
    send,
    smtp_config,
)
from tests.conftest import FIXTURES

SMTP_ENV = {
    "SMTP_HOST": "smtp.example.com",
    "SMTP_PORT": "587",
    "SMTP_USER": "me@example.com",
    "SMTP_PASSWORD": "app-password",
    "NOTIFY_TO": "me@example.com",
}


def _review_dir(tmp_path: Path) -> Path:
    review = tmp_path / "review"
    review.mkdir()
    shutil.copy(FIXTURES / "digest_expected.md", review / "2026-10-29.md")
    return review


def test_read_digest(tmp_path):
    summary = read_digest(_review_dir(tmp_path) / "2026-10-29.md")

    assert (summary.day, summary.count) == ("2026-10-29", 2)
    assert summary.top == [
        ("Flaky tests: a field guide", 0.87),
        ("Test automation with Playwright", 0.61),
    ]


def test_read_digest_rejects_other_files(tmp_path):
    path = tmp_path / "x.md"
    path.write_text("# Something else", encoding="utf-8")
    with pytest.raises(NotifyError):
        read_digest(path)


def test_latest_digest_by_name(tmp_path):
    for name in ["2026-10-28.md", "2026-10-29.md", "2026-10-29-2.md", "2026-10-29-10.md"]:
        (tmp_path / name).write_text("", encoding="utf-8")
    assert latest_digest(tmp_path).name == "2026-10-29-10.md"


def test_latest_digest_none(tmp_path):
    with pytest.raises(NotifyError, match="no digest"):
        latest_digest(tmp_path)


def test_count_drafts(tmp_path):
    (tmp_path / "2026-10-29-roundup.md").write_text("", encoding="utf-8")
    (tmp_path / "2026-10-28-roundup.md").write_text("", encoding="utf-8")
    assert count_drafts("2026-10-29", tmp_path) == 1
    assert count_drafts("2026-10-30", tmp_path / "missing") == 0


def test_build_email():
    summary = DigestSummary(
        Path("review/2026-10-29.md"),
        "2026-10-29",
        20,
        [("First", 0.871), ("Second", 0.8), ("Third", 0.75)],
    )

    msg = build_email(summary, drafts=1, sender="me@example.com", to="you@example.com")

    assert msg["Subject"] == "Radar: 20 new items to review (2026-10-29)"
    assert (msg["From"], msg["To"]) == ("me@example.com", "you@example.com")
    assert msg.get_content() == (
        "Top items:\n  1. First (0.87)\n  2. Second (0.80)\n  3. Third (0.75)\n\n"
        "Digest: review/2026-10-29.md\nDrafts created: 1\n"
    )


def test_smtp_config_lists_missing(monkeypatch):
    for name in SMTP_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    with pytest.raises(NotifyError, match="SMTP_PORT, SMTP_USER, SMTP_PASSWORD, NOTIFY_TO"):
        smtp_config()


def test_send_uses_starttls_and_login(mocker):
    smtp_class = mocker.patch("radar.notify.smtplib.SMTP")
    smtp = smtp_class.return_value.__enter__.return_value
    msg = build_email(DigestSummary(Path("r.md"), "d", 1, []), 0, "a@x", "b@x")

    send(msg, SMTP_ENV)

    smtp_class.assert_called_once_with("smtp.example.com", 587, timeout=30)
    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with("me@example.com", "app-password")
    smtp.send_message.assert_called_once_with(msg)


def test_notify_dry_run_prints_and_does_not_send(tmp_path, monkeypatch, mocker, capsys):
    _review_dir(tmp_path)
    monkeypatch.chdir(tmp_path)
    smtp_class = mocker.patch("radar.notify.smtplib.SMTP")

    assert main(["notify", "--dry-run"]) == 0

    out = capsys.readouterr().out
    assert "Subject: Radar: 2 new items to review (2026-10-29)" in out
    assert "1. Flaky tests: a field guide (0.87)" in out
    assert "Drafts created: 0" in out
    smtp_class.assert_not_called()


def test_notify_sends(tmp_path, monkeypatch, mocker, capsys):
    _review_dir(tmp_path)
    monkeypatch.chdir(tmp_path)
    for name, value in SMTP_ENV.items():
        monkeypatch.setenv(name, value)
    smtp_class = mocker.patch("radar.notify.smtplib.SMTP")

    assert main(["notify"]) == 0

    sent = smtp_class.return_value.__enter__.return_value.send_message.call_args.args[0]
    assert sent["To"] == "me@example.com"
    assert "sent 'Radar: 2 new items" in capsys.readouterr().out


def test_notify_missing_smtp_config_fails_cleanly(tmp_path, monkeypatch, capsys):
    _review_dir(tmp_path)
    monkeypatch.chdir(tmp_path)
    for name in SMTP_ENV:
        monkeypatch.delenv(name, raising=False)

    assert main(["notify"]) == 1
    assert "missing in .env" in capsys.readouterr().err


def test_dry_run_prints_non_ascii_readably(tmp_path, monkeypatch, capsys):
    review = _review_dir(tmp_path)
    digest = review / "2026-10-29.md"
    digest.write_text(
        digest.read_text(encoding="utf-8").replace("a field guide", "przewodnik — zażółć"),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    assert main(["notify", "--dry-run"]) == 0
    assert "1. Flaky tests: przewodnik — zażółć (0.87)" in capsys.readouterr().out
