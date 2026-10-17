"""Parse RBA statistical tables (CSV or legacy .xls) into long rows: one per series per date.

Both formats share one layout: a header block (Title, Description, ..., Units,
Source, Publication date, Series ID) followed by rows of `dd-Mon-yyyy, value, ...`.
"""
from __future__ import annotations

import csv
import math
from datetime import datetime
from pathlib import Path

import pandas as pd

COLUMNS = ["series_id", "title", "units", "obs_date", "value"]


def _cell(value) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d-%b-%Y")
    return str(value).strip()


def _read_rows(path: Path) -> list[list[str]]:
    if path.suffix == ".xls":
        frame = pd.read_excel(path, header=None, engine="xlrd", dtype=object)
        return [[_cell(v) for v in row] for row in frame.itertuples(index=False)]
    with path.open(encoding="utf-8-sig", newline="") as f:
        return [[c.strip() for c in row] for row in csv.reader(f)]


def parse_rba_table(path: Path) -> pd.DataFrame:
    """Values stay as published text, because A2 has entries like '17.00 to 17.50'."""
    rows = _read_rows(path)
    id_rows = [i for i, row in enumerate(rows) if row and row[0] == "Series ID"]
    if not id_rows:
        raise ValueError(f"{path.name}: no 'Series ID' row, so this is not an RBA statistical table")
    start = id_rows[0] + 1
    header = {row[0]: row[1:] for row in rows[:start] if row and row[0]}
    series = list(zip(header["Series ID"], header["Title"], header["Units"]))

    records = []
    # Files are padded with blank rows, and a series with no observation that day has an empty cell.
    for row in rows[start:]:
        if not row or not row[0]:
            continue
        obs_date = datetime.strptime(row[0], "%d-%b-%Y").date()
        for (series_id, title, units), value in zip(series, row[1:]):
            if value:
                records.append((series_id, title, units, obs_date, value))
    return pd.DataFrame(records, columns=COLUMNS)
