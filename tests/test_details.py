"""Offline tests for fetching Arbeitsagentur job descriptions."""
import base64
from datetime import datetime, timezone

import pytest
import requests

from tracker import cli, config, storage
from tracker.sources import arbeitsagentur_details as d


@pytest.fixture(autouse=True)
def tmp_data(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(config, "RUN_LOG", tmp_path / "runs.jsonl")
    monkeypatch.setattr(config, "REQUEST_DELAY_SECONDS", 0)
    monkeypatch.setattr(config, "BA_DETAIL_URLS", ["https://x/v4/jobdetails", "https://x/v3/jobdetails"])


def write_listing(ids):
    t = datetime.now(timezone.utc)
    storage.write_raw("arbeitsagentur", "r", t, [{"_id": i, "referenznummer": i} for i in ids], "_id")


def http_error(status):
    resp = requests.Response()
    resp.status_code = status
    return requests.HTTPError(response=resp)


def test_encode_refnr_matches_documented_example():
    # Example from the bundesAPI docs: 10001-1002716922-S -> MTAwMDEtMTAwMjcxNjkyMi1T
    assert d.encode_refnr("10001-1002716922-S") == "MTAwMDEtMTAwMjcxNjkyMi1T"


def test_encode_refnr_escapes_slash():
    refnr = next(r for r in (f"x{i}?" for i in range(500)) if "/" in base64.b64encode(r.encode()).decode())
    assert "/" not in d.encode_refnr(refnr)


def test_extract_description_known_and_unknown_fields():
    assert d.extract_description({"stellenangebotsBeschreibung": "Python, SQL"}) == "Python, SQL"
    long_text = "Wir suchen " + "x" * 300
    assert d.extract_description({"titel": "kurz", "neuesFeld": long_text}) == long_text
    assert d.extract_description({"titel": "kurz"}) is None


def test_fetches_only_new_ids_and_marks_gone_postings(monkeypatch):
    write_listing(["A", "B", "C"])
    calls = []

    def fake_get(session, url, params=None, headers=None):
        calls.append(url)
        assert headers["X-API-Key"] == "jobboerse-jobsuche"
        if d.encode_refnr("C") in url or d.encode_refnr("C", True) in url:
            raise http_error(404)
        return {"stellenangebotsBeschreibung": f"text for {url}"}

    monkeypatch.setattr(d, "get_json", fake_get)
    assert cli.details() == 0
    recs = {e["payload"]["_id"]: e["payload"] for e in storage.iter_raw() if e["source"] == d.SOURCE}
    assert recs["A"]["_status"] == "ok" and recs["B"]["_status"] == "ok"
    assert recs["C"]["_status"] == "not_found"          # tried every endpoint variant, then gave up

    # Second run: nothing new -> no HTTP calls at all
    calls.clear()
    assert cli.details() == 0
    assert calls == []


def test_falls_back_to_v3(monkeypatch):
    write_listing(["A"])

    def fake_get(session, url, params=None, headers=None):
        if "/v4/" in url:
            raise http_error(404)
        return {"stellenangebotsBeschreibung": "from v3"}

    monkeypatch.setattr(d, "get_json", fake_get)
    rec = next(d.fetch(None))
    assert rec["_status"] == "ok" and rec["_endpoint"].endswith("/v3/jobdetails")


def test_limit_caps_requests(monkeypatch):
    write_listing([f"id{i}" for i in range(10)])
    monkeypatch.setattr(d, "get_json", lambda *a, **k: {"stellenangebotsBeschreibung": "t"})
    assert len(list(d.fetch(None, limit=3))) == 3


def test_expired_posting_v4_404_then_v3_403_is_not_found(monkeypatch):
    # Real case from 2026-11-26: v4 -> 404 (gone), v3 -> 403 "No match found" (route removed)
    write_listing(["OK1", "GONE", "OK2"])

    def fake_get(session, url, params=None, headers=None):
        if d.encode_refnr("GONE") in url or d.encode_refnr("GONE", True) in url:
            raise http_error(404 if "/v4/" in url else 403)
        return {"stellenangebotsBeschreibung": "t"}

    monkeypatch.setattr(d, "get_json", fake_get)
    assert cli.details() == 0
    recs = {e["payload"]["_id"]: e["payload"]["_status"] for e in storage.iter_raw() if e["source"] == d.SOURCE}
    assert recs == {"OK1": "ok", "GONE": "not_found", "OK2": "ok"}


def test_all_403_aborts_but_keeps_what_was_fetched(monkeypatch):
    # Key blocked / API moved mid-run: stop, fail the run, but save earlier results and mark nothing as gone
    write_listing(["A", "B", "C"])
    state = {"n": 0}

    def fake_get(session, url, params=None, headers=None):
        if d.encode_refnr("A") in url:
            return {"stellenangebotsBeschreibung": "t"}
        raise http_error(403)

    monkeypatch.setattr(d, "get_json", fake_get)
    assert cli.details() == 1
    recs = {e["payload"]["_id"]: e["payload"]["_status"] for e in storage.iter_raw() if e["source"] == d.SOURCE}
    assert recs == {"A": "ok"}                          # B, C untouched -> retried next run


def test_single_transient_error_is_skipped_and_retried(monkeypatch):
    write_listing(["A", "FLAKY", "B"])

    def fake_get(session, url, params=None, headers=None):
        if d.encode_refnr("FLAKY") in url:
            raise http_error(500)
        return {"stellenangebotsBeschreibung": "t"}

    monkeypatch.setattr(d, "get_json", fake_get)
    assert cli.details() == 0                           # one flaky posting doesn't fail the run
    recs = {e["payload"]["_id"] for e in storage.iter_raw() if e["source"] == d.SOURCE}
    assert recs == {"A", "B"}                           # FLAKY not stored -> fetched again tomorrow


def test_repeated_server_errors_fail_the_run(monkeypatch):
    write_listing([f"id{i}" for i in range(8)])

    def boom(*a, **k):
        raise http_error(500)

    monkeypatch.setattr(d, "get_json", boom)
    assert cli.details() == 1                           # red build -> email alert
    assert '"aborted": true' in config.RUN_LOG.read_text()


def test_ctrl_c_keeps_completed_batches(monkeypatch):
    # User pressed Ctrl+C during a long run (2026-11-26): earlier batches must survive
    write_listing([f"id{i:03d}" for i in range(40)])
    calls = {"n": 0}

    def fake_get(session, url, params=None, headers=None):
        calls["n"] += 1
        if calls["n"] == 30:
            raise KeyboardInterrupt
        return {"stellenangebotsBeschreibung": "t"}

    monkeypatch.setattr(d, "get_json", fake_get)
    assert cli.details() == 1
    saved = [e for e in storage.iter_raw() if e["source"] == d.SOURCE]
    assert len(saved) == 25                             # first batch of 25 kept, ids 25-28 refetched next run

    # next run picks up exactly the remaining 15
    monkeypatch.setattr(d, "get_json", lambda *a, **k: {"stellenangebotsBeschreibung": "t"})
    assert cli.details() == 0
    assert len({e["payload"]["_id"] for e in storage.iter_raw() if e["source"] == d.SOURCE}) == 40
