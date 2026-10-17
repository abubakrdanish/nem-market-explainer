import zipfile
from datetime import date, datetime

import duckdb
import pytest

from ingestion import aemo
from ingestion.config import WAREHOUSE_PATH
from tests.conftest import FIXTURES, zip_fixture

TABLES = {t.name: t for t in aemo.TABLES}
DATA = "/Data_Archive/Wholesale_Electricity/MMSDM/2024/MMSDM_2024_08/MMSDM_Historical_Data_SQLLoader/DATA/"
LISTING = f"""
<A HREF="{DATA}PUBLIC_DVD_DISPATCHPRICE_202407010000.zip">x</A>
<A HREF="{DATA}PUBLIC_DVD_PREDISPATCHPRICE_D_202407010000.zip">x</A>
<A HREF="{DATA}PUBLIC_ARCHIVE%23DISPATCH_UNIT_SCADA%23FILE02%23202408010000.zip">x</A>
<A HREF="{DATA}PUBLIC_ARCHIVE%23DISPATCH_UNIT_SCADA%23FILE01%23202408010000.zip">x</A>
<A HREF="{DATA}PUBLIC_ARCHIVE%23INTERMITTENT_GEN_SCADA%23FILE01%23202408010000.zip">x</A>
"""


def test_both_archive_naming_schemes_are_found():
    assert [part for _, part in aemo.table_links(LISTING, "DISPATCHPRICE")] == ["01"]
    scada = aemo.table_links(LISTING, "DISPATCH_UNIT_SCADA")
    assert [part for _, part in scada] == ["01", "02"]
    assert scada[0][0].endswith("PUBLIC_ARCHIVE%23DISPATCH_UNIT_SCADA%23FILE01%23202408010000.zip")
    assert aemo.table_links(LISTING, "PREDISPATCHPRICE") == []


def test_published_months_come_from_the_year_listing():
    listing = '<A HREF="/x/2026/MMSDM_2026_08/">MMSDM_2026_08</A> <A HREF="/x/2026/MMSDM_2026_09/">x</A>'
    assert aemo.published_months(listing) == [date(2026, 8, 1), date(2026, 9, 1)]


def test_columns_are_read_by_name_and_typed(con, tmp_path):
    table = TABLES["DISPATCHPRICE"]
    rows = aemo.load_file(con, table, zip_fixture(table, tmp_path), datetime(2026, 10, 17))
    assert rows == 60
    first = con.execute("select settlementdate, regionid, intervention, rrp, price_status "
                        "from raw.aemo_dispatchprice order by settlementdate, regionid limit 1").fetchone()
    assert first == (datetime(2026, 9, 1, 0, 5), "NSW1", 0, 100.0, "FIRM")


def test_quoted_timestamps_and_a_wide_opening_record_load(con, tmp_path):
    table = TABLES["DUALLOC"]
    assert aemo.load_file(con, table, zip_fixture(table, tmp_path), datetime(2026, 10, 17)) == 3
    assert con.execute("select min(effectivedate) from raw.aemo_dualloc").fetchone()[0] == datetime(2020, 1, 1)


def test_a_missing_column_is_named(con, tmp_path):
    path = tmp_path / "dispatchprice_202609_01_20261017.zip"
    text = (FIXTURES / "synthetic_aemo_dispatchprice.csv").read_text().replace("APCFLAG", "OTHERFLAG")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("x.CSV", text)
    with pytest.raises(ValueError, match=r"columns \['APCFLAG'\] not in"):
        aemo.load_file(con, TABLES["DISPATCHPRICE"], path, datetime(2026, 10, 17))


def test_a_truncated_file_is_rejected_and_nothing_is_loaded(con, tmp_path):
    path = tmp_path / "dispatchprice_202609_01_20261017.zip"
    lines = (FIXTURES / "synthetic_aemo_dispatchprice.csv").read_text().split("\r\n")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("x.CSV", "\r\n".join(lines[:10] + lines[-1:]))
    with pytest.raises(ValueError, match="file says 63"):
        aemo.load_file(con, TABLES["DISPATCHPRICE"], path, datetime(2026, 10, 17))
    assert con.execute("select count(*) from raw.aemo_dispatchprice").fetchone()[0] == 0


def test_loading_twice_adds_nothing(con, tmp_path):
    table = TABLES["DISPATCH_UNIT_SCADA"]
    paths = [zip_fixture(table, tmp_path)]
    assert aemo.load(con, table, paths) == 1
    assert aemo.load(con, table, paths) == 0
    assert con.execute("select count(*) from raw.aemo_dispatch_unit_scada").fetchone()[0] == 36


REGIONS = ["NSW1", "QLD1", "SA1", "TAS1", "VIC1"]


def add_flagged_prices(con, first: str, last: str, suspended: int = 0, apc: int = 0):
    """Pricing-run rows for every region and 5-minute interval ending from first to last."""
    con.execute("""insert into raw.aemo_dispatchprice
        (settlementdate, regionid, intervention, rrp, apcflag, marketsuspendedflag, _source_file, _loaded_at)
        select t, r, 0, 300, ?, ?, 'x.zip', now()
        from generate_series(?::timestamp, ?::timestamp, interval 5 minute) s(t), unnest(?) u(r)""",
                [apc, suspended, first, last, REGIONS])


def test_the_june_2022_suspension_is_one_run_through_both_flag_codes(con):
    # AEMO suspended every region from 14:05 on 15 June 2022 to 14:00 on 24 June. The archive flags it 2 until
    # the interval ending 04:00 on 23 June and 1 after, so a filter on "= 1" would start the run on 23 June.
    add_flagged_prices(con, "2022-06-15 13:00", "2022-06-15 14:05")
    add_flagged_prices(con, "2022-06-15 14:10", "2022-06-23 04:00", suspended=2)
    add_flagged_prices(con, "2022-06-23 04:05", "2022-06-24 14:00", suspended=1)
    add_flagged_prices(con, "2022-06-24 14:05", "2022-06-24 15:00")
    assert aemo.suspension_runs(con) == [
        (r, datetime(2022, 6, 15, 14, 10), datetime(2022, 6, 24, 14, 0), 2591) for r in REGIONS]


def test_any_apc_bit_counts_as_set(con):
    for i, apc in enumerate([0, 1, 4, 16, 21]):
        add_flagged_prices(con, f"2022-06-13 0{i}:05", f"2022-06-13 0{i}:05", apc=apc)
    rows = con.execute(f"select count(*) from raw.aemo_dispatchprice where {aemo.APC_SET}").fetchone()[0]
    assert rows == 4 * len(REGIONS)


@pytest.mark.skipif(not WAREHOUSE_PATH.exists(), reason="needs the loaded warehouse")
def test_the_warehouse_flags_the_full_june_2022_suspension():
    with duckdb.connect(str(WAREHOUSE_PATH), read_only=True) as warehouse:
        if not warehouse.execute("select count(*) from raw.aemo_dispatchprice "
                                 "where settlementdate = '2022-06-20 12:00'").fetchone()[0]:
            pytest.skip("warehouse does not hold June 2022")
        runs = aemo.suspension_runs(warehouse)
    june = [run for run in runs if date(2022, 6, 1) <= run[1].date() < date(2022, 7, 1)]
    assert june ==[(r, datetime(2022, 6, 15, 14, 10), datetime(2022, 6, 24, 14, 0), 2591) for r in REGIONS]


class FakeClient:
    """Serves listings and zips by URL and records every request."""

    def __init__(self, pages: dict[str, bytes]):
        self.pages, self.requested = pages, []

    def get(self, url: str) -> bytes:
        self.requested.append(url)
        return self.pages[url]


def archive_pages(base: str) -> dict[str, bytes]:
    pages = {f"{base}2026/": b'<A HREF="/MMSDM/2026/MMSDM_2026_08/">x</A><A HREF="/MMSDM/2026/MMSDM_2026_09/">x</A>'}
    for month in ("08", "09"):
        data = f"/MMSDM/2026/MMSDM_2026_{month}/MMSDM_Historical_Data_SQLLoader/DATA/"
        links = [f"{data}PUBLIC_ARCHIVE%23{t.name}%23FILE01%232026{month}010000.zip" for t in aemo.TABLES]
        pages[f"{base}2026/MMSDM_2026_{month}/MMSDM_Historical_Data_SQLLoader/DATA/"] = \
            "".join(f'<A HREF="{link}">x</A>' for link in links).encode()
        pages.update({f"https://nemweb.example{link}": f"{link}".encode() for link in links})
    return pages


def test_download_fetches_each_table_month_once_and_standing_tables_for_the_newest_month(tmp_path):
    base = "https://nemweb.example/MMSDM/"
    settings = {"archive_url": base, "start_month": "2026-08", "scada_start_month": "2026-09"}
    client = FakeClient(archive_pages(base))
    aemo.download(client, settings, tmp_path, today=date(2026, 10, 17))
    saved = sorted(p.name.rsplit("_", 1)[0] for p in tmp_path.iterdir())
    interval = ["dispatchinterconnectorres", "dispatchprice", "dispatchregionsum", "tradingprice"]
    standing = ["dualloc", "dudetailsummary", "genunits", "market_price_thresholds"]
    assert saved == sorted([f"{t}_202608_01" for t in interval] + [f"{t}_202609_01" for t in interval]
                           + ["dispatch_unit_scada_202609_01"] + [f"{t}_202609_01" for t in standing])

    client.requested.clear()
    aemo.download(client, settings, tmp_path, today=date(2026, 10, 17))
    assert client.requested == [f"{base}2026/"]
