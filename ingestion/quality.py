"""Data quality checks on the raw tables. Exits 1 if any check fails.

    python -m ingestion.quality
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime

import duckdb

from ingestion import aemo
from ingestion.config import WAREHOUSE_PATH, sources
from ingestion.run import NEM_TIME

RBA_TABLES = ["rba_f11", "rba_f1", "rba_a2"]
UNIQUE_KEYS = {
    "aemo_dispatchprice": "settlementdate, regionid, intervention",
    "aemo_tradingprice": "settlementdate, regionid",
    "aemo_dispatchregionsum": "settlementdate, regionid, intervention",
    "aemo_dispatchinterconnectorres": "settlementdate, interconnectorid, intervention",
    "aemo_dispatch_unit_scada": "settlementdate, duid",
}
# Five-minute settlement started on 1 October 2021. The last 30-minute trading interval ends at midnight.
FIVE_MINUTE_SETTLEMENT = "2021-10-01 00:00:00"


@dataclass(frozen=True)
class Check:
    name: str
    status: str  # pass, warn or fail
    detail: str


def _count_check(con, name: str, sql: str, what: str) -> Check:
    n = con.execute(sql).fetchone()[0]
    return Check(name, "fail" if n else "pass", f"{n} {what}")


def check_unique_keys(con: duckdb.DuckDBPyConnection) -> list[Check]:
    # Each file is a snapshot, so the same key in two files is expected.
    return [_count_check(con, f"unique_{table.removeprefix('aemo_')}",
                         f"select count(*) from (select 1 from raw.{table} group by {key}, _source_file "
                         "having count(*) > 1)", f"duplicate ({key}) keys within a file")
            for table, key in UNIQUE_KEYS.items()]


def check_regions(con: duckdb.DuckDBPyConnection, regions: list[str]) -> Check:
    present = {r[0] for r in con.execute("select distinct regionid from raw.aemo_dispatchprice").fetchall()}
    missing, extra = sorted(set(regions) - present), sorted(present - set(regions))
    if missing or extra:
        return Check("regions", "fail", f"missing {missing}, unexpected {extra}")
    return Check("regions", "pass", f"all {len(regions)} regions present")


def check_dispatch_intervals(con: duckdb.DuckDBPyConnection) -> Check:
    """Warn on missing 5-minute intervals inside each region's range of pricing-run prices."""
    rows = con.execute("""
        select regionid, (epoch(max(settlementdate)) - epoch(min(settlementdate))) / 300 + 1
                         - count(distinct settlementdate) as gaps
        from raw.aemo_dispatchprice where intervention = 0 group by regionid order by regionid
    """).fetchall()
    notes = [f"{region}: {int(gaps)} missing intervals" for region, gaps in rows if gaps]
    return Check("dispatch_intervals", "warn" if notes else "pass", "; ".join(notes) or "no gaps")


def check_price_limits(con: duckdb.DuckDBPyConnection) -> Check:
    """Every dispatch price must sit between the market price floor and cap in force at the time."""
    return _count_check(con, "price_limits", """
        with limits as (
            select effectivedate, max_by(voll, versionno) as cap, max_by(marketpricefloor, versionno) as floor
            from raw.aemo_market_price_thresholds group by effectivedate
        )
        select count(*) from raw.aemo_dispatchprice p
        asof left join limits l on p.settlementdate > l.effectivedate
        where l.cap is null or p.rrp > l.cap or p.rrp < l.floor
    """, "dispatch prices outside the floor and cap, or with no thresholds loaded")


def check_trading_intervals(con: duckdb.DuckDBPyConnection) -> Check:
    return _count_check(con, "trading_intervals", f"""
        select count(*) from raw.aemo_tradingprice
        where (settlementdate <= '{FIVE_MINUTE_SETTLEMENT}' and minute(settlementdate) % 30 != 0)
           or second(settlementdate) != 0 or minute(settlementdate) % 5 != 0
    """, "trading prices off the 30-minute grid before 5-minute settlement or the 5-minute grid after")


def check_no_future_rows(con: duckdb.DuckDBPyConnection, now: datetime) -> Check:
    parts = [f"(select count(*) from raw.{t} where settlementdate > '{now:%Y-%m-%d %H:%M:%S}')" for t in UNIQUE_KEYS]
    parts += [f"(select count(*) from raw.{t} where obs_date > '{now.date()}')" for t in RBA_TABLES]
    return _count_check(con, "no_future_rows", "select " + " + ".join(parts), f"rows dated after {now:%Y-%m-%d %H:%M}")


def check_units_registered(con: duckdb.DuckDBPyConnection) -> Check:
    missing = [r[0] for r in con.execute("""
        select distinct duid from raw.aemo_dispatch_unit_scada
        where duid not in (select duid from raw.aemo_dudetailsummary) order by duid
    """).fetchall()]
    if missing:
        return Check("units_registered", "warn", f"{len(missing)} units with SCADA but no registration: "
                                                  f"{', '.join(missing[:10])}")
    return Check("units_registered", "pass", "every unit with SCADA is registered")


def check_snapshots_do_not_shrink(con: duckdb.DuckDBPyConnection) -> Check:
    """A newer snapshot of a dataset with fewer rows than the one before usually means a truncated file."""
    stamp = r"_\d{8}(T\d{6})?\.\w+$"
    datasets = {t: stamp for t in RBA_TABLES}
    # An interval table's dataset is one table-month. A standing table repeats all history, so months compare.
    datasets |= {t.raw_table: r"_\d{6}_\d\d" + stamp if t.standing else stamp for t in aemo.TABLES}
    shrunk = []
    for table, pattern in datasets.items():
        shrunk += con.execute(f"""
            with files as (
                select regexp_replace(_source_file, '{pattern}', '') as dataset, _source_file, count(*) as n
                from raw.{table} group by all
            )
            select _source_file, n, prev from (
                select *, lag(n) over (partition by dataset order by _source_file) as prev from files
            ) where n < prev
        """).fetchall()
    if shrunk:
        return Check("snapshots_do_not_shrink", "fail",
                     "; ".join(f"{f}: {n} rows, previous {p}" for f, n, p in shrunk))
    return Check("snapshots_do_not_shrink", "pass", "no snapshot is smaller than the one before")


def check_freshness(con: duckdb.DuckDBPyConnection, now: datetime, max_age_days: int) -> list[Check]:
    newest = con.execute("select max(settlementdate) from raw.aemo_dispatchprice").fetchone()[0]
    if newest is None:
        dispatch = Check("freshness_dispatch", "fail", "no dispatch prices loaded")
    else:
        age = (now - newest).days
        dispatch = Check("freshness_dispatch", "warn" if age > max_age_days else "pass",
                         f"newest dispatch interval {newest}, {age} days old")
    newest_rba = {t: con.execute(f"select max(obs_date) from raw.{t}").fetchone()[0] for t in RBA_TABLES}
    status = "fail" if None in newest_rba.values() else "pass"
    detail = ", ".join(f"{t} {d}" for t, d in newest_rba.items())
    return [dispatch, Check("freshness_rba", status, f"newest observations: {detail}")]


def run_checks(con: duckdb.DuckDBPyConnection, regions: list[str], now: datetime,
               max_age_days: int) -> list[Check]:
    return [
        *check_unique_keys(con),
        check_regions(con, regions),
        check_dispatch_intervals(con),
        check_price_limits(con),
        check_trading_intervals(con),
        check_no_future_rows(con, now),
        check_units_registered(con),
        check_snapshots_do_not_shrink(con),
        *check_freshness(con, now, max_age_days),
    ]


def nem_now() -> datetime:
    """Current NEM market time as a naive datetime, matching how AEMO timestamps are stored."""
    return datetime.now(NEM_TIME).replace(tzinfo=None)


def main() -> int:
    settings = sources()
    with duckdb.connect(str(WAREHOUSE_PATH), read_only=True) as con:
        results = run_checks(con, settings["aemo"]["regions"], nem_now(),
                             settings["quality"]["max_dispatch_age_days"])
    for r in results:
        print(f"{r.status.upper():4}  {r.name}: {r.detail}")
    return 1 if any(r.status == "fail" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
