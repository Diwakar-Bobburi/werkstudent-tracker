# Werkstudent Job-Market Tracker 🇩🇪

A daily data pipeline tracking **Werkstudent (working student) roles in AI, ML and Data** across German job boards, built to answer: *which skills, cities and companies drive demand for data-focused working students, and how does that change over time?*

> **Status:** Phase 1 (ingestion) ✅ · Phase 2 (dbt modelling + data tests) ✅ · Phase 3 (skill extraction) ⏳ · Phase 4 (dashboard) ⏳

## Architecture

```
GitHub Actions (daily)
   │
   ├── Bundesagentur für Arbeit Jobsuche API ──┐   full open list (100-day window), client-side relevance filter
   └── Arbeitnow job-board API ────────────────┤   whole board, newest-first, client-side filter
                                               ▼
   RAW      data/raw/source=<name>/dt=YYYY-MM-DD/*.jsonl.gz      append-only, untouched API payloads
                                               ▼
   dbt + DuckDB (transform/)
   STAGING  stg_arbeitsagentur, stg_arbeitnow → stg_postings     one shape, cities/states normalised,
                                                                  one row per posting per day
   MARTS    fct_posting_snapshots                                 posting X was listed on day D
            fct_postings                                          one row per posting + lifecycle
            dim_company                                           hiring companies
            mart_daily_market                                     active / new / removed per day
            mart_salary                                           median pay ranges by city & pay unit
   TESTS    31 checks: uniqueness, not-null, accepted values, grain, salary ranges, freshness, city aliases
                                               ▼
   EXPORT   data/marts/*.csv                                      committed daily, readable on GitHub
```

**Design choices**
- **Raw layer is immutable.** Full API payloads are stored as-is (JSON column in DuckDB), so a schema change upstream (e.g. the v4 → v6 rename) is fixed in one staging model with no re-fetch.
- **Full snapshot every day.** A posting that stops appearing was taken down, which makes *time-to-fill* measurable. (Before 2026-11-26 only the last 7 days were fetched; `is_closed_reliably` excludes those closures.)
- **Failure isolation + alerting.** One source failing doesn't block the other; a failed ingest or data test turns the run red so GitHub emails an alert.
- **Polite fetching.** Retries with exponential backoff, a 1 s delay between requests, and an identifying User-Agent.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate   # Windows Git Bash: source .venv/Scripts/activate
pip install -r requirements.txt                       # installs the `tracker` command + dbt-duckdb

pytest -q                       # unit tests (offline)
tracker ingest                  # fetch both sources
tracker build                   # dbt models + 31 data tests, export marts to data/marts/
tracker stats                   # quick summary
```

Explore the warehouse directly: `duckdb data/warehouse.duckdb` → `select * from mart_daily_market;`

Edit `src/tracker/config.py` to change keywords, page limits or the relevance filter, and `transform/seeds/*.csv` to add city/state spellings.

## Data sources

| Source | Access | Notes |
|---|---|---|
| [Bundesagentur für Arbeit Jobsuche](https://www.arbeitsagentur.de/jobsuche/) | Public client id, documented by [bundesAPI/jobsuche-api](https://github.com/bundesAPI/jobsuche-api) | Germany's largest vacancy database. Unofficial endpoint, so requests are kept gentle. |
| [Arbeitnow](https://www.arbeitnow.com) | [Free job board API](https://www.arbeitnow.com/blog/job-board-api), no key | English-friendly tech roles. Job data courtesy of Arbeitnow. |

Only public job-posting data is collected. No personal or applicant data.

## Repo layout

```
transform/                dbt project (staging → marts, seeds, data tests)
src/tracker/
  config.py              keywords, limits, filters
  filters.py             Werkstudent + AI/Data relevance rule
  http.py                session with retries + rate limiting
  sources/arbeitsagentur.py
  sources/arbeitnow.py
  storage.py             raw JSONL.gz writer/reader, run log
  cli.py                 ingest / build / export / stats commands
tests/                   offline tests with faked API responses
.github/workflows/ingest.yml
data/raw, data/marts     raw snapshots + exported marts, committed by the bot
```

## Roadmap
- [x] Phase 1: daily ingestion, raw layer, run monitoring
- [x] Phase 2: dbt models, posting lifecycle, data tests in CI, CSV export
- [ ] Phase 3: job-description fetch, skill extraction (dictionary + LLM), DE/EN language-requirement tag, evaluated on a hand-labelled set
- [ ] Phase 4: public dashboard (skill trends, cities, posting lifetime)
- [ ] Phase 5: CV-to-posting match score, weekly digest
