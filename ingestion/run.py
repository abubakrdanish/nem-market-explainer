"""Download RBA tables, import inbox prices and events.csv, load everything into raw, refresh sessions.

    python -m ingestion.run            # full run
    python -m ingestion.run --offline  # no downloads; import and load local files only
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import duckdb

from ingestion.config import EVENTS_FILE, INBOX_DIR, RAW_DATA_DIR, rba_tables, sources
from ingestion.contracts import ContractError, inbox_stem, parse_events, parse_prices
from ingestion.http_client import PoliteClient
from ingestion.init_duckdb import connect
from ingestion.load_raw import load_files
from ingestion.raw_files import list_raw_files, save_raw
from ingestion.rba import parse_rba_table
from ingestion.trading_calendar import load_sessions

log = logging.getLogger("ingestion")


def download_rba(raw_dir: Path) -> None:
    settings = sources()
    client = PoliteClient(settings["user_agent"], settings["min_request_gap_seconds"])
    for table in rba_tables():
        save_raw(client.get(table.url), raw_dir / "rba", table.name, table.ext)


def import_local_files(inbox: Path, events_file: Path, raw_dir: Path) -> list[str]:
    """Copy valid inbox files and events.csv into raw. Returns contract errors; bad files are not copied."""
    candidates = [(p, parse_prices, raw_dir / "prices", inbox_stem(p)) for p in sorted(inbox.glob("*.csv"))]
    candidates.append((events_file, parse_events, raw_dir / "events", "events"))
    errors = []
    for path, parse, directory, stem in candidates:
        try:
            parse(path)
        except ContractError as exc:
            errors.append(str(exc))
            continue
        save_raw(path.read_bytes(), directory, stem, "csv")
    return errors


def load_all(con: duckdb.DuckDBPyConnection, raw_dir: Path) -> None:
    rba_files = defaultdict(list)
    for table in rba_tables():
        rba_files[table.table] += list_raw_files(raw_dir / "rba", table.name, table.ext)
    for table, paths in rba_files.items():
        load_files(con, table, paths, parse_rba_table)
    load_files(con, "prices", sorted((raw_dir / "prices").glob("*.csv")), parse_prices)
    load_files(con, "events", list_raw_files(raw_dir / "events", "events", "csv"), parse_events)


def summary(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    queries = {
        "prices": "select count(*), min(date), max(date), count(distinct ticker) from raw.prices",
        "rba_f11": "select count(*), min(obs_date), max(obs_date), count(distinct series_id) from raw.rba_f11",
        "rba_f1": "select count(*), min(obs_date), max(obs_date), count(distinct series_id) from raw.rba_f1",
        "rba_a2": "select count(*), min(obs_date), max(obs_date), count(distinct series_id) from raw.rba_a2",
        "events": "select count(*), min(event_date), max(event_date), count(distinct event_type) from raw.events",
        "asx_sessions": "select count(*), min(session_date), max(session_date), null from raw.asx_sessions",
    }
    return [(table, *con.execute(sql).fetchone()) for table, sql in queries.items()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--offline", action="store_true", help="skip downloads")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not args.offline:
        download_rba(RAW_DATA_DIR)
    errors = import_local_files(INBOX_DIR, EVENTS_FILE, RAW_DATA_DIR)
    with connect() as con:
        load_all(con, RAW_DATA_DIR)
        load_sessions(con, sources()["calendar"]["start"], date(date.today().year + 1, 12, 31))
        for table, rows, first, last, keys in summary(con):
            log.info("raw.%-13s %8d rows  %s to %s  %s", table, rows, first, last, "" if keys is None else f"{keys} keys")
    for error in errors:
        log.error("Not imported: %s", error)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
