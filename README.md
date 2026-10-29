# tech-content-radar

A bot that collects tech content (blog posts, YouTube videos, podcasts, community links) about
software testing, test automation, AI and technology, ranks it, and produces review digests and
Markdown blog-post drafts for a static blog.

- **Collection** runs on GitHub Actions every 6 hours and writes `data/raw/`.
- **Scoring, summaries and drafts** run locally through the `claude` CLI (your Claude
  subscription — never the Anthropic API).
- Sources can be English or Polish; all output is in English.

See [PLAN.md](PLAN.md) for the full design.

## How it works

```
GitHub Actions, every 6 h               Your machine (python -m radar run-local)
collect → dedupe → pre-filter            git pull → enrich (claude -p) → digest
→ data/raw/YYYY-MM-DD.jsonl              → drafts → email → commit & push
→ backlog reminder email                 data/enriched/, review/, drafts/
```

1. You get an email: *Radar: 20 new items to review*.
2. Open `review/YYYY-MM-DD.md` and tick one box per item: `keep`, `skip` or `write`.
3. The next local run learns from your ticks (similar items rank higher or lower) and turns items
   marked `write` into a roundup draft in `drafts/` (front matter `draft: true`).

## Setup

Requirements: Python 3.12, git, and [Claude Code](https://claude.com/claude-code) installed and
logged in with your subscription (`claude` on your PATH).

```bash
git clone https://github.com/RafalSzypulewski/tech-content-radar.git
cd tech-content-radar
python3.12 -m venv .venv            # Windows: py -3.12 -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
pip install -e ".[collect,local,dev]"
cp .env.example .env                # then fill it in, see "Email" below
```

The first local run downloads the embedding model (~470 MB) into your Hugging Face cache.

> **Never set `ANTHROPIC_API_KEY`.** If it is set, the `claude` CLI bills the API instead of your
> subscription, so every LLM command refuses to run.

### Email (Gmail app password)

1. Turn on 2-Step Verification for your Google account.
2. Go to <https://myaccount.google.com/apppasswords>, create an app password (e.g. "radar") and
   copy the 16-character password.
3. Put it in `.env` — never your real Google password:

   ```
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=you@gmail.com
   SMTP_PASSWORD=abcdabcdabcdabcd
   NOTIFY_TO=you@gmail.com
   ```

4. Check it: `python -m radar notify --dry-run` prints the email, `python -m radar notify` sends it.
5. For the backlog reminder from GitHub Actions, add the same five values as repository secrets
   (Settings → Secrets and variables → Actions).

## Running locally

```bash
python -m radar run-local                  # everything below, in order
python -m radar run-local --no-push        # commit but don't push
python -m radar run-local --no-email       # skip the email
python -m radar run-local --max-items 10   # score at most 10 items with claude
```

`run-local` runs: `git pull --rebase --autostash` → `enrich` → `digest` → `draft` → `notify` →
commit and push `data/enriched/`, `review/` and `drafts/` (nothing else). Run it from the repository
root. Each step is also a command of its own:

| Command | What it does |
|---|---|
| `collect` | Fetch all sources into `data/raw/` (normally only on GitHub Actions) |
| `enrich [--max-items N]` | Pre-rank unscored items and score the top ones with `claude -p` |
| `digest` | Write `review/YYYY-MM-DD.md` with items not shown before |
| `draft` | Write `drafts/YYYY-MM-DD-roundup.md` from items marked `write` |
| `notify [--dry-run]` | Email a summary of the latest digest |
| `notify --backlog` | Remind when many collected items wait (used by GitHub Actions) |

### Settings

Defaults can be overridden in `.env` (or as environment variables):

| Name | Default | Meaning |
|---|---|---|
| `LLM_MAX_ITEMS` | 60 | Items scored by `claude` per run |
| `LLM_BATCH_SIZE` | 20 | Items per `claude -p` call |
| `DIGEST_SIZE` | 20 | Items per digest |
| `FRESHNESS_HALF_LIFE_DAYS` | 7 | Age at which the freshness score halves |
| `CLUSTER_THRESHOLD` | 0.85 | Similarity above which items count as the same story |
| `BACKLOG_ALERT` | 100 | Waiting items that trigger the reminder email |

## Adding sources

Edit [sources.yaml](sources.yaml). Each source needs an `id`, `name`, `kind`, `type`, and for RSS a
`url`:

```yaml
  - id: my-blog                # unique, used in data files
    name: My Favourite Blog
    kind: rss                  # rss | hackernews | devto
    type: blog                 # blog | video | podcast | release | community
    url: https://example.com/feed.xml
    lang: pl                   # en (default) or pl
    trust: 0.8                 # 0..1, how much you trust it (default 0.5)
    always_include: true       # optional: skip the keyword filter (topic-specific sources)
```

- **YouTube channel:** `kind: rss`, `type: video`,
  `url: https://www.youtube.com/feeds/videos.xml?channel_id=<CHANNEL_ID>`.
- **Podcast:** `kind: rss`, `type: podcast`, `url:` the podcast's RSS feed.
- **GitHub releases:** `url: https://github.com/<owner>/<repo>/releases.atom`, `type: release`.
- **Substack / Medium:** their RSS feed (`https://<name>.substack.com/feed`,
  `https://medium.com/feed/@<user>`).

Items from sources without `always_include` must match a keyword from [topics.yaml](topics.yaml)
(whole word, case-insensitive). Run `python -m radar collect` once to check a new source: the summary
table shows fetched / new / kept / errors per source.

## Scheduling the local run

`claude`, `git` (with push access) and the virtualenv must work for the user the job runs as.

### Windows Task Scheduler

1. Task Scheduler → *Create Task…* → *General*: run only when the user is logged on (so `claude`
   and git credentials are available).
2. *Triggers*: e.g. daily at 07:00.
3. *Actions* → *Start a program*:
   - Program: `C:\path\to\tech-content-radar\.venv\Scripts\python.exe`
   - Arguments: `-m radar run-local`
   - Start in: `C:\path\to\tech-content-radar`

### cron (macOS / Linux)

```cron
0 7 * * * cd /path/to/tech-content-radar && PATH="$HOME/.npm-global/bin:/usr/local/bin:/usr/bin:/bin" .venv/bin/python -m radar run-local >> run-local.log 2>&1
```

Adjust `PATH` so it contains the directory of `claude` (`which claude`); cron starts with a minimal
`PATH`.

## Development

```bash
ruff check .
pytest
```

Tests never touch the network or the real `claude` CLI. CI (`.github/workflows/tests.yml`) runs
both on every push and pull request without the `[local]` extras.
