# Werkstudent Job-Market Tracker 🇩🇪

A daily data pipeline tracking **Werkstudent (working student) roles in AI, ML and Data** across German job boards, built to answer: *which skills, cities and companies drive demand for data-focused working students, and how does that change over time?*

> **Status:** Phase 1 (ingestion) ✅ · Phase 2 (dbt modelling) ⏳ · Phase 3 (skill extraction) ⏳ · Phase 4 (dashboard) ⏳

## Architecture

```
GitHub Actions (daily cron 05:17 UTC)
   │
   ├── Bundesagentur für Arbeit Jobsuche API ──┐   keyword search, 7-day overlap window
   └── Arbeitnow job-board API ────────────────┤   newest-first pagination + client-side filter
                                               ▼
              data/raw/source=<name>/dt=YYYY-MM-DD/HHMMSS.jsonl.gz   (append-only, untouched payloads)
              data/runs.jsonl                                       (per-run health log)
                                               ▼
                         Phase 2: dbt + DuckDB → staging → marts
```

**Design choices**
- **Raw layer is immutable.** Full API payloads are stored as-is, so models can be rebuilt without re-fetching.
- **Overlapping windows.** Each run looks back 7 days, so a missed run fixes itself; dedupe happens downstream.
- **Failure isolation.** If one source fails, the other's data is still committed, and the run goes red so GitHub emails an alert.
- **Polite fetching.** Retries with exponential backoff, a 1 s delay between requests, and an identifying User-Agent.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export PYTHONPATH=src                                 # Windows PowerShell: $env:PYTHONPATH="src"

pytest -q                                   # offline tests
python -m tracker.cli ingest                # fetch everything
python -m tracker.cli ingest -s arbeitnow   # one source
python -m tracker.cli stats                 # summary of collected data
```

Edit `src/tracker/config.py` to change keywords, page limits or the relevance filter.

## Data sources

| Source | Access | Notes |
|---|---|---|
| [Bundesagentur für Arbeit Jobsuche](https://www.arbeitsagentur.de/jobsuche/) | Public client id, documented by [bundesAPI/jobsuche-api](https://github.com/bundesAPI/jobsuche-api) | Germany's largest vacancy database. Unofficial endpoint, so requests are kept gentle. |
| [Arbeitnow](https://www.arbeitnow.com) | [Free job board API](https://www.arbeitnow.com/blog/job-board-api), no key | English-friendly tech roles. Job data courtesy of Arbeitnow. |

Only public job-posting data is collected. No personal or applicant data.

## Repo layout

```
src/tracker/
  config.py              keywords, limits, filters
  http.py                session with retries + rate limiting
  sources/arbeitsagentur.py
  sources/arbeitnow.py
  storage.py             raw JSONL.gz writer/reader, run log
  cli.py                 ingest / stats commands
tests/                   offline tests with faked API responses
.github/workflows/ingest.yml
data/                    raw data committed by the bot
```

## Roadmap
- [x] Phase 1: daily ingestion, raw layer, run monitoring
- [ ] Phase 2: dbt models (`stg_postings`, `fact_posting_snapshots`, `dim_company`), data tests
- [ ] Phase 3: job-description fetch, skill extraction (dictionary + LLM), DE/EN language-requirement tag, evaluated on a hand-labelled set
- [ ] Phase 4: public dashboard (skill trends, cities, posting lifetime)
- [ ] Phase 5: CV-to-posting match score, weekly digest
