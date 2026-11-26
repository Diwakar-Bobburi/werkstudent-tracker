"""Full job descriptions for Arbeitsagentur postings.

The search endpoint has no description text, and postings disappear within weeks,
so each relevant posting's details are fetched ONCE, on the day it is first seen,
and stored in the raw layer forever.

Endpoint (community docs: github.com/bundesAPI/jobsuche-api):
    GET /pc/v4/jobdetails/{base64(refnr)}   (v3 as fallback)
"""
import base64
import gzip
import json
import logging
from typing import Iterator
from urllib.parse import quote

import requests

from tracker import config
from tracker.http import get_json

log = logging.getLogger(__name__)
SOURCE = "arbeitsagentur_details"

# Fields that have held the description text across API versions; first non-empty wins.
DESCRIPTION_KEYS = ("stellenangebotsBeschreibung", "stellenbeschreibung", "beschreibung", "description")


def encode_refnr(refnr: str, urlsafe: bool = False) -> str:
    raw = (base64.urlsafe_b64encode if urlsafe else base64.b64encode)(refnr.encode()).decode()
    return quote(raw, safe="")  # "/" or "+" in standard base64 must not break the URL path


def extract_description(detail: dict) -> str | None:
    for k in DESCRIPTION_KEYS:
        if isinstance(detail.get(k), str) and detail[k].strip():
            return detail[k]
    # Unknown schema: fall back to the longest string field, which is the description in practice.
    strings = [v for v in detail.values() if isinstance(v, str)]
    longest = max(strings, key=len, default="")
    return longest if len(longest) > 200 else None


def _known_ids() -> set[str]:
    """IDs already fetched (found or not) in earlier runs."""
    ids = set()
    for path in (config.RAW_DIR / f"source={SOURCE}").glob("*/*.jsonl.gz"):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                ids.add(json.loads(line)["payload"]["_id"])
    return ids


def _latest_listing_ids() -> list[str]:
    """Posting IDs from the most recent Arbeitsagentur listing run."""
    files = sorted((config.RAW_DIR / "source=arbeitsagentur").glob("*/*.jsonl.gz"))
    if not files:
        return []
    ids = []
    with gzip.open(files[-1], "rt", encoding="utf-8") as f:
        for line in f:
            ids.append(json.loads(line)["payload"]["_id"])
    return ids


class EndpointUnavailable(RuntimeError):
    """Every endpoint refused us (not "posting gone"): API change or blocked key. Stop the run."""


def _fetch_one(session, refnr: str, headers: dict) -> dict:
    statuses = []
    for base in config.BA_DETAIL_URLS:
        for urlsafe in (False, True):
            url = f"{base}/{encode_refnr(refnr, urlsafe)}"
            try:
                return {"_status": "ok", "_endpoint": base, **get_json(session, url, headers=headers)}
            except requests.HTTPError as exc:
                code = exc.response.status_code
                statuses.append(code)
                # 400/404 = this posting isn't there; 403 "No match found" = this endpoint/route doesn't exist.
                if code not in (400, 403, 404):
                    raise
    if 404 in statuses or 400 in statuses:
        # A live endpoint said the posting doesn't exist: it expired. Remember that, don't retry daily.
        return {"_status": "not_found", "_http_statuses": statuses}
    raise EndpointUnavailable(f"{refnr}: every endpoint refused ({statuses})")


MAX_ERRORS_PER_RUN = 5


def fetch(session, limit: int | None = None, report: dict | None = None) -> Iterator[dict]:
    """Yield one detail record per new posting.

    Never raises mid-run: whatever was fetched so far is still yielded (and saved).
    Problems are reported in `report` so the caller can fail the run afterwards.
    """
    report = {} if report is None else report
    report.update(errors=0, aborted=False)
    headers = {"X-API-Key": config.BA_API_KEY}
    todo = [i for i in dict.fromkeys(_latest_listing_ids()) if i not in _known_ids()]
    limit = config.BA_DETAIL_MAX_PER_RUN if limit is None else limit
    if len(todo) > limit:
        log.info("BA details: %d new postings, fetching %d this run (rest tomorrow)", len(todo), limit)
        todo = todo[:limit]
    found = gone = 0
    for refnr in todo:
        try:
            detail = _fetch_one(session, refnr, headers)
        except EndpointUnavailable as exc:
            log.error("BA details: stopping run - %s", exc)
            report["aborted"] = True
            break
        except Exception as exc:  # one bad posting must not cost us the rest; it is retried next run
            report["errors"] += 1
            log.warning("BA details: %s failed (%s: %s) - will retry next run", refnr, type(exc).__name__, exc)
            if report["errors"] >= MAX_ERRORS_PER_RUN:
                log.error("BA details: %d errors, stopping run", report["errors"])
                report["aborted"] = True
                break
            continue
        found += detail["_status"] == "ok"
        gone += detail["_status"] == "not_found"
        done = found + gone
        if done % 10 == 0 or done == len(todo):
            log.info("BA details: %d/%d done (%d found, %d already gone)", done, len(todo), found, gone)
        yield {"_id": refnr, **detail}
    log.info("BA details: %d found, %d already gone, %d errors", found, gone, report["errors"])
