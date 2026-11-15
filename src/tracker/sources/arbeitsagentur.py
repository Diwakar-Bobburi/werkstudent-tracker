"""Bundesagentur für Arbeit Jobsuche (unofficial public endpoint).

Docs (community): https://github.com/bundesAPI/jobsuche-api
The API version and field names change without notice (v4 `stellenangebote` -> v6 `ergebnisliste`),
so this module resolves the endpoint at runtime and reads fields defensively.
"""
import logging
from typing import Iterator

import requests

from tracker import config
from tracker.filters import is_relevant
from tracker.http import get_json

log = logging.getLogger(__name__)
SOURCE = "arbeitsagentur"

LIST_KEYS = ("ergebnisliste", "stellenangebote")
ID_KEYS = ("refnr", "referenznummer", "hashId", "id")
TITLE_KEYS = ("titel", "stellenangebotsTitel", "title")


def _first(d: dict, keys) -> object:
    for k in keys:
        if d.get(k):
            return d[k]
    return None


def _occupations(job: dict) -> str:
    occ = job.get("alleBerufe") or [job.get("hauptberuf") or job.get("beruf") or ""]
    return " ".join(o for o in occ if o)


def _jobs(data: dict) -> list[dict]:
    for k in LIST_KEYS:
        if isinstance(data.get(k), list):
            return data[k]
    return []


def _resolve_url(session, headers) -> str:
    """Return the first endpoint version that responds."""
    errors = []
    for url in config.BA_URLS:
        try:
            get_json(session, url, params={"was": "Werkstudent", "size": 1}, headers=headers)
            log.info("BA endpoint: %s", url)
            return url
        except requests.HTTPError as exc:
            errors.append(f"{url} -> {exc.response.status_code}")
    raise RuntimeError("No Arbeitsagentur endpoint answered: " + "; ".join(errors))


def fetch(session, published_since_days: int | None = None) -> Iterator[dict]:
    """Yield relevant raw postings, each with `_query` and a stable `_id`."""
    headers = {"X-API-Key": config.BA_API_KEY}
    url = _resolve_url(session, headers)
    days = published_since_days or config.BA_PUBLISHED_SINCE_DAYS
    warned_schema = False

    for keyword in config.BA_KEYWORDS:
        for page in range(1, config.BA_MAX_PAGES + 1):
            params = {"was": keyword, "veroeffentlichtseit": days, "page": page, "size": config.BA_PAGE_SIZE}
            data = get_json(session, url, params=params, headers=headers)
            jobs = _jobs(data)
            total = int(data.get("maxErgebnisse") or 0)

            kept = 0
            for job in jobs:
                job_id = _first(job, ID_KEYS)
                title = _first(job, TITLE_KEYS) or ""
                if job_id is None or not title:
                    if not warned_schema:
                        log.warning("BA item missing id/title; item keys = %s", sorted(job))
                        warned_schema = True
                    continue
                if is_relevant(title, extra=_occupations(job), student_hint=False):
                    kept += 1
                    yield {"_query": keyword, "_id": str(job_id), **job}

            log.info("BA %r page %d: %d jobs, %d relevant (total %d)", keyword, page, len(jobs), kept, total)
            if not jobs or page * config.BA_PAGE_SIZE >= total:
                break


def _location(raw: dict) -> dict:
    """v6: stellenlokationen[0].adresse + breite/laenge; v4: arbeitsort."""
    locs = raw.get("stellenlokationen") or []
    if locs:
        loc = locs[0] or {}
        addr = loc.get("adresse") or {}
        return {**addr, "lat": loc.get("breite"), "lon": loc.get("laenge")}
    ort = raw.get("arbeitsort") or {}
    koord = ort.get("koordinaten") or {}
    return {**ort, "lat": koord.get("lat"), "lon": koord.get("lon")}


def normalize(raw: dict) -> dict:
    """Map German field names (v6, with v4 fallbacks) to a flat, source-agnostic shape."""
    loc = _location(raw)
    job_id = raw.get("_id") or _first(raw, ID_KEYS)
    occ = raw.get("alleBerufe") or ([raw["hauptberuf"]] if raw.get("hauptberuf") else [])
    if not occ and raw.get("beruf"):
        occ = [raw["beruf"]]
    published = raw.get("datumErsteVeroeffentlichung") or raw.get("aktuelleVeroeffentlichungsdatum") \
        or (raw.get("veroeffentlichungszeitraum") or {}).get("von")
    return {
        "source": SOURCE,
        "source_id": job_id,
        "title": _first(raw, TITLE_KEYS),
        "company": raw.get("firma") or raw.get("arbeitgeber"),
        "city": loc.get("ort"),
        "region": (loc.get("region") or "").title() or None,   # NIEDERSACHSEN -> Niedersachsen
        "country": (loc.get("land") or "").title() or None,
        "lat": loc.get("lat"),
        "lon": loc.get("lon"),
        "published_at": published,
        "url": raw.get("externeUrl")
        or (f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{job_id}" if job_id else None),
        "remote": None,
        "tags": occ,
        "salary_min": raw.get("gehaltsspanneVon"),
        "salary_max": raw.get("gehaltsspanneBis"),
        "salary_unit": raw.get("verguetungsangabe"),  # e.g. STUNDENLOHN / MONATSGEHALT, as given
        "description": None,  # listing endpoint has no description; fetched in Phase 3
    }
