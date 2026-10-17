import pandas as pd
import pytest

from ingestion.contracts import ContractError, parse_events
from tests.conftest import EVENTS_FILE


def test_committed_events_file_meets_the_contract():
    frame = parse_events(EVENTS_FILE)
    assert frame.event_date.min() >= pd.Timestamp("2021-07-01").date()
    assert {"rba_decision", "abs_release", "nem_market", "generator_closure"} <= set(frame.event_type)


def test_events_say_which_dates_were_checked():
    frame = parse_events(EVENTS_FILE)
    unchecked = frame[frame.verified_on.isna()]
    assert sorted(unchecked.event_type.value_counts().items()) == [("abs_release", 15), ("nem_market", 1)]


def test_a_bad_verified_on_is_rejected(tmp_path):
    path = tmp_path / "events.csv"
    path.write_text("event_date,time_sydney,event_type,title,source_url,verified_on\n"
                    "2026-09-29,14:30,rba_decision,RBA decision,,17/10/2026\n")
    with pytest.raises(ContractError, match="verified_on is not YYYY-MM-DD"):
        parse_events(path)
