# Tech Content Radar — Implementation Plan

A bot that collects tech content (blog posts, YouTube videos, podcasts, community links) about
**software testing, test automation, AI and technology**, ranks it, and produces review digests
and Markdown blog-post drafts for a static blog.

---

## 0. Instructions for Claude Code

- Work **one milestone at a time**, in order. After each milestone: run `ruff check .` and
  `pytest`, make sure both pass, then **stop and summarize** what was done and what to test
  manually. Do not start the next milestone until I approve.
- Do not add dependencies outside the list in §3 without asking first.
- Tests must never hit the network or call the real `claude` CLI — use fixtures and mocks.
- Never commit `.env`, `data/local.db`, or any secrets.
- **Never use the Anthropic API or `ANTHROPIC_API_KEY`.** All LLM calls go through the local
  `claude` CLI (Claude Code headless mode), which uses my subscription.
- Keep code simple and readable; prefer small functions with type hints and docstrings.
- If something in this plan is unclear or seems wrong, ask instead of guessing.

---

## 1. Key decisions (fixed)

| Topic | Decision |
|---|---|
| Collection | Runs on **GitHub Actions** cron (every 6 h) |
| LLM work (scoring, summaries, drafts) | Runs **locally only**, via `claude -p` (subscription, no API billing) |
| Sources | English **and Polish** sources |
| Output language | **English only** (summaries, digests, drafts). Translation is out of scope. |
| Review | Markdown digest files with checkboxes + **email notification** |
| Blog | Static site → drafts are Markdown with front matter (`draft: true`) |
| Storage | JSONL files in git (raw + enriched); local SQLite as a disposable cache |

---

## 2. Architecture

```
GitHub Actions (cron)                         Local machine (manual or scheduled)
──────────────────────                        ─────────────────────────────────────
collect from sources                          git pull --rebase
canonicalize URLs + dedupe                    load raw JSONL → SQLite cache
detect language                               parse feedback from review/*.md
keyword + age pre-filter                      embeddings (multilingual) → pre-rank
append data/raw/YYYY-MM-DD.jsonl              top N → claude -p (batched) → scores/summaries
(optional) backlog reminder email             final ranking + clustering
commit & push                                 write review/YYYY-MM-DD.md
                                              send email notification
                                              drafts for items marked "write"
                                              commit & push enriched/, review/, drafts/
```

**Ownership rule (prevents merge conflicts):**
- GitHub Actions writes **only** `data/raw/`.
- The local step writes **only** `data/enriched/`, `review/`, `drafts/`.
- Both sides `git pull --rebase` before pushing.

---

## 3. Tech stack

- Python 3.12, packaged with `pyproject.toml`, package name `radar`
- CLI: `argparse` → `python -m radar <command>`
- Dependencies:
  - `httpx` (HTTP), `feedparser` (RSS/Atom), `trafilatura` (article text extraction)
  - `pydantic` (schemas/validation), `pyyaml` (config), `python-dotenv` (.env)
  - `lingua-language-detector` (language detection)
  - `sentence-transformers` (local multilingual embeddings) — **local only**, not installed in the collect workflow
- Dev: `pytest`, `pytest-mock`, `respx` (mock httpx), `ruff`
- Split dependencies into extras: `[collect]`, `[local]`, `[dev]` so GitHub Actions installs only what collection needs.

---

## 4. Repository layout

```
radar/
  __init__.py
  __main__.py          # CLI entry: collect | enrich | digest | notify | draft | run-local
  config.py            # load sources.yaml, topics.yaml, settings, .env
  models.py            # pydantic models: RawItem, Enrichment, Feedback
  canonical.py         # URL canonicalization + item id
  collectors/
    rss.py             # blogs, Substack, Medium, YouTube channel feeds, podcasts, GitHub releases
    hackernews.py      # HN Algolia API
    devto.py           # dev.to API
  prefilter.py         # keyword + age filter
  language.py          # language detection
  rawstore.py          # read/append data/raw/*.jsonl, known-ids index
  store.py             # local SQLite cache
  embeddings.py        # multilingual embeddings + topic similarity
  llm.py               # claude -p wrapper (batching, JSON parsing, retries)
  ranking.py           # pre-rank, final score, clustering/novelty, feedback boost
  digest.py            # write review/*.md
  feedback.py          # parse checkboxes from review/*.md
  notify.py            # email via SMTP
  draft.py             # blog drafts via claude -p
prompts/
  score.md             # prompt template for scoring + summarizing
  draft.md             # prompt template for roundup drafts
data/
  raw/                 # written by GitHub Actions only
  enriched/            # written by local step only (scores.jsonl, state.json)
review/                # digests (I edit the checkboxes)
drafts/                # blog post drafts
tests/
  fixtures/            # sample feeds, API responses, claude outputs, review files
.github/workflows/
  collect.yml          # cron collection
  tests.yml            # ruff + pytest on push / PR
sources.yaml
topics.yaml
.env.example
README.md
```

---

## 5. Configuration files

### sources.yaml

```yaml
defaults:
  trust: 0.5            # 0..1, used in ranking
  max_age_days: 21
sources:
  - id: google-testing-blog
    name: Google Testing Blog
    kind: rss            # rss | hackernews | devto
    type: blog           # blog | video | podcast | release | community
    url: https://testing.googleblog.com/feeds/posts/default
    lang: en
    trust: 0.9
    always_include: true # topic-specific source: skip keyword filter
  - id: martin-fowler
    name: Martin Fowler
    kind: rss
    type: blog
    url: https://martinfowler.com/feed.atom
    lang: en
    trust: 0.9
  - id: simon-willison
    name: Simon Willison
    kind: rss
    type: blog
    url: https://simonwillison.net/atom/everything/
    lang: en
    trust: 0.8
  - id: playwright-releases
    name: Playwright releases
    kind: rss
    type: release
    url: https://github.com/microsoft/playwright/releases.atom
    lang: en
    trust: 0.8
    always_include: true
  - id: hn-testing
    name: Hacker News
    kind: hackernews
    type: community
    query: ["testing", "test automation", "playwright", "selenium", "LLM"]
    min_points: 30
  - id: devto-testing
    name: dev.to
    kind: devto
    type: community
    tags: ["testing", "automation", "qa", "ai"]
  # YouTube channel: kind: rss, type: video,
  #   url: https://www.youtube.com/feeds/videos.xml?channel_id=<CHANNEL_ID>
  # Podcast: kind: rss, type: podcast, url: <podcast RSS feed>
  # Polish sources: add with lang: pl
```

Claude Code: verify each example URL returns a valid feed during milestone 1; remove or flag broken ones. I will add more sources (incl. Polish ones) myself.

### topics.yaml

```yaml
keywords:            # pre-filter, case-insensitive, EN + PL
  - testing
  - testowanie
  - testy
  - test automation
  - automatyzacja
  - QA
  - quality assurance
  - playwright
  - selenium
  - cypress
  - pytest
  - flaky
  - CI/CD
  - AI
  - sztuczna inteligencja
  - LLM
  - agent
profiles:            # used for embedding similarity (relevance)
  - id: test-automation
    text: "Test automation frameworks, patterns and practices: Playwright, Selenium, Cypress, pytest, flaky tests, test architecture."
  - id: ai-in-testing
    text: "Using AI and LLMs in software testing and QA: test generation, AI agents, evaluating AI systems."
  - id: ai-engineering
    text: "Practical AI engineering: LLM tools, agents, prompting, building with AI models."
  - id: dev-practices
    text: "Software engineering practices: CI/CD, DevOps, code quality, developer productivity."
tags: [test-automation, ai-in-testing, ai, llm, tools, ci-cd, career, release, tutorial, opinion]
```

### Settings (in `config.py`, overridable via `.env`)

`LLM_MAX_ITEMS=60`, `LLM_BATCH_SIZE=20`, `DIGEST_SIZE=20`, `FRESHNESS_HALF_LIFE_DAYS=7`,
`CLUSTER_THRESHOLD=0.85`, `BACKLOG_ALERT=100`.

### .env.example

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=          # Gmail app password, never your real password
NOTIFY_TO=
```

---

## 6. Data schemas

### Raw item — one JSON object per line in `data/raw/YYYY-MM-DD.jsonl`

| Field | Type | Notes |
|---|---|---|
| `id` | str | first 12 hex chars of sha1(canonical_url) |
| `url` | str | original URL |
| `canonical_url` | str | see §7 |
| `title` | str | original title |
| `source_id`, `source_name` | str | from sources.yaml |
| `type` | str | blog / video / podcast / release / community |
| `lang` | str | `en`, `pl` or `other` |
| `published_at`, `fetched_at` | ISO 8601 UTC | |
| `author` | str \| null | |
| `text` | str | description / feed content / extracted text, max 4000 chars |
| `engagement` | dict | e.g. `{"points": 120, "comments": 45}`, may be empty |
| `matched_keywords` | list[str] | from pre-filter |

### Enrichment — `data/enriched/scores.jsonl`

`id`, `title_en`, `summary_en` (2–3 sentences), `relevance` (1–10), `quality` (1–10),
`reason` (≤ 25 words, English), `tags` (from topics.yaml list), `scored_at`, `error` (str | null).

### `data/enriched/state.json`

`{"last_processed_at": "<ISO timestamp>", "last_digest": "review/2026-10-29.md"}` —
read by the collect workflow for the backlog reminder.

---

## 7. Rules and algorithms

**URL canonicalization:** lowercase scheme and host, remove `www.`, drop the fragment, drop
tracking params (`utm_*`, `fbclid`, `gclid`, `ref`, `source`), strip the trailing slash,
normalize YouTube links (`youtu.be/X`, `/shorts/X`, `watch?v=X&...`) to `https://youtube.com/watch?v=X`.

**Dedupe:** skip items whose `id` is already present in the raw files of the last 90 days
(keep an in-memory set built at start; fine at this scale).

**Pre-filter (Actions):** keep an item if it is younger than `max_age_days` AND
(`always_include` source OR at least one keyword matches title/text, word-boundary, case-insensitive).
For Hacker News, also require `min_points`.

**Pre-rank (local, before LLM):**
`pre = 0.6·embedding_relevance + 0.25·freshness + 0.15·trust`, where
`embedding_relevance` = max cosine similarity to any topic profile, using
`paraphrase-multilingual-MiniLM-L12-v2` (works for EN + PL). Take the top `LLM_MAX_ITEMS`
items not yet scored.

**Freshness:** `0.5 ** (age_days / FRESHNESS_HALF_LIFE_DAYS)`.

**Final score:**
`final = 0.45·(relevance/10) + 0.25·quality_mix + 0.15·freshness + 0.15·novelty + feedback_boost`
- `quality_mix = 0.5·(quality/10) + 0.3·trust + 0.2·engagement_norm` (engagement normalized 0..1, log-scaled; 0 when missing)
- **Novelty:** cluster items whose embeddings have cosine ≥ `CLUSTER_THRESHOLD`; the best item in a cluster gets 1.0, others 0.3. The digest shows related items under the best one.
- **Feedback boost:** `+0.1 · max_sim(kept/written items) − 0.1 · max_sim(skipped items)` using embeddings; 0 when there is no feedback yet.

---

## 8. LLM wrapper (`llm.py`)

- Call: `subprocess.run([shutil.which("claude"), "-p", "--output-format", "json", "--tools", ""], input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=300, cwd=<temp dir>)`.
  The prompt goes via **stdin** (Windows `claude.cmd` shim has an 8191-char command-line limit and mangles
  quotes/`%`); run from an empty temp dir with tools disabled so the repo's CLAUDE.md is not loaded.
- The CLI returns a JSON envelope; the model's answer is in the `result` field. Parse it as JSON.
- **Safety check at start:** if `ANTHROPIC_API_KEY` is set in the environment, abort with a clear
  error message (it would switch billing to the API).
- If the `claude` command is not found, abort with a clear message.
- Batch items (`LLM_BATCH_SIZE`); send `id`, `title`, `lang`, `type`, `source_name` and the first 1500 chars of `text`.
- Validate the response with pydantic. Tolerate ```json code fences around the answer.
- On invalid JSON or missing ids: retry the batch once with a "return only valid JSON" reminder;
  if it fails again, record `error` for those items and continue with other batches.
- Prompts live in `prompts/*.md` with `{placeholders}`. The scoring prompt must say:
  *"Write all output in English, even when the source is in Polish."*

---

## 9. Review digest format (`review/YYYY-MM-DD.md`)

```markdown
# Review — 2026-10-29 (20 items)

Mark one box per item: keep = good material, skip = not interesting, write = make a blog draft.

### 1. Flaky tests: a field guide — score 0.87
<!-- id: 7f3a9c1b2d4e -->
blog · Google Testing Blog · EN · 2026-10-27 · https://…
**Summary:** …
**Why:** …
**Tags:** test-automation, tutorial
Related: [Other post on the same topic](https://…)
- [ ] keep
- [ ] skip
- [ ] write
```

- Items already shown in an earlier digest are not shown again.
- For Polish sources, show the original title below the heading: `Original (PL): …`.
- `feedback.py` parses every `review/*.md`: for each `<!-- id: … -->` block, read which box is
  checked (`[x]` or `[X]`). Unchecked = no feedback. If several are checked, `write` > `keep` > `skip`.
  Feedback is stored in SQLite and re-parsed on every run (the files are the source of truth).

---

## 10. Email notification (`notify.py`)

- Sent after the digest is written: subject `Radar: 20 new items to review (2026-10-29)`,
  body = top 3 titles with scores + the path of the digest file + the count of drafts created.
- SMTP with STARTTLS, credentials from `.env`. `--dry-run` prints the email instead of sending.
- **Backlog reminder (GitHub Actions):** after collecting, count raw items with
  `fetched_at > state.json.last_processed_at`. If ≥ `BACKLOG_ALERT`, send a short email
  "N items waiting — run the local step". SMTP credentials come from GitHub Secrets.
  Send at most one reminder per 24 h (store the last reminder time in `data/raw/_meta.json`).

---

## 11. Blog drafts (`draft.py`)

- Input: items marked `write` that have no draft yet.
- Output: one roundup file `drafts/YYYY-MM-DD-roundup.md` per run (if there are any `write` items):

```markdown
---
title: "Testing & AI roundup — 2026-10-29"
date: 2026-10-29
tags: [testing, automation, ai]
draft: true
---

Intro paragraph (2–3 sentences).

## Item title
2–3 sentence summary in my own words, with a link to the original.

<!-- your take: -->
```

- Generated via `claude -p` with `prompts/draft.md`. The prompt must say: summarize in your own
  words, never copy text from the source, always link the original, English only.
- Record drafted ids so items are never drafted twice.

---

## 12. GitHub Actions

### `.github/workflows/collect.yml`
- Triggers: `schedule: "0 */6 * * *"` and `workflow_dispatch`.
- `permissions: contents: write`; `concurrency: collect` (no parallel runs).
- Steps: checkout → setup Python 3.12 with pip cache → `pip install .[collect]` →
  `python -m radar collect` → backlog check → `git pull --rebase` → commit `data/raw` (skip if no changes) → push.
- One failing source must not fail the run: log the error, continue, print a summary table
  (source, fetched, new, kept, errors) to the job log.

### `.github/workflows/tests.yml`
- On push and pull request: `pip install .[collect,dev]` → `ruff check .` → `pytest`.
- Tests that need `[local]` deps (embeddings) are marked `@pytest.mark.local` and skipped in CI;
  embedding logic should be testable with a fake embedder.

---

## 13. Local run (`python -m radar run-local`)

Runs in order: `git pull --rebase` → load raw → parse feedback → embeddings + pre-rank →
LLM scoring → final ranking → digest → notify → drafts → write `state.json` → commit & push
`data/enriched/`, `review/`, `drafts/`. Each step is also available as its own command.
Flags: `--no-push`, `--no-email`, `--max-items N`. Must work on Windows, macOS and Linux
(no shell-specific commands; call git via `subprocess` with argument lists).

---

## 14. Milestones

### M0 — Scaffold
- pyproject with extras, package skeleton, CLI with stub commands, ruff config, pytest setup,
  `tests.yml`, `.gitignore` (`.env`, `data/local.db`, `__pycache__`, `.venv`), `.env.example`, README stub.
- ✅ `python -m radar --help` works; `ruff check .` and `pytest` pass in CI.

### M1 — RSS collector
- `config.py`, `models.py`, `canonical.py`, `collectors/rss.py`, `prefilter.py`, `rawstore.py`, `collect` command, `collect.yml`.
- ✅ Tests: canonicalization table test (many URL cases), dedupe, keyword filter (EN + PL),
  RSS + Atom + YouTube feed parsing from fixtures, one broken source doesn't stop the run.
- ✅ A manual `python -m radar collect` creates a valid JSONL file.

### M2 — More sources + enrichment in collection
- `collectors/hackernews.py`, `collectors/devto.py`, `language.py`, text extraction with
  `trafilatura` for blog items whose feed text is shorter than 500 chars (timeout 10 s, polite User-Agent).
- ✅ Tests with `respx` mocks for HN/dev.to responses; language detection for EN and PL samples.

### M3 — Local store + pre-ranking
- `store.py` (SQLite), `embeddings.py`, pre-rank part of `ranking.py`.
- ✅ Tests with a fake embedder; loading raw JSONL into SQLite is idempotent.

### M4 — LLM scoring
- `llm.py`, `prompts/score.md`, `enrich` command, writes `data/enriched/scores.jsonl`.
- ✅ Tests (mock `subprocess.run`): valid response, response in code fences, invalid JSON → retry →
  error recorded, missing ids, `ANTHROPIC_API_KEY` set → abort, `claude` missing → clear error.
- ✅ Manual run on ~10 real items with my subscription.

### M5 — Ranking, digest, notification
- Final scoring + clustering in `ranking.py`, `digest.py`, `notify.py`, `digest` / `notify` commands.
- ✅ Tests: score formula, clustering, digest snapshot test, items not repeated across digests,
  email built correctly (`--dry-run`, SMTP mocked).

### M6 — Feedback loop + backlog reminder
- `feedback.py`, feedback boost in ranking, `state.json`, backlog email in `collect.yml`.
- ✅ Tests: parsing all checkbox combinations, malformed blocks ignored, boost changes ranking as expected.

### M7 — Drafts + `run-local`
- `draft.py`, `prompts/draft.md`, `run-local` command with flags.
- ✅ Tests: draft front matter valid, no double drafting, run-local step order (mocked steps).
- ✅ README: setup, adding sources, running locally, scheduling the local run (Windows Task Scheduler / cron), Gmail app password setup.

---

## 15. Out of scope (for now)
- Translating output to Polish
- Automatic publishing to the blog
- Podcast/video transcription
- YouTube Data API (channel RSS is enough)
- Web UI
