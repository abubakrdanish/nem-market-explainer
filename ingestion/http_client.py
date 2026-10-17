"""HTTP GET with timeouts, retries with backoff on 429/5xx, and a minimum gap between requests."""
from __future__ import annotations

import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TIMEOUT = (10, 120)  # connect, read seconds


class PoliteClient:
    def __init__(self, user_agent: str, min_gap_seconds: float, retries: int = 5):
        # backoff_factor=2 waits about 2, 4, 8, 16 s between attempts, or Retry-After when sent.
        retry = Retry(total=retries, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods={"GET"}, respect_retry_after_header=True)
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.min_gap_seconds = min_gap_seconds
        self._last_request = 0.0

    def get(self, url: str) -> bytes:
        wait = self._last_request + self.min_gap_seconds - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            response = self.session.get(url, timeout=TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Download failed for {url}: {exc}") from exc
        finally:
            self._last_request = time.monotonic()
        return response.content
