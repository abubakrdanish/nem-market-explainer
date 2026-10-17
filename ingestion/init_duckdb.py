"""Create the DuckDB warehouse with schemas raw, staging and marts, and the raw tables."""
from __future__ import annotations

import duckdb

from ingestion import aemo
from ingestion.config import WAREHOUSE_PATH

LINEAGE = "_source_file varchar not null, _loaded_at timestamptz not null"
RBA_COLUMNS = f"series_id varchar, title varchar, units varchar, obs_date date, value varchar, {LINEAGE}"

RAW_TABLES = {
    "rba_f11": RBA_COLUMNS,
    "rba_f1": RBA_COLUMNS,
    "rba_a2": RBA_COLUMNS,
    "events": (f"event_date date, time_sydney varchar, event_type varchar, title varchar, source_url varchar, "
               f"verified_on date, {LINEAGE}"),
    **{table.raw_table: aemo.table_ddl(table) for table in aemo.TABLES},
}


def init(con: duckdb.DuckDBPyConnection) -> None:
    for schema in ("raw", "staging", "marts"):
        con.execute(f"create schema if not exists {schema}")
    for table, columns in RAW_TABLES.items():
        con.execute(f"create table if not exists raw.{table} ({columns})")


def connect(path=WAREHOUSE_PATH) -> duckdb.DuckDBPyConnection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    init(con)
    return con


if __name__ == "__main__":
    connect().close()
    print(f"Initialised {WAREHOUSE_PATH}")
