"""Shared fixtures. Network access is blocked so every test proves it runs offline."""
from __future__ import annotations

import shutil
import socket
from pathlib import Path

import pytest

from ingestion.init_duckdb import connect

FIXTURES = Path(__file__).parent / "fixtures"
EVENTS_FILE = Path(__file__).parent.parent / "data" / "events.csv"

# Fixture file -> where the pipeline would have saved it under data/raw.
RAW_LAYOUT = {
    "rba_f11_hist_sample.xls": "rba/rba_f11_2014_2017_20261017.xls",
    "rba_f11_1_sample.csv": "rba/rba_f11_1_2023_current_20261017.csv",
    "rba_f1_sample.csv": "rba/rba_f1_20261017.csv",
    "rba_a2_sample.csv": "rba/rba_a2_20261017.csv",
}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def guard(self, address):
        raise RuntimeError(f"Network access attempted during tests: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", guard)


@pytest.fixture
def raw_dir(tmp_path) -> Path:
    """A data/raw folder holding the RBA fixtures as if they had been downloaded."""
    root = tmp_path / "raw"
    for fixture, target in RAW_LAYOUT.items():
        (root / target).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(FIXTURES / fixture, root / target)
    return root


@pytest.fixture
def inbox(tmp_path) -> Path:
    folder = tmp_path / "inbox"
    folder.mkdir()
    shutil.copy(FIXTURES / "FAKE_synthetic_prices.csv", folder)
    return folder


@pytest.fixture
def con(tmp_path):
    with connect(tmp_path / "test.duckdb") as connection:
        yield connection
