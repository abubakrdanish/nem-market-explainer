"""Shared fixtures. Network access is blocked so every test proves it runs offline."""
from __future__ import annotations

import os
import shutil
import socket
import zipfile
from datetime import date
from pathlib import Path

import duckdb
import pytest

from ingestion import aemo
from ingestion.init_duckdb import connect

FIXTURES = Path(__file__).parent / "fixtures"
EVENTS_FILE = Path(__file__).parent.parent / "data" / "events.csv"
DBT_PROJECT = Path(__file__).parent.parent / "dbt_project"

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


@pytest.fixture(scope="session")
def fixture_marts(tmp_path_factory) -> Path:
    """The fixtures loaded into raw and built into marts by dbt, once per test session."""
    from dbt.cli.main import dbtRunner

    from tests.fixtures.build_fixture_warehouse import build

    work = tmp_path_factory.mktemp("marts")
    warehouse = work / "fixture.duckdb"
    build(warehouse)
    profiles = work / "profiles"
    profiles.mkdir()
    shutil.copy(DBT_PROJECT / "profiles.yml.example", profiles / "profiles.yml")
    old = os.environ.get("NEM_FIXTURE_WAREHOUSE")
    os.environ["NEM_FIXTURE_WAREHOUSE"] = str(warehouse)
    try:
        result = dbtRunner().invoke(["build", "--quiet", "--project-dir", str(DBT_PROJECT), "--profiles-dir", str(profiles),
                                     "--target", "fixture", "--target-path", str(work / "target"),
                                     "--log-path", str(work / "logs")])
    finally:
        if old is None:
            os.environ.pop("NEM_FIXTURE_WAREHOUSE")
        else:
            os.environ["NEM_FIXTURE_WAREHOUSE"] = old
    assert result.success, result.exception
    # dbt-duckdb keeps its connection open in this process, and DuckDB refuses a second, read-only one to the
    # same file, so tests read a copy. The models are still in the write-ahead log, so it is copied too and
    # checkpointed into the copy.
    copy = work / "explainer_fixture.duckdb"
    shutil.copy(warehouse, copy)
    if warehouse.with_suffix(".duckdb.wal").exists():
        shutil.copy(warehouse.with_suffix(".duckdb.wal"), copy.with_suffix(".duckdb.wal"))
    duckdb.connect(str(copy)).execute("checkpoint").close()
    return copy


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
