"""Offline tests: API calls are faked with fixture payloads shaped like the real responses."""
import time

import pytest

from tracker import cli, config, storage
from tracker.sources import arbeitnow, arbeitsagentur


@pytest.fixture(autouse=True)
def tmp_data(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "RUN_LOG", tmp_path / "runs.jsonl")
    monkeypatch.setattr(config, "REQUEST_DELAY_SECONDS", 0)
    return tmp_path


def ba_job(refnr, titel="Werkstudent Data Science (m/w/d)", beruf="Data Scientist"):
    # v6 item shape, copied from a live response (Nov 2026)
    return {
        "referenznummer": refnr, "stellenangebotsTitel": titel, "stellenangebotsart": "ARBEIT",
        "hauptberuf": beruf, "alleBerufe": [beruf],
        "firma": "Beispiel GmbH",
        "stellenlokationen": [{"adresse": {"plz": "80331", "ort": "München", "region": "BAYERN",
                                           "land": "DEUTSCHLAND"}, "breite": 48.13, "laenge": 11.57}],
        "datumErsteVeroeffentlichung": "2026-11-05",
        "verguetungsangabe": "STUNDENLOHN", "gehaltsspanneVon": 800.0, "gehaltsspanneBis": 1600.0,
    }


V4_JOB = {
    "refnr": "9", "titel": "Werkstudent Data (m/w/d)", "beruf": "Informatiker/in", "arbeitgeber": "Alt GmbH",
    "arbeitsort": {"ort": "Köln", "region": "Nordrhein-Westfalen", "land": "Deutschland"},
    "aktuelleVeroeffentlichungsdatum": "2026-01-01",
}


def an_job(slug, title, tags=(), days_old=0):
    return {
        "slug": slug, "title": title, "company_name": "Acme", "location": "Berlin",
        "remote": False, "tags": list(tags), "job_types": [], "url": f"https://www.arbeitnow.com/jobs/{slug}",
        "description": "<p>...</p>", "created_at": int(time.time()) - days_old * 86400,
    }


def test_ba_paginates_and_stops(monkeypatch):
    monkeypatch.setattr(config, "BA_KEYWORDS", ["Werkstudent Data"])
    monkeypatch.setattr(config, "BA_PAGE_SIZE", 2)
    pages = {1: [ba_job("1"), ba_job("2", "Werkstudent Marketing", beruf="Marketingassistent/in")], 2: [ba_job("3")]}
    calls = []

    def fake_get(session, url, params=None, headers=None):
        assert headers["X-API-Key"] == "jobboerse-jobsuche"
        if "page" not in params:  # endpoint probe
            return {"ergebnisliste": [], "maxErgebnisse": 0}
        calls.append(params["page"])
        return {"ergebnisliste": pages.get(params["page"], []), "maxErgebnisse": 3}

    monkeypatch.setattr(arbeitsagentur, "get_json", fake_get)
    jobs = list(arbeitsagentur.fetch(None))
    assert [j["_id"] for j in jobs] == ["1", "3"]  # marketing role filtered out
    assert calls == [1, 2]  # stopped once page * size >= total


def test_ba_falls_back_to_next_endpoint_version(monkeypatch):
    import requests

    monkeypatch.setattr(config, "BA_URLS", ["https://x/v6/jobs", "https://x/v5/jobs"])
    monkeypatch.setattr(config, "BA_KEYWORDS", ["Werkstudent Data"])
    used = []

    def fake_get(session, url, params=None, headers=None):
        if "v6" in url:
            resp = requests.Response()
            resp.status_code = 403
            raise requests.HTTPError(response=resp)
        used.append(url)
        return {"ergebnisliste": [ba_job("1")] if "page" in params else [], "maxErgebnisse": 1}

    monkeypatch.setattr(arbeitsagentur, "get_json", fake_get)
    assert [j["_id"] for j in arbeitsagentur.fetch(None)] == ["1"]
    assert set(used) == {"https://x/v5/jobs"}


@pytest.mark.parametrize("title,tags,expected", [
    ("Werkstudent Data Engineering (m/w/d)", [], True),
    ("Working Student Machine Learning", [], True),
    ("Working Student", ["Python", "Data"], True),
    ("Werkstudent Marketing", ["Social Media"], False),
    ("Senior Data Engineer", ["Python"], False),
    ("Werkstudent Maintenance", [], False),  # "ai" inside a word must not match
])
def test_arbeitnow_relevance(title, tags, expected):
    assert arbeitnow.is_relevant(an_job("x", title, tags)) is expected


def test_arbeitnow_stops_at_lookback(monkeypatch):
    monkeypatch.setattr(config, "ARBEITNOW_LOOKBACK_DAYS", 7)
    pages = {
        1: [an_job("a", "Werkstudent Data"), an_job("b", "Sales Manager")],
        2: [an_job("c", "Werkstudent AI", days_old=30)],
        3: [an_job("d", "Werkstudent Data", days_old=40)],
    }
    calls = []

    def fake_get(session, url, params=None, headers=None):
        calls.append(params["page"])
        return {"data": pages[params["page"]], "links": {"next": "more"}}

    monkeypatch.setattr(arbeitnow, "get_json", fake_get)
    assert [j["slug"] for j in arbeitnow.fetch(None)] == ["a", "c"]
    assert calls == [1, 2]


def test_ingest_dedupes_writes_and_logs(monkeypatch):
    monkeypatch.setattr(arbeitsagentur, "fetch", lambda s: iter([{"_id": i, **ba_job(i)} for i in ("1", "1", "2")]))
    monkeypatch.setattr(arbeitnow, "fetch", lambda s: iter([an_job("a", "Werkstudent Data")]))
    assert cli.ingest(["arbeitsagentur", "arbeitnow"]) == 0

    envs = list(storage.iter_raw())
    assert sorted(e["payload"].get("_id") or e["payload"]["slug"] for e in envs) == ["1", "2", "a"]
    assert config.RUN_LOG.read_text().count('"status": "ok"') == 2


def test_one_source_failing_still_saves_the_other(monkeypatch):
    def boom(session):
        raise ConnectionError("API down")
        yield  # pragma: no cover

    monkeypatch.setattr(arbeitsagentur, "fetch", boom)
    monkeypatch.setattr(arbeitnow, "fetch", lambda s: iter([an_job("a", "Werkstudent Data")]))
    assert cli.ingest(["arbeitsagentur", "arbeitnow"]) == 1  # red build -> email alert
    assert len(list(storage.iter_raw())) == 1
    assert '"status": "error"' in config.RUN_LOG.read_text()


def test_normalize_shapes_match():
    a = arbeitsagentur.normalize(ba_job("1"))
    b = arbeitnow.normalize(an_job("x", "Werkstudent Data"))
    assert a.keys() == b.keys()
    assert a["city"] == "München" and b["city"] == "Berlin"


def test_ba_normalize_v6_fields():
    n = arbeitsagentur.normalize(ba_job("1"))
    assert n["source_id"] == "1"
    assert n["company"] == "Beispiel GmbH"
    assert (n["region"], n["country"]) == ("Bayern", "Deutschland")
    assert (n["lat"], n["lon"]) == (48.13, 11.57)
    assert (n["salary_min"], n["salary_max"], n["salary_unit"]) == (800.0, 1600.0, "STUNDENLOHN")
    assert n["published_at"] == "2026-11-05"
    assert n["url"].endswith("/jobdetail/1")


def test_ba_normalize_v4_fallback():
    n = arbeitsagentur.normalize(V4_JOB)
    assert (n["company"], n["city"], n["published_at"]) == ("Alt GmbH", "Köln", "2026-01-01")


def test_stats_runs(monkeypatch, capsys):
    monkeypatch.setattr(arbeitsagentur, "fetch", lambda s: iter([{"_id": i, **ba_job(i)} for i in ("1", "2")]))
    monkeypatch.setattr(arbeitnow, "fetch", lambda s: iter([an_job("a", "Werkstudent Data")]))
    cli.ingest(["arbeitsagentur", "arbeitnow"])
    assert cli.stats() == 0
    out = capsys.readouterr().out
    assert "München" in out and "Berlin" in out


def test_ba_still_reads_old_v4_shape(monkeypatch):
    monkeypatch.setattr(config, "BA_KEYWORDS", ["Werkstudent"])
    monkeypatch.setattr(arbeitsagentur, "get_json",
                        lambda s, u, params=None, headers=None: {"stellenangebote": [V4_JOB], "maxErgebnisse": 1})
    assert [j["_id"] for j in arbeitsagentur.fetch(None)] == ["9"]


def test_ba_warns_when_item_schema_unknown(monkeypatch, caplog):
    monkeypatch.setattr(config, "BA_KEYWORDS", ["Werkstudent"])
    monkeypatch.setattr(arbeitsagentur, "get_json",
                        lambda s, u, params=None, headers=None: {"ergebnisliste": [{"foo": 1}], "maxErgebnisse": 1})
    assert list(arbeitsagentur.fetch(None)) == []
    assert "item keys = ['foo']" in caplog.text
