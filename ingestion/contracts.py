"""Column contract for the hand-edited events.csv."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

EVENT_COLUMNS = ["event_date", "time_sydney", "event_type", "title", "source_url", "verified_on"]
MAX_REPORTED = 5


class ContractError(ValueError):
    pass


def _read(path: Path, columns: list[str]) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    frame.columns = [c.strip().lower() for c in frame.columns]
    missing = [c for c in columns if c not in frame.columns]
    extra = [c for c in frame.columns if c not in columns]
    if missing or extra:
        raise ContractError(f"{path.name}: expected columns {columns}; missing {missing}, unexpected {extra}")
    return frame[columns].apply(lambda col: col.str.strip())


def _raise_if_bad(path: Path, frame: pd.DataFrame, bad: pd.Series, problem: str) -> None:
    if bad.any():
        lines = [str(i + 2) for i in frame.index[bad][:MAX_REPORTED]]  # +2: header line, 1-based
        raise ContractError(f"{path.name}: {problem} on line(s) {', '.join(lines)} ({int(bad.sum())} rows)")


def _dates(path: Path, frame: pd.DataFrame, column: str, required: bool) -> list:
    parsed = pd.to_datetime(frame[column], format="%Y-%m-%d", errors="coerce")
    bad = parsed.isna() if required else parsed.isna() & (frame[column] != "")
    _raise_if_bad(path, frame, bad, f"{column} is not YYYY-MM-DD")
    return [d.date() if pd.notna(d) else None for d in parsed]


def parse_events(path: Path) -> pd.DataFrame:
    """verified_on is the date someone checked event_date against source_url; empty means unchecked."""
    frame = _read(path, EVENT_COLUMNS)
    frame["event_date"] = _dates(path, frame, "event_date", required=True)
    frame["verified_on"] = _dates(path, frame, "verified_on", required=False)
    bad_time = (frame["time_sydney"] != "") & ~frame["time_sydney"].str.fullmatch(r"\d\d:\d\d")
    _raise_if_bad(path, frame, bad_time, "time_sydney is not HH:MM")
    _raise_if_bad(path, frame, ~frame["event_type"].str.fullmatch(r"[a-z_]+"),
                  "event_type is not a lowercase word such as rba_decision")
    _raise_if_bad(path, frame, frame["title"] == "", "title is empty")
    return frame.replace({"time_sydney": {"": None}, "source_url": {"": None}})
