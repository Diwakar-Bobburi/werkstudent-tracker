"""Arbeitnow free job-board API (no key). Terms ask for a link back to arbeitnow.com.

The API has no keyword search, so we paginate newest-first and filter client-side.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Iterator

from tracker import config
from tracker.filters import has_term
from tracker.filters import is_relevant as _is_relevant
from tracker.http import get_json

log = logging.getLogger(__name__)
SOURCE = "arbeitnow"


def is_relevant(job: dict) -> bool:
    job_types = " ".join(job.get("job_types") or [])
    return _is_relevant(
        job.get("title") or "",
        extra=" ".join(job.get("tags") or []),
        student_hint=has_term(job_types, ["working student", "werkstudent"]),
    )


def fetch(session) -> Iterator[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=config.ARBEITNOW_LOOKBACK_DAYS)
    for page in range(1, config.ARBEITNOW_MAX_PAGES + 1):
        data = get_json(session, config.ARBEITNOW_URL, params={"page": page})
        jobs = data.get("data") or []
        kept = [j for j in jobs if is_relevant(j)]
        log.info("Arbeitnow page %d: %d jobs, %d relevant", page, len(jobs), len(kept))
        yield from ({"_query": "filter:werkstudent+data", **j} for j in kept)

        oldest = min((j.get("created_at") or 0 for j in jobs), default=0)
        if not jobs or not (data.get("links") or {}).get("next"):
            break
        if oldest and datetime.fromtimestamp(oldest, timezone.utc) < cutoff:
            break


def normalize(raw: dict) -> dict:
    created = raw.get("created_at")
    return {
        "source": SOURCE,
        "source_id": raw.get("slug"),
        "title": raw.get("title"),
        "company": raw.get("company_name"),
        "city": raw.get("location"),
        "region": None,
        "country": None,
        "lat": None,
        "lon": None,
        "published_at": datetime.fromtimestamp(created, timezone.utc).date().isoformat() if created else None,
        "url": raw.get("url"),
        "remote": raw.get("remote"),
        "tags": raw.get("tags") or [],
        "salary_min": None,
        "salary_max": None,
        "salary_unit": None,
        "description": raw.get("description"),
    }
