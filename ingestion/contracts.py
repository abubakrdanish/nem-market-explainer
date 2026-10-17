"""Column contracts for the files people supply by hand: inbox price files and events.csv."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

PRICE_COLUMNS = ["ticker", "date", "open", "high", "low", "close", "adj_close", "volume"]
EVENT_COLUMNS = ["event_date", "time_sydney", "event_type", "title", "source_url"]
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


def _dates(path: Path, frame: pd.DataFrame, column: str) -> pd.Series:
    parsed = pd.to_datetime(frame[column], format="%Y-%m-%d", errors="coerce")
    _raise_if_bad(path, frame, parsed.isna(), f"{column} is not YYYY-MM-DD")
    return parsed.dt.date


def _numbers(path: Path, frame: pd.DataFrame, column: str, required: bool) -> pd.Series:
    parsed = pd.to_numeric(frame[column], errors="coerce")
    unparseable = parsed.isna() & (frame[column] != "")
    _raise_if_bad(path, frame, unparseable, f"{column} is not a number")
    if required:
        _raise_if_bad(path, frame, parsed.isna(), f"{column} is empty")
    return parsed


def parse_prices(path: Path) -> pd.DataFrame:
    """Check an inbox price file against the contract and return typed rows.

    Only structure is checked here. Content problems such as high below low are
    loaded as-is and reported by the quality checks.
    """
    frame = _read(path, PRICE_COLUMNS)
    frame["ticker"] = frame["ticker"].str.upper()
    _raise_if_bad(path, frame, ~frame["ticker"].str.fullmatch(r"[A-Z0-9]{1,6}"),
                  "ticker is not a plain ASX code such as BHP")
    out = pd.DataFrame({"ticker": frame["ticker"], "date": _dates(path, frame, "date")})
    for column in ["open", "high", "low", "adj_close"]:
        out[column] = _numbers(path, frame, column, required=False)
    out["close"] = _numbers(path, frame, "close", required=True)
    volume = _numbers(path, frame, "volume", required=False)
    _raise_if_bad(path, frame, volume.notna() & (volume % 1 != 0), "volume is not a whole number")
    out["volume"] = volume.astype("Int64")
    return out[PRICE_COLUMNS]


def parse_events(path: Path) -> pd.DataFrame:
    frame = _read(path, EVENT_COLUMNS)
    frame["event_date"] = _dates(path, frame, "event_date")
    bad_time = (frame["time_sydney"] != "") & ~frame["time_sydney"].str.fullmatch(r"\d\d:\d\d")
    _raise_if_bad(path, frame, bad_time, "time_sydney is not HH:MM")
    _raise_if_bad(path, frame, ~frame["event_type"].str.fullmatch(r"[a-z_]+"),
                  "event_type is not a lowercase word such as rba_decision")
    _raise_if_bad(path, frame, frame["title"] == "", "title is empty")
    return frame.replace({"time_sydney": {"": None}, "source_url": {"": None}})


def inbox_stem(path: Path) -> str:
    """'BHP prices.csv' -> 'bhp_prices', used to name the raw copy."""
    return re.sub(r"[^a-z0-9]+", "_", path.stem.lower()).strip("_")
