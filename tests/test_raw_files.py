from datetime import datetime, timezone

from ingestion.raw_files import list_raw_files, save_raw

NOW = datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc)


def test_identical_bytes_are_not_saved_twice(tmp_path):
    first = save_raw(b"a,b\n1,2\n", tmp_path, "rba_f1", "csv", now=NOW)
    assert first.name == "rba_f1_20261017.csv"
    assert save_raw(b"a,b\n1,2\n", tmp_path, "rba_f1", "csv", now=NOW) is None
    assert list_raw_files(tmp_path, "rba_f1", "csv") == [first]


def test_changed_content_on_the_same_day_gets_a_time_suffix(tmp_path):
    save_raw(b"v1", tmp_path, "rba_f1", "csv", now=NOW)
    second = save_raw(b"v2", tmp_path, "rba_f1", "csv", now=NOW)
    assert second.name == "rba_f1_20261017T090000.csv"
    assert second.read_bytes() == b"v2"


def test_listing_matches_the_exact_dataset_stem(tmp_path):
    save_raw(b"x", tmp_path, "rba_f1", "csv", now=NOW)
    save_raw(b"y", tmp_path, "rba_f11_1_2023_current", "csv", now=NOW)
    save_raw(b"z", tmp_path, "rba_f1_extra", "csv", now=NOW)
    assert [p.name for p in list_raw_files(tmp_path, "rba_f1", "csv")] == ["rba_f1_20261017.csv"]
