"""Data quality checks on the raw tables. Exits 1 if any check fails.

    python -m ingestion.quality
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

import duckdb

from ingestion.config import WAREHOUSE_PATH, expected_tickers, sources

SNAPSHOT_TABLES = ["prices", "rba_f11", "rba_f1", "rba_a2"]
RBA_TABLES = ["rba_f11", "rba_f1", "rba_a2"]


@dataclass(frozen=True)
class Check:
    name: str
    status: str  # pass, warn or fail
    detail: str


def _count_check(con, name: str, sql: str, what: str) -> Check:
    n = con.execute(sql).fetchone()[0]
    return Check(name, "fail" if n else "pass", f"{n} {what}")


def sydney_today() -> date:
    return datetime.now(ZoneInfo("Australia/Sydney")).date()


def check_prices(con: duckdb.DuckDBPyConnection, today: date) -> list[Check]:
    return [
        _count_check(con, "positive_prices",
                     "select count(*) from raw.prices where open <= 0 or high <= 0 or low <= 0 "
                     "or close <= 0 or adj_close <= 0", "rows with a zero or negative price"),
        _count_check(con, "high_not_below_low",
                     "select count(*) from raw.prices where high < low", "rows with high below low"),
        # Each file is a snapshot, so the same (ticker, date) in two files is expected.
        _count_check(con, "unique_ticker_date",
                     "select count(*) from (select 1 from raw.prices "
                     "group by ticker, date, _source_file having count(*) > 1)",
                     "duplicate (ticker, date) pairs within a file"),
        _count_check(con, "trading_days",
                     "select count(*) from raw.prices p where p.date between "
                     "(select min(session_date) from raw.asx_sessions) and (select max(session_date) from raw.asx_sessions) "
                     "and p.date not in (select session_date from raw.asx_sessions)",
                     "price rows on days the ASX was closed"),
        _count_check(con, "no_future_dates",
                     f"select (select count(*) from raw.prices where date > '{today}') + "
                     + " + ".join(f"(select count(*) from raw.{t} where obs_date > '{today}')" for t in RBA_TABLES),
                     f"rows dated after {today}"),
    ]


def check_expected_tickers(con: duckdb.DuckDBPyConnection, expected: dict[str, list[str]]) -> Check:
    present = {r[0] for r in con.execute("select distinct ticker from raw.prices").fetchall()}
    missing = [t for t, codes in expected.items() if not present.intersection(codes)]
    if missing:
        return Check("expected_tickers", "fail", f"missing {len(missing)} of {len(expected)}: {', '.join(missing)}")
    return Check("expected_tickers", "pass", f"all {len(expected)} present")


def check_snapshots_do_not_shrink(con: duckdb.DuckDBPyConnection) -> Check:
    """A newer snapshot of a dataset with fewer rows than the one before usually means a truncated file."""
    shrunk = []
    for table in SNAPSHOT_TABLES:
        shrunk += con.execute(f"""
            with files as (
                select regexp_replace(_source_file, '_\\d{{8}}(T\\d{{6}})?\\.\\w+$', '') as dataset,
                       _source_file, count(*) as n
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


def check_coverage(con: duckdb.DuckDBPyConnection, max_age: int) -> Check:
    """Warn on missing sessions inside each ticker's range and on tickers that stop early (delisted or renamed)."""
    rows = con.execute("""
        with spans as (
            select ticker, min(date) as first, max(date) as last, count(distinct date) as days
            from raw.prices group by ticker
        )
        select s.ticker, s.last,
               (select count(*) from raw.asx_sessions where session_date between s.first and s.last) - s.days as gaps,
               (select count(*) from raw.asx_sessions where session_date > s.last
                  and session_date <= (select max(date) from raw.prices)) as behind
        from spans s order by s.ticker
    """).fetchall()
    notes = [f"{t}: {g} missing sessions" for t, _, g, _ in rows if g > 0]
    notes += [f"{t}: ends {last}, {b} sessions before the newest price" for t, last, _, b in rows if b > max_age]
    return Check("coverage", "warn" if notes else "pass", "; ".join(notes) or "no gaps")


def check_freshness(con: duckdb.DuckDBPyConnection, today: date, max_age: int) -> list[Check]:
    newest = con.execute("select max(date) from raw.prices").fetchone()[0]
    if newest is None:
        prices = Check("freshness_prices", "fail", "no price data loaded")
    else:
        age = con.execute("select count(*) from raw.asx_sessions where session_date > ? and session_date <= ?",
                          [newest, today]).fetchone()[0]
        status = "warn" if age > max_age else "pass"
        prices = Check("freshness_prices", status,
                       f"newest price {newest}, {age} sessions and {(today - newest).days} days old")
    rba = ", ".join(f"{t} {con.execute(f'select max(obs_date) from raw.{t}').fetchone()[0]}" for t in RBA_TABLES)
    return [prices, Check("freshness_rba", "pass", f"newest observations: {rba}")]


def run_checks(con: duckdb.DuckDBPyConnection, expected: dict[str, list[str]], today: date,
               max_age: int) -> list[Check]:
    return [
        *check_prices(con, today),
        check_expected_tickers(con, expected),
        check_snapshots_do_not_shrink(con),
        check_coverage(con, max_age),
        *check_freshness(con, today, max_age),
    ]


def main() -> int:
    max_age = sources()["quality"]["max_price_age_sessions"]
    with duckdb.connect(str(WAREHOUSE_PATH), read_only=True) as con:
        results = run_checks(con, expected_tickers(), sydney_today(), max_age)
    for r in results:
        print(f"{r.status.upper():4}  {r.name}: {r.detail}")
    return 1 if any(r.status == "fail" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
