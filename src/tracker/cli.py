"""Command line entry point.

    python -m tracker.cli ingest            # fetch all sources, write raw files
    python -m tracker.cli ingest -s arbeitnow
    python -m tracker.cli ingest --backfill-days 100   # one-off history grab
    python -m tracker.cli stats             # quick sanity summary of everything collected
    python -m tracker.cli details           # full descriptions for new Arbeitsagentur postings
    python -m tracker.cli build             # dbt models + data tests, then CSV export to data/marts/
"""
import argparse
import itertools
import logging
import sys
import time
from datetime import datetime, timezone

from tracker import storage
from tracker.http import make_session
from tracker.sources import SOURCES

log = logging.getLogger("tracker")
ID_KEYS = {"arbeitsagentur": "_id", "arbeitnow": "slug"}


def ingest(source_names: list[str], backfill_days: int | None = None) -> int:
    session = make_session()
    fetched_at = datetime.now(timezone.utc)
    run_id = fetched_at.strftime("%Y%m%dT%H%M%SZ")
    failures = 0
    total = 0

    for name in source_names:
        module = SOURCES[name]
        start = time.monotonic()
        entry = {"run_id": run_id, "source": name, "started_at": fetched_at.isoformat()}
        try:
            records = module.fetch(session, backfill_days) if (backfill_days and name == "arbeitsagentur") else module.fetch(session)
            path, n = storage.write_raw(name, run_id, fetched_at, records, ID_KEYS[name])
            entry.update(status="ok" if n else "empty", n_postings=n, file=str(path) if path else None)
            total += n
            log.info("%s: %d unique postings -> %s", name, n, path)
        except Exception as exc:  # one source failing must not kill the other
            failures += 1
            entry.update(status="error", n_postings=0, error=f"{type(exc).__name__}: {exc}")
            log.exception("%s failed", name)
        entry["duration_s"] = round(time.monotonic() - start, 1)
        storage.append_run_log(entry)

    # Non-zero exit makes the GitHub Action go red -> you get an email. That's the monitoring.
    if failures or total == 0:
        log.error("Run unhealthy: %d source(s) failed, %d postings total", failures, total)
        return 1
    return 0


def stats() -> int:
    import duckdb

    rows = []
    for env in storage.iter_raw():
        if env["source"] not in SOURCES:   # e.g. description records: not postings
            continue
        norm = SOURCES[env["source"]].normalize(env["payload"])
        rows.append({**norm, "fetched_at": env["fetched_at"], "query": env["payload"].get("_query")})
    if not rows:
        print("No raw data yet. Run: python -m tracker.cli ingest")
        return 0

    import json
    import tempfile

    con = duckdb.connect()
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as tmp:
        tmp.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    con.execute(f"CREATE TABLE postings AS SELECT * FROM read_json_auto('{tmp.name}', format='newline_delimited')")
    con.execute("""
        CREATE VIEW latest AS
        SELECT * FROM postings
        QUALIFY row_number() OVER (PARTITION BY source, source_id ORDER BY fetched_at DESC) = 1
    """)
    q = lambda sql: print(con.sql(sql))  # noqa: E731
    print("\n== Unique postings per source ==")
    q("SELECT source, count(*) AS postings, min(fetched_at)::DATE AS first_seen, max(fetched_at)::DATE AS last_seen FROM latest GROUP BY 1")
    print("\n== Snapshots per day ==")
    q("SELECT fetched_at::DATE AS day, source, count(DISTINCT source_id) AS postings FROM postings GROUP BY 1, 2 ORDER BY 1 DESC, 2 LIMIT 14")
    print("\n== Top cities ==")
    q("SELECT city, count(*) AS n FROM latest WHERE city IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 10")
    print("\n== Top companies ==")
    q("SELECT company, count(*) AS n FROM latest GROUP BY 1 ORDER BY 2 DESC LIMIT 10")
    return 0


DETAIL_BATCH = 25


def details(limit: int | None = None) -> int:
    """Fetch full descriptions for Arbeitsagentur postings not seen before (once per posting)."""
    from tracker.sources import arbeitsagentur_details as d

    fetched_at = datetime.now(timezone.utc)
    run_id = fetched_at.strftime("%Y%m%dT%H%M%SZ")
    start = time.monotonic()
    entry = {"run_id": run_id, "source": d.SOURCE, "started_at": fetched_at.isoformat()}
    report: dict = {}
    n_total, parts, rc = 0, [], 0
    records = d.fetch(make_session(), limit, report)
    try:
        # Save in batches of 25: Ctrl+C or a crash loses at most one batch, never the whole run.
        while True:
            batch = list(itertools.islice(records, DETAIL_BATCH))
            if not batch:
                break
            path, n = storage.write_raw(d.SOURCE, run_id, fetched_at, batch, "_id", part=len(parts))
            n_total += n
            parts.append(str(path))
            log.info("%s: saved %d so far", d.SOURCE, n_total)
    except KeyboardInterrupt:
        log.warning("%s: interrupted - %d records already saved, the rest is fetched next run", d.SOURCE, n_total)
        report["aborted"] = True
    except Exception as exc:
        entry.update(error=f"{type(exc).__name__}: {exc}")
        log.exception("%s failed", d.SOURCE)
        report["aborted"] = True
    bad = report.get("aborted") or report.get("errors")
    entry.update(status="partial" if bad else "ok", n_postings=n_total, errors=report.get("errors", 0),
                 aborted=report.get("aborted", False), files=parts)
    rc = 1 if report.get("aborted") else 0
    entry["duration_s"] = round(time.monotonic() - start, 1)
    storage.append_run_log(entry)
    return rc


MART_TABLES = ["fct_postings", "dim_company", "mart_daily_market", "mart_salary"]


def _ensure_raw_placeholders() -> None:
    """dbt reads every raw source with a glob; DuckDB errors on a glob with no files.
    An empty gzip file per source keeps fresh clones and new sources buildable."""
    import gzip

    from tracker import config
    from tracker.sources import arbeitsagentur_details

    for source in [*SOURCES, arbeitsagentur_details.SOURCE]:
        src_dir = config.RAW_DIR / f"source={source}"
        if not any(src_dir.glob("*/*.jsonl.gz")):
            placeholder = src_dir / "dt=0000-00-00" / "placeholder.jsonl.gz"
            placeholder.parent.mkdir(parents=True, exist_ok=True)
            gzip.open(placeholder, "wt").close()


def build(skip_export: bool = False) -> int:
    """Run dbt (models + data tests) and export the marts as CSVs for GitHub / the dashboard."""
    import shutil
    import subprocess

    from tracker import config

    transform_dir = config.ROOT / "transform"
    _ensure_raw_placeholders()
    dbt = shutil.which("dbt")
    if not dbt:
        log.error("dbt not found. Run: pip install -e .[transform]")
        return 1
    result = subprocess.run([dbt, "build", "--profiles-dir", "."], cwd=transform_dir)
    if result.returncode != 0:
        log.error("dbt build failed (a model or data test broke) - see output above")
        return result.returncode
    return 0 if skip_export else export()


def export() -> int:
    import duckdb

    from tracker import config

    out_dir = config.DATA_DIR / "marts"
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(config.DATA_DIR / "warehouse.duckdb"), read_only=True)
    for table in MART_TABLES:
        path = out_dir / f"{table}.csv"
        con.execute(f"COPY (SELECT * FROM {table}) TO '{path.as_posix()}' (HEADER, DELIMITER ',')")
        n = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        log.info("exported %s (%d rows) -> %s", table, n, path)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tracker")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_ing = sub.add_parser("ingest", help="fetch postings and write raw files")
    p_ing.add_argument("-s", "--source", action="append", choices=list(SOURCES), help="default: all")
    p_ing.add_argument("--backfill-days", type=int, help="one-off: look back N days (max 100) on Arbeitsagentur")
    sub.add_parser("stats", help="print a summary of collected data")
    p_det = sub.add_parser("details", help="fetch full descriptions for new Arbeitsagentur postings")
    p_det.add_argument("--limit", type=int, help="max postings this run (default from config)")
    p_build = sub.add_parser("build", help="run dbt models + data tests, then export marts to data/marts/")
    p_build.add_argument("--no-export", action="store_true")
    sub.add_parser("export", help="export marts from data/warehouse.duckdb to CSV")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.cmd == "ingest":
        return ingest(args.source or list(SOURCES), args.backfill_days)
    if args.cmd == "details":
        return details(args.limit)
    if args.cmd == "build":
        return build(skip_export=args.no_export)
    if args.cmd == "export":
        return export()
    return stats()


if __name__ == "__main__":
    sys.exit(main())
