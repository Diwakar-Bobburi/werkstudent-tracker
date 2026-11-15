"""Shared HTTP session with retries and a polite delay."""
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from tracker import config


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=2,  # 2s, 4s, 8s, 16s
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=True,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": config.USER_AGENT, "Accept": "application/json"})
    return session


def get_json(session: requests.Session, url: str, *, params=None, headers=None) -> dict:
    resp = session.get(url, params=params, headers=headers, timeout=config.REQUEST_TIMEOUT)
    resp.raise_for_status()
    time.sleep(config.REQUEST_DELAY_SECONDS)
    return resp.json()
