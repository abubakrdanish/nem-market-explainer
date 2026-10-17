"""Shared fixtures. Network access is blocked so every test proves it runs offline."""
from __future__ import annotations

import shutil
import socket
import zipfile
from datetime import date
from pathlib import Path

import pytest

from ingestion import aemo
from ingestion.init_duckdb import connect

FIXTURES = Path(__file__).parent / "fixtures"
EVENTS_FILE = Path(__file__).parent.parent / "data" / "events.csv"

# Fixture file -> where the pipeline would have saved it under data/raw.
RAW_LAYOUT = {
    "synthetic_rba_f11_hist.xls": "rba/rba_f11_2014_2017_20261017.xls",
    "synthetic_rba_f11_1.csv": "rba/rba_f11_1_2023_current_20261017.csv",
    "rba_f1_sample.csv": "rba/rba_f1_20261017.csv",
    "rba_a2_sample.csv": "rba/rba_a2_20261017.csv",
}


def zip_fixture(table: aemo.AemoTable, directory: Path, saved: str = "20261017") -> Path:
    """Zip a synthetic AEMO CSV the way the archive ships it, named as the pipeline saves it."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{aemo.stem(table, date(2026, 9, 1), '01')}_{saved}.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.write(FIXTURES / f"synthetic_aemo_{table.name.lower()}.csv", f"PUBLIC_ARCHIVE#{table.name}.CSV")
    return path


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def guard(self, address):
        raise RuntimeError(f"Network access attempted during tests: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", guard)


@pytest.fixture
def raw_dir(tmp_path) -> Path:
    """A data/raw folder holding the RBA and AEMO fixtures as if they had been downloaded."""
    root = tmp_path / "raw"
    for fixture, target in RAW_LAYOUT.items():
        (root / target).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(FIXTURES / fixture, root / target)
    for table in aemo.TABLES:
        zip_fixture(table, root / "aemo")
    return root


@pytest.fixture
def con(tmp_path):
    with connect(tmp_path / "test.duckdb") as connection:
        yield connection
