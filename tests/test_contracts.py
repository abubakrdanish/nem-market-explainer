import pandas as pd
import pytest

from ingestion.config import expected_tickers
from ingestion.contracts import ContractError, inbox_stem, parse_events, parse_prices
from tests.conftest import EVENTS_FILE, FIXTURES

HEADER = "ticker,date,open,high,low,close,adj_close,volume\n"


def write(tmp_path, body: str, header: str = HEADER):
    path = tmp_path / "prices.csv"
    path.write_text(header + body)
    return path


def test_fake_sample_meets_the_contract():
    frame = parse_prices(FIXTURES / "FAKE_synthetic_prices.csv")
    assert set(frame.ticker) == set(expected_tickers())
    assert frame["volume"].dtype == "Int64"
    index_rows = frame[frame.ticker == "XJO"]
    assert index_rows.adj_close.isna().all() and index_rows.volume.isna().all()


def test_columns_may_come_in_any_order_and_case(tmp_path):
    path = write(tmp_path, "10,2026-10-16,bhp,,,,,\n", header="Close,Date,Ticker,open,high,low,adj_close,volume\n")
    frame = parse_prices(path)
    assert frame.iloc[0].ticker == "BHP" and frame.iloc[0].close == 10


@pytest.mark.parametrize("body, message", [
    ("BHP,16/10/2026,1,1,1,1,1,1\n", "date is not YYYY-MM-DD on line\\(s\\) 2"),
    ("BHP,2026-10-16,1,1,1,,1,1\n", "close is empty"),
    ("BHP,2026-10-16,1,1,1,abc,1,1\n", "close is not a number"),
    ("BHP,2026-10-16,1,1,1,1,1,1.5\n", "volume is not a whole number"),
    ("BHP.AX,2026-10-16,1,1,1,1,1,1\n", "ticker is not a plain ASX code"),
])
def test_bad_rows_are_reported_with_line_numbers(tmp_path, body, message):
    with pytest.raises(ContractError, match=message):
        parse_prices(write(tmp_path, body))


def test_missing_and_extra_columns_are_named(tmp_path):
    path = write(tmp_path, "BHP,2026-10-16,1\n", header="ticker,date,price\n")
    with pytest.raises(ContractError, match=r"missing \['open'.*unexpected \['price'\]"):
        parse_prices(path)


def test_committed_events_file_meets_the_contract():
    frame = parse_events(EVENTS_FILE)
    assert frame.event_date.min() >= pd.Timestamp("2024-01-01").date()
    assert {"rba_decision", "abs_release"} <= set(frame.event_type)


def test_inbox_stem_is_safe_for_file_names():
    assert inbox_stem(FIXTURES / "BHP prices (2016-2026).csv") == "bhp_prices_2016_2026"
