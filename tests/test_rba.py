from datetime import date

import pytest

from ingestion.rba import parse_rba_table
from tests.conftest import FIXTURES


def test_csv_becomes_long_rows_and_skips_empty_cells():
    frame = parse_rba_table(FIXTURES / "synthetic_rba_f11_1.csv")
    assert list(frame.columns) == ["series_id", "title", "units", "obs_date", "value"]
    assert len(frame) == 5  # 3 dates x 2 series, minus one empty TWI cell
    first = frame.iloc[0]
    assert (first.series_id, first.units, first.obs_date, first.value) == ("FXRUSD", "USD", date(2026, 10, 1), "0.1111")


def test_legacy_xls_has_the_same_shape():
    frame = parse_rba_table(FIXTURES / "synthetic_rba_f11_hist.xls")
    assert set(frame.series_id) == {"FXRUSD", "FXRTWI"}
    assert frame.obs_date.max() == date(2017, 12, 29)
    assert frame[frame.series_id == "FXRUSD"].value.tolist() == ["0.1111", "0.2222", "0.3333"]


def test_a2_ranges_are_kept_as_text():
    frame = parse_rba_table(FIXTURES / "rba_a2_sample.csv")
    assert "17.00 to 17.50" in frame.value.tolist()


def test_a_non_rba_file_is_rejected(tmp_path):
    page = tmp_path / "error.csv"
    page.write_text("<html>Service unavailable</html>\n")
    with pytest.raises(ValueError, match="not an RBA statistical table"):
        parse_rba_table(page)
