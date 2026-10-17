"""Download RBA tables and the AEMO monthly archive, import events.csv, load everything into raw.

    python -m ingestion.run            # full run
    python -m ingestion.run --offline  # no downloads; load local files only
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

from ingestion import aemo
from ingestion.config import EVENTS_FILE, RAW_DATA_DIR, rba_tables, sources
from ingestion.contracts import ContractError, parse_events
from ingestion.http_client import PoliteClient
from ingestion.init_duckdb import connect
from ingestion.load_raw import load_files
from ingestion.raw_files import list_raw_files, save_raw
from ingestion.rba import parse_rba_table

log = logging.getLogger("ingestion")

# NEM market time is AEST all year; Brisbane has no daylight saving.
NEM_TIME = ZoneInfo("Australia/Brisbane")


def download_all(raw_dir: Path) -> None:
    settings = sources()
    client = PoliteClient(settings["user_agent"], settings["min_request_gap_seconds"])
    for table in rba_tables():
        save_raw(client.get(table.url), raw_dir / "rba", table.name, table.ext)
    aemo.download(client, settings["aemo"], raw_dir / "aemo", datetime.now(NEM_TIME).date())


def import_events(events_file: Path, raw_dir: Path) -> str | None:
    """Copy events.csv into raw if it meets the contract. Returns the contract error, if any."""
    try:
        parse_events(events_file)
    except ContractError as exc:
        return str(exc)
    save_raw(events_file.read_bytes(), raw_dir / "events", "events", "csv")
    return None


def load_all(con: duckdb.DuckDBPyConnection, raw_dir: Path) -> None:
    rba_files = defaultdict(list)
    for table in rba_tables():
        rba_files[table.table] += list_raw_files(raw_dir / "rba", table.name, table.ext)
    for table, paths in rba_files.items():
        load_files(con, table, paths, parse_rba_table)
    for table in aemo.TABLES:
        aemo.load(con, table, aemo.raw_files(raw_dir / "aemo", table))
    load_files(con, "events", list_raw_files(raw_dir / "events", "events", "csv"), parse_events)


def summary(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    queries = {t: f"select count(*), min(obs_date), max(obs_date) from raw.{t}" for t in ("rba_f11", "rba_f1", "rba_a2")}
    queries["events"] = "select count(*), min(event_date), max(event_date) from raw.events"
    for table in aemo.TABLES:
        span = "null, null" if table.standing else "min(settlementdate), max(settlementdate)"
        queries[table.raw_table] = f"select count(*), {span} from raw.{table.raw_table}"
    return [(table, *con.execute(sql).fetchone()) for table, sql in queries.items()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--offline", action="store_true", help="skip downloads")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not args.offline:
        download_all(RAW_DATA_DIR)
    error = import_events(EVENTS_FILE, RAW_DATA_DIR)
    with connect() as con:
        load_all(con, RAW_DATA_DIR)
        for table, rows, first, last in summary(con):
            span = f"  {first} to {last}" if first else ""
            log.info("raw.%-32s %12d rows%s", table, rows, span)
    if error:
        log.error("events.csv not imported: %s", error)
    return 1 if error else 0


if __name__ == "__main__":
    sys.exit(main())
