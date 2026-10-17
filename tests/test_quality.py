from datetime import date, datetime, timezone

import pytest

from ingestion.config import expected_tickers
from ingestion.quality import run_checks
from ingestion.run import import_local_files, load_all
from ingestion.trading_calendar import load_sessions
from tests.conftest import EVENTS_FILE

TODAY = date(2026, 10, 17)


@pytest.fixture
def loaded(con, raw_dir, inbox):
    import_local_files(inbox, EVENTS_FILE, raw_dir)
    load_all(con, raw_dir)
    load_sessions(con, "2016-01-01", date(2027, 12, 31))
    return con


def results(con, today=TODAY) -> dict[str, tuple[str, str]]:
    return {c.name: (c.status, c.detail) for c in run_checks(con, expected_tickers(), today, max_age=5)}


def add_price(con, ticker="BHP", day="2026-10-16", high=11.0, low=10.0, close=10.5, source="extra_20261017.csv"):
    con.execute("insert into raw.prices values (?, ?, ?, ?, ?, ?, null, null, ?, ?)",
                [ticker, day, close, high, low, close, source, datetime.now(timezone.utc)])


def test_fixture_data_passes_every_check(loaded):
    statuses = {name: status for name, (status, _) in results(loaded).items()}
    assert statuses == {name: "pass" for name in statuses}


@pytest.mark.parametrize("bad_row, failing_check", [
    ({"close": 0.0}, "positive_prices"),
    ({"high": 9.0, "low": 10.0}, "high_not_below_low"),
    ({"day": "2026-10-11"}, "trading_days"),  # a Sunday
    ({"day": "2026-10-19"}, "no_future_dates"),
])
def test_bad_rows_fail_their_check(loaded, bad_row, failing_check):
    add_price(loaded, **bad_row)
    assert results(loaded)[failing_check][0] == "fail"


def test_duplicate_ticker_date_in_one_file_fails(loaded):
    add_price(loaded)
    add_price(loaded)
    assert results(loaded)["unique_ticker_date"][0] == "fail"


def test_missing_ticker_is_named(loaded):
    loaded.execute("delete from raw.prices where ticker = 'CSL'")
    status, detail = results(loaded)["expected_tickers"]
    assert status == "fail" and "CSL" in detail


def test_a_smaller_newer_snapshot_fails(loaded):
    first = loaded.execute("select distinct _source_file from raw.prices").fetchone()[0]
    stem = first.rsplit("_", 1)[0]
    loaded.execute(f"insert into raw.prices select * replace ('{stem}_20991231.csv' as _source_file) "
                   f"from raw.prices where ticker = 'BHP'")
    assert results(loaded)["snapshots_do_not_shrink"][0] == "fail"


def test_freshness_reports_age_and_warns_when_stale(loaded):
    status, detail = results(loaded)["freshness_prices"]
    assert status == "pass" and detail == "newest price 2026-10-16, 0 sessions and 1 days old"
    status, detail = results(loaded, today=date(2026, 11, 2))["freshness_prices"]
    assert status == "warn" and "11 sessions" in detail


def test_an_empty_rba_table_fails_freshness(loaded):
    loaded.execute("delete from raw.rba_a2")
    status, detail = results(loaded)["freshness_rba"]
    assert status == "fail" and "rba_a2 None" in detail


def test_a_ticker_that_stops_early_is_flagged(loaded):
    loaded.execute("delete from raw.prices where ticker = 'WDS' and date > '2026-09-25'")
    status, detail = results(loaded)["coverage"]
    assert status == "warn" and detail.startswith("WDS: ends 2026-09-25")
