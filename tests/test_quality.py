from datetime import datetime

import pytest

from ingestion.quality import run_checks
from ingestion.run import import_events, load_all
from tests.conftest import EVENTS_FILE

REGIONS = ["NSW1", "QLD1", "SA1", "TAS1", "VIC1"]
NOW = datetime(2026, 10, 17, 12, 0)


@pytest.fixture
def loaded(con, raw_dir):
    import_events(EVENTS_FILE, raw_dir)
    load_all(con, raw_dir)
    return con


def results(con, now=NOW) -> dict[str, tuple[str, str]]:
    return {c.name: (c.status, c.detail) for c in run_checks(con, REGIONS, now, max_age_days=50)}


def add_price(con, when="2026-09-01 00:05:00", region="NSW1", rrp=50.0, intervention=0, source="extra.zip"):
    con.execute("insert into raw.aemo_dispatchprice (settlementdate, regionid, intervention, rrp, _source_file, "
                "_loaded_at) values (?, ?, ?, ?, ?, now())", [when, region, intervention, rrp, source])


def test_fixture_data_passes_every_check(loaded):
    statuses = {name: status for name, (status, _) in results(loaded).items()}
    assert statuses == {name: "pass" for name in statuses}


def test_duplicate_keys_within_a_file_fail(loaded):
    add_price(loaded)
    add_price(loaded)
    assert results(loaded)["unique_dispatchprice"][0] == "fail"


def test_an_intervention_row_is_not_a_duplicate(loaded):
    add_price(loaded, intervention=1, source="dispatchprice_202609_01_20261017.zip")
    assert results(loaded)["unique_dispatchprice"][0] == "pass"


@pytest.mark.parametrize("rrp", [10_000.0, -1_000.0])
def test_prices_outside_the_floor_and_cap_fail(loaded, rrp):
    add_price(loaded, rrp=rrp)
    assert results(loaded)["price_limits"][0] == "fail"


def test_prices_need_thresholds(loaded):
    loaded.execute("delete from raw.aemo_market_price_thresholds")
    assert results(loaded)["price_limits"][0] == "fail"


def test_a_missing_region_is_named(loaded):
    loaded.execute("delete from raw.aemo_dispatchprice where regionid = 'TAS1'")
    status, detail = results(loaded)["regions"]
    assert status == "fail" and "TAS1" in detail


def test_a_missing_interval_warns(loaded):
    loaded.execute("delete from raw.aemo_dispatchprice where regionid = 'SA1' and settlementdate = '2026-09-01 00:30'")
    status, detail = results(loaded)["dispatch_intervals"]
    assert status == "warn" and detail == "SA1: 1 missing intervals"


@pytest.mark.parametrize("when", ["2021-09-30 23:55:00", "2026-09-01 00:07:00"])
def test_trading_prices_off_their_grid_fail(loaded, when):
    loaded.execute("insert into raw.aemo_tradingprice (settlementdate, regionid, rrp, _source_file, _loaded_at) "
                   "values (?, 'NSW1', 1, 'x.zip', now())", [when])
    assert results(loaded)["trading_intervals"][0] == "fail"


def test_a_30_minute_trading_price_before_the_change_passes(loaded):
    loaded.execute("insert into raw.aemo_tradingprice (settlementdate, regionid, rrp, _source_file, _loaded_at) "
                   "values ('2021-10-01 00:00:00', 'NSW1', 1, 'x.zip', now())")
    assert results(loaded)["trading_intervals"][0] == "pass"


def test_future_rows_fail(loaded):
    assert results(loaded, now=datetime(2026, 9, 1, 0, 30))["no_future_rows"][0] == "fail"


def test_an_unregistered_unit_warns(loaded):
    loaded.execute("insert into raw.aemo_dispatch_unit_scada values ('2026-09-01 00:05', 'SYN_GHOST', 1, 'x.zip', now())")
    status, detail = results(loaded)["units_registered"]
    assert status == "warn" and "SYN_GHOST" in detail


def test_a_smaller_republished_month_fails(loaded):
    loaded.execute("insert into raw.aemo_dispatchprice select * replace ('dispatchprice_202609_01_20991231.zip' "
                   "as _source_file) from raw.aemo_dispatchprice where regionid = 'NSW1'")
    assert results(loaded)["snapshots_do_not_shrink"][0] == "fail"


def test_a_smaller_standing_table_in_a_later_month_fails(loaded):
    loaded.execute("insert into raw.aemo_dualloc select * replace ('dualloc_202610_01_20261112.zip' "
                   "as _source_file) from raw.aemo_dualloc limit 1")
    assert results(loaded)["snapshots_do_not_shrink"][0] == "fail"


def test_a_new_interval_month_is_not_compared_with_the_last(loaded):
    loaded.execute("insert into raw.aemo_dispatchprice select * replace ('dispatchprice_202610_01_20261112.zip' "
                   "as _source_file, settlementdate + interval 30 days as settlementdate) "
                   "from raw.aemo_dispatchprice where regionid = 'NSW1' limit 1")
    assert results(loaded, now=datetime(2026, 11, 1))["snapshots_do_not_shrink"][0] == "pass"


def test_freshness_reports_age_and_warns_when_stale(loaded):
    status, detail = results(loaded)["freshness_dispatch"]
    assert status == "pass" and detail == "newest dispatch interval 2026-09-01 01:00:00, 46 days old"
    assert results(loaded, now=datetime(2026, 11, 1))["freshness_dispatch"][0] == "warn"


def test_an_empty_rba_table_fails_freshness(loaded):
    loaded.execute("delete from raw.rba_a2")
    status, detail = results(loaded)["freshness_rba"]
    assert status == "fail" and "rba_a2 None" in detail
