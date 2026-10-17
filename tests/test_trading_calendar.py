import csv
from datetime import date

from ingestion.trading_calendar import load_sessions, sessions
from tests.conftest import FIXTURES


def test_xasx_matches_the_calendar_asx_publishes():
    """Cross-check against the ASX 2026-27 trading calendar, transcribed on 2026-10-17."""
    calendar = sessions("2026-01-01", date(2027, 12, 31)).set_index("session_date")["close_time_sydney"]
    with (FIXTURES / "asx_published_calendar_2026_2027.csv").open() as f:
        for row in csv.DictReader(f):
            day = date.fromisoformat(row["date"])
            if row["status"] == "closed":
                assert day not in calendar.index, f"{day} should be closed"
            else:
                assert calendar[day] == row["close_time_sydney"], f"{day} closing time"


def test_sessions_are_weekdays_and_reload_replaces_rows(con):
    assert load_sessions(con, "2026-01-01", date(2026, 12, 31)) == load_sessions(con, "2026-01-01", date(2026, 12, 31))
    weekend = con.execute("select count(*) from raw.asx_sessions where isodow(session_date) > 5").fetchone()[0]
    total = con.execute("select count(*) from raw.asx_sessions").fetchone()[0]
    assert weekend == 0 and 245 <= total <= 256
