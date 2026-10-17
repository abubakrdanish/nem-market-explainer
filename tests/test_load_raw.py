import duckdb
import pandas as pd
import pytest

from ingestion.init_duckdb import init
from ingestion.load_raw import load_files
from ingestion.run import import_local_files, load_all, summary
from tests.conftest import EVENTS_FILE


def counts(con) -> dict[str, int]:
    return {table: rows for table, rows, *_ in summary(con)}


def test_fixtures_load_into_every_raw_table(con, raw_dir, inbox):
    assert import_local_files(inbox, EVENTS_FILE, raw_dir) == []
    load_all(con, raw_dir)
    loaded = counts(con)
    assert loaded["prices"] == 620
    assert loaded["rba_f11"] == 10
    assert loaded["rba_f1"] == 3
    assert loaded["rba_a2"] == 6
    assert loaded["events"] == len(pd.read_csv(EVENTS_FILE))
    files = con.execute("select distinct _source_file from raw.prices").fetchall()
    assert len(files) == 1 and files[0][0].startswith("fake_synthetic_prices_")


def test_loading_twice_adds_nothing(con, raw_dir, inbox):
    import_local_files(inbox, EVENTS_FILE, raw_dir)
    load_all(con, raw_dir)
    first = counts(con)
    import_local_files(inbox, EVENTS_FILE, raw_dir)
    load_all(con, raw_dir)
    assert counts(con) == first
    assert len(list((raw_dir / "prices").iterdir())) == 1


def test_a_bad_inbox_file_is_reported_and_not_copied(raw_dir, inbox):
    (inbox / "broken.csv").write_text("ticker,date\nBHP,2026-10-16\n")
    errors = import_local_files(inbox, EVENTS_FILE, raw_dir)
    assert len(errors) == 1 and "broken.csv" in errors[0]
    assert [p.name.startswith("fake_synthetic_prices_") for p in (raw_dir / "prices").iterdir()] == [True]


def test_a_file_that_fails_to_insert_leaves_the_table_unchanged(con, tmp_path):
    path = tmp_path / "rba_f1_20261017.csv"
    path.write_text("unused")
    bad = pd.DataFrame({"series_id": ["X"], "obs_date": ["not a date"]})
    with pytest.raises(Exception):
        load_files(con, "rba_f1", [path], lambda p: bad)
    assert con.execute("select count(*) from raw.rba_f1").fetchone()[0] == 0


def test_an_older_warehouse_gains_the_verified_on_column(tmp_path):
    with duckdb.connect(str(tmp_path / "old.duckdb")) as old:
        old.execute("create schema raw")
        old.execute("create table raw.events (event_date date, time_sydney varchar, event_type varchar, title varchar, "
                    "source_url varchar, _source_file varchar not null, _loaded_at timestamptz not null)")
        init(old)
        assert "verified_on" in [r[0] for r in old.execute("describe raw.events").fetchall()]
