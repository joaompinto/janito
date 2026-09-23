# Overall-use accounting

Janito keeps a **local SQLite log of every completed LLM turn** (issue #72) so
you can see how many tokens and how much money each provider/model has cost
you, per working directory, over time.

## Where the data lives

The log is stored at:

```
<config dir>/accounting.db
```

where the config dir is `~/.janito` by default (honoring `-c/--config-dir`
and `-l/--local` like every other config file, mirroring the `tools_use.db`
pattern).

## What is recorded

One row is appended per **completed turn that reported token usage** — from
the interactive shell, `/ask`, `/compact`, one-shot prompts and the web UI.
Each row has:

| Column         | Meaning                                                        |
|----------------|----------------------------------------------------------------|
| `cwd`          | Working directory the turn ran in                              |
| `timestamp`    | UTC time the turn completed (ISO-8601)                         |
| `provider`     | Provider that served the turn (e.g. `deepseek`)                |
| `model`        | Model used (e.g. `deepseek-flash`)                          |
| `input_tokens` | Turn-wide input tokens (all API rounds of the turn included)   |
| `cached_tokens`| Turn-wide cached input tokens (`NULL` when not reported)       |
| `output_tokens`| Turn-wide output tokens (all API rounds of the turn included)  |
| `cost`         | Estimated cost in dollars (REAL), `NULL` when unknown          |

The token counters are the **turn-wide cumulative** values (tool-call rounds
included) and the cost is the numeric dollar estimate — the same estimate the
end-of-turn `Cost:` summary shows, but stored as a plain number so it can be
summed and aggregated.

!!! note
    Accounting is a best-effort side feature: it never raises and can never
    break tool execution or the agent loop. Rows are only written for turns
    that completed successfully and reported usage.

## Retention

On every startup Janito **prunes entries older than 10 days** from
`accounting.db` (issue #76), so the database reflects roughly the last ten
days of usage and does not grow unbounded. Pruning is best-effort like every
other database access — it never raises and never breaks startup.

## Inspecting the log

The interactive shell offers a `/use_stats` command (issue #75) that reads
the accounting database and prints the **last 10 days** as two rich tables.
The first groups the rows **by calendar day** — one row per day with the
summed input/cached/output tokens and the summed estimated cost. The
`input_tokens` column is the day's **total** input — the API reports
`prompt_tokens`/`input_tokens` with the cached tokens counted inside them —
and the cached-token value is followed by the percentage of that total input
that was served from cache (`cached / input`, rounded to a whole number).
The cost column is rendered with the **same adaptive, magnitude-aware format
the end-of-turn `Cost:` summary uses** (issue #67): `0.abc¢` below one cent,
`X.a¢` below one dollar, `X.a$` below $100 and `X$` above — `N/A` when no
cost was reported:

```text
                 Usage Statistics (last 10 days)
┏━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Day          ┃ Input tokens   ┃ Cached tokens   ┃ Output tokens   ┃     Cost ┃
┡━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ 2026-08-28   │          1,200 │     300 (25%)   │             800 │   0.170¢ │
│ 2026-08-29   │          1,800 │     600 (33%)   │           1,600 │   0.240¢ │
└──────────────┴────────────────┴─────────────────┴─────────────────┴──────────┘
Database: /home/me/.janito/accounting.db
```

The second table breaks the same period down **by day, provider and model**,
so you can see at a glance which model drove the usage on each day:

```text
                                 Per Model Statistics (last 10 days)
┏━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ Day            ┃ Provider  ┃ Model                 ┃ Input tokens    ┃ Cached tokens    ┃ Output tokens    ┃       Cost ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━┩
│ 2026-08-28     │ deepseek  │ deepseek-flash     │             180 │          6 (6%)  │              120 │    0.010¢ │
│ 2026-08-28     │ openai    │ gpt-6-luna          │           1,200 │       300 (25%)  │              800 │    0.170¢ │
│ 2026-08-29     │ openai    │ gpt-6-luna          │           1,800 │       600 (33%)  │            1,600 │    0.240¢ │
└────────────────┴───────────┴───────────────────────┴─────────────────┴──────────────────┴──────────────────┴────────────┘
```

Turns whose provider or model is unknown (e.g. rows recorded without one)
are grouped under `unknown`, and their cost column shows `N/A` when no cost
was reported — the same best-effort fallbacks the daily table uses.

The module also ships a small command-line inspector:

```bash
python -m janito.tooling.accounting            # last 10 rows
python -m janito.tooling.accounting --limit 50 # last 50 rows
python -m janito.tooling.accounting --json     # JSON output
```

Example output:

```
2026-08-28T17:47:34.778205+00:00  /home/me/proj  deepseek/deepseek-flash  in=180 cached=10 out=120  cost=0.0001$
2026-08-28T17:47:34.778580+00:00  /home/me/proj  openai/gpt-6-luna          in=50000 cached=5000 out=4000  cost=0.0150$
```

## Querying with SQL

`accounting.db` is a plain SQLite database, so you can query it directly:

```bash
sqlite3 ~/.janito/accounting.db \
  "SELECT provider, model, SUM(input_tokens) AS in, SUM(output_tokens) AS out,
          ROUND(SUM(cost), 4) AS total_cost
   FROM accounting GROUP BY provider, model ORDER BY total_cost DESC;"
```

```bash
sqlite3 ~/.janito/accounting.db \
  "SELECT cwd, COUNT(*) AS turns, ROUND(SUM(cost), 4) AS total_cost
   FROM accounting GROUP BY cwd ORDER BY total_cost DESC;"
```
