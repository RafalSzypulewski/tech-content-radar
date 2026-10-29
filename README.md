# tech-content-radar

A bot that collects tech content (blog posts, YouTube videos, podcasts, community links) about
software testing, test automation, AI and technology, ranks it, and produces review digests and
Markdown blog-post drafts for a static blog.

- **Collection** runs on GitHub Actions every 6 hours and writes `data/raw/`.
- **Scoring, summaries and drafts** run locally through the `claude` CLI (subscription, no API key).
- Sources can be English or Polish; all output is in English.

## Status

Planning. Nothing is implemented yet — see [PLAN.md](PLAN.md) for the design and milestones (M0–M7).
Setup and usage instructions will be added as milestones land.
