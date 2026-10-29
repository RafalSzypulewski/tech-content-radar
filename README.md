# tech-content-radar

A bot that collects tech content (blog posts, YouTube videos, podcasts, community links) about
software testing, test automation, AI and technology, ranks it, and produces review digests and
Markdown blog-post drafts for a static blog.

- **Collection** runs on GitHub Actions every 6 hours and writes `data/raw/`.
- **Scoring, summaries and drafts** run locally through the `claude` CLI (subscription, no API key).
- Sources can be English or Polish; all output is in English.

## Status

M0 (scaffold) — the CLI exists but every command is a stub. See [PLAN.md](PLAN.md) for the design
and milestones (M0–M7). Full setup and usage instructions will be added as milestones land.

## Development

```bash
python3.12 -m venv .venv      # Windows: py -3.12 -m venv .venv
.venv/Scripts/activate        # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -e ".[collect,dev]"
python -m radar --help
ruff check .
pytest
```

Install `.[local]` as well for the local scoring step (embeddings).
