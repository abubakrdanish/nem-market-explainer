"""Load raw files into DuckDB raw tables, one transaction per file.

Every file is a snapshot. Rows keep `_source_file` and `_loaded_at`, and a file
already present in its table is skipped, so re-running adds nothing.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import duckdb
import pandas as pd

log = logging.getLogger(__name__)


def write(con: duckdb.DuckDBPyConnection, table: str, frame: pd.DataFrame, replace: bool = False) -> None:
    """Insert a frame by column name in one transaction, optionally replacing the table's rows."""
    con.begin()
    try:
        if replace:
            con.execute(f"delete from raw.{table}")
        con.register("incoming", frame)
        con.execute(f"insert into raw.{table} by name select * from incoming")
        con.unregister("incoming")
        con.commit()
    except Exception:
        con.rollback()
        raise


def loaded_files(con: duckdb.DuckDBPyConnection, table: str) -> set[str]:
    return {r[0] for r in con.execute(f"select distinct _source_file from raw.{table}").fetchall()}


def load_files(con: duckdb.DuckDBPyConnection, table: str, paths: list[Path],
               parse: Callable[[Path], pd.DataFrame]) -> int:
    """Load each file not yet in `raw.<table>`. Returns how many files were loaded."""
    already = loaded_files(con, table)
    loaded_at = datetime.now(timezone.utc)
    new = [p for p in paths if p.name not in already]
    for path in new:
        frame = parse(path).assign(_source_file=path.name, _loaded_at=loaded_at)
        write(con, table, frame)
        log.info("Loaded %s into raw.%s (%d rows)", path.name, table, len(frame))
    return len(new)
