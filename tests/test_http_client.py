import pytest
import requests

from ingestion.http_client import PoliteClient


class FakeResponse:
    def __init__(self, status: int, content: bytes = b"ok"):
        self.status_code, self.content = status, content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


def test_requests_are_spaced_out(monkeypatch):
    client = PoliteClient("test-agent", min_gap_seconds=5)
    monkeypatch.setattr(client.session, "get", lambda url, timeout: FakeResponse(200))
    clock = iter([100.0, 100.0, 101.0, 106.0])
    monkeypatch.setattr("ingestion.http_client.time.monotonic", lambda: next(clock))
    slept = []
    monkeypatch.setattr("ingestion.http_client.time.sleep", slept.append)

    client.get("https://example.org/a")
    client.get("https://example.org/b")
    assert slept == [4.0]


def test_errors_name_the_url(monkeypatch):
    client = PoliteClient("test-agent", min_gap_seconds=0)
    monkeypatch.setattr(client.session, "get", lambda url, timeout: FakeResponse(404))
    with pytest.raises(RuntimeError, match="https://example.org/missing"):
        client.get("https://example.org/missing")


def test_retries_cover_rate_limits_and_server_errors():
    retry = PoliteClient("test-agent", min_gap_seconds=0).session.get_adapter("https://x").max_retries
    assert {429, 500, 502, 503, 504} <= set(retry.status_forcelist)
    assert retry.respect_retry_after_header
