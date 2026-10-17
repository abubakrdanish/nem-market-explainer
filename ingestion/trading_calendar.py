"""ASX trading sessions from the exchange_calendars XASX calendar."""
from __future__ import annotations

from datetime import date, datetime, timezone
from importlib.metadata import version

import duckdb
import exchange_calendars as xc
import pandas as pd

from ingestion.load_raw import write


def sessions(start: str, end: date) -> pd.DataFrame:
    """One row per trading day with the Sydney closing time (14:10 on early-close days)."""
    calendar = xc.get_calendar("XASX", start=start, end=end.isoformat())
    closes = calendar.schedule["close"].dt.tz_convert("Australia/Sydney")
    return pd.DataFrame({
        "session_date": calendar.sessions.date,
        "close_time_sydney": closes.dt.strftime("%H:%M").to_numpy(),
    })


def load_sessions(con: duckdb.DuckDBPyConnection, start: str, end: date) -> int:
    """Replace raw.asx_sessions. It is derived from a library, not a downloaded file."""
    frame = sessions(start, end).assign(
        _source=f"exchange_calendars {version('exchange_calendars')}",
        _loaded_at=datetime.now(timezone.utc),
    )
    write(con, "asx_sessions", frame, replace=True)
    return len(frame)
