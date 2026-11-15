"""Raw layer: append-only, gzipped JSON Lines, partitioned by source and date.

data/raw/source=<name>/dt=YYYY-MM-DD/<HHMMSS>.jsonl.gz

Each line is an envelope: {run_id, source, fetched_at, payload}. We keep the
untouched API payload so later phases can re-derive anything without re-fetching.
"""
import gzip
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator

from tracker import config


def write_raw(source: str, run_id: str, fetched_at: datetime, records: Iterable[dict], key: str) -> tuple[Path | None, int]:
    """Write records for one source/run, deduplicated on `key`. Returns (path, n_written)."""
    seen, rows = set(), []
    for rec in records:
        rid = rec.get(key)
        if rid is None or rid in seen:
            continue
        seen.add(rid)
        rows.append({"run_id": run_id, "source": source, "fetched_at": fetched_at.isoformat(), "payload": rec})
    if not rows:
        return None, 0

    out_dir = config.RAW_DIR / f"source={source}" / f"dt={fetched_at:%Y-%m-%d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{fetched_at:%H%M%S}.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path, len(rows)


def iter_raw(raw_dir: Path | None = None) -> Iterator[dict]:
    for path in sorted((raw_dir or config.RAW_DIR).glob("source=*/dt=*/*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                yield json.loads(line)


def append_run_log(entry: dict) -> None:
    config.RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(config.RUN_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
