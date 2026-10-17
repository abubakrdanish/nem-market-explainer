import pandas as pd
import pytest

from ingestion import aemo
from ingestion.load_raw import load_files
from ingestion.run import import_events, load_all, summary
from tests.conftest import EVENTS_FILE


def counts(con) -> dict[str, int]:
    return {table: rows for table, rows, *_ in summary(con)}


def test_fixtures_load_into_every_raw_table(con, raw_dir):
    assert import_events(EVENTS_FILE, raw_dir) is None
    load_all(con, raw_dir)
    loaded = counts(con)
    assert loaded["rba_f11"] == 10
    assert loaded["rba_f1"] == 3
    assert loaded["rba_a2"] == 6
    assert loaded["events"] == len(pd.read_csv(EVENTS_FILE))
    assert loaded["aemo_dispatchprice"] == 60
    assert loaded["aemo_dispatchinterconnectorres"] == 72
    assert loaded["aemo_dispatch_unit_scada"] == 36
    assert loaded["aemo_market_price_thresholds"] == 1
    assert all(loaded[t.raw_table] > 0 for t in aemo.TABLES)


def test_loading_twice_adds_nothing(con, raw_dir):
    import_events(EVENTS_FILE, raw_dir)
    load_all(con, raw_dir)
    first = counts(con)
    import_events(EVENTS_FILE, raw_dir)
    load_all(con, raw_dir)
    assert counts(con) == first
    assert len(list((raw_dir / "events").iterdir())) == 1


def test_a_bad_events_file_is_reported_and_not_copied(tmp_path, raw_dir):
    bad = tmp_path / "events.csv"
    bad.write_text("event_date,title\n2026-10-16,Something\n")
    assert "missing" in import_events(bad, raw_dir)
    assert not (raw_dir / "events").exists()


def test_a_file_that_fails_to_insert_leaves_the_table_unchanged(con, tmp_path):
    path = tmp_path / "rba_f1_20261017.csv"
    path.write_text("unused")
    bad = pd.DataFrame({"series_id": ["X"], "obs_date": ["not a date"]})
    with pytest.raises(Exception):
        load_files(con, "rba_f1", [path], lambda p: bad)
    assert con.execute("select count(*) from raw.rba_f1").fetchone()[0] == 0
