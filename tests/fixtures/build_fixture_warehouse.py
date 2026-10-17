"""Load the committed fixtures into a new DuckDB file, so dbt can build without the real warehouse.

    python -m tests.fixtures.build_fixture_warehouse warehouse/fixture.duckdb

The fixtures cover one hour of 1 September 2026, so dbt tests that need whole days have nothing to check.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from ingestion import aemo
from ingestion.init_duckdb import connect
from ingestion.run import import_events, load_all
from tests.conftest import EVENTS_FILE, FIXTURES, RAW_LAYOUT, zip_fixture


def build(path: Path) -> None:
    if path.exists():
        raise SystemExit(f"{path} already exists; remove it first")
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw"
        for fixture, target in RAW_LAYOUT.items():
            (raw / target).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(FIXTURES / fixture, raw / target)
        for table in aemo.TABLES:
            zip_fixture(table, raw / "aemo")
        import_events(EVENTS_FILE, raw)
        with connect(path) as con:
            load_all(con, raw)


if __name__ == "__main__":
    build(Path(sys.argv[1]))
