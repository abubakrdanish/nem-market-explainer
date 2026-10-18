from __future__ import annotations

import pytest

from warehouse_chat.validate import ALLOWED_FUNCTIONS, ValidationError, validate_sql


def rejected(sql: str, rule: str) -> None:
    with pytest.raises(ValidationError) as exc:
        validate_sql(sql)
    assert exc.value.rule == rule
    assert str(exc.value).startswith(rule + ":")


def test_allows_select_ctes_joins_and_case():
    sql = """
        with days as (
            select market_date, case when avg_price < 0 then 1 else 0 end as negative
            from marts.mart_region_daily)
        select r.region_name, count(*) filter (where d.negative = 1) as days
        from days d cross join reference.regions r
        group by r.region_name
    """
    assert validate_sql(sql).startswith("WITH days AS")


def test_declared_function_allowlist_is_accepted():
    expressions = {
        "abs": "abs(price)", "avg": "avg(price)", "coalesce": "coalesce(price, 0)", "count": "count(*)",
        "date_part": "date_part('year', market_date)", "date_trunc": "date_trunc('month', market_date)",
        "day": "day(market_date)", "dayname": "dayname(market_date)", "dayofweek": "dayofweek(market_date)",
        "extract": "extract(year from market_date)", "greatest": "greatest(price, 0)",
        "hour": "hour(interval_end)", "least": "least(price, 0)", "max": "max(price)",
        "median": "median(price)", "min": "min(price)", "minute": "minute(interval_end)",
        "month": "month(market_date)", "nullif": "nullif(price, 0)", "quarter": "quarter(market_date)",
        "round": "round(price, 2)", "strftime": "strftime(market_date, '%Y-%m')", "sum": "sum(price)",
        "week": "week(market_date)", "year": "year(market_date)",
    }
    assert set(expressions) == ALLOWED_FUNCTIONS
    for expression in expressions.values():
        validate_sql(f"select {expression} from marts.mart_region_interval")


@pytest.mark.parametrize("sql", [
    "insert into marts.mart_region_daily by name select * from marts.mart_region_daily",
    "update marts.mart_region_daily set avg_price = 0",
    "delete from marts.mart_region_daily",
    "create table x as select 1",
    "drop table marts.mart_region_daily",
    "attach 'other.duckdb' as other",
    "copy marts.mart_region_daily to '/tmp/out.csv'",
    "install httpfs",
    "load httpfs",
    "export database '/tmp/export'",
    "pragma database_list",
    "set memory_limit = '1GB'",
])
def test_rejects_every_non_select_category(sql):
    with pytest.raises(ValidationError):
        validate_sql(sql)


@pytest.mark.parametrize("sql", [
    "select * from read_csv_auto('/etc/passwd')",
    "select * from read_parquet('/tmp/data.parquet')",
    "select * from glob('/tmp/*')",
    "select read_blob('/etc/passwd')",
])
def test_rejects_file_reads(sql):
    with pytest.raises(ValidationError) as exc:
        validate_sql(sql)
    assert exc.value.rule in ("table_function_not_allowed", "function_not_allowed")


@pytest.mark.parametrize("table", [
    "raw.aemo_dispatchprice",
    "staging.stg_aemo__dispatch_price",
    "intermediate.int_price_30min",
    "reference.event_regions",
    "reference.fuel_groups",
])
def test_rejects_tables_outside_allowlist(table):
    rejected(f"select * from {table}", "table_not_allowed")


def test_rejects_unqualified_physical_table():
    rejected("select * from mart_region_daily", "table_not_allowed")


def test_rejects_unknown_function():
    rejected("select current_setting('access_mode') from marts.mart_region_daily", "function_not_allowed")


def test_rejects_multiple_statements():
    rejected("select * from marts.mart_region_daily; select * from marts.mart_events", "single_statement_only")


def test_rejects_second_statement_hidden_in_comment():
    rejected("select count(*) from marts.mart_region_daily /* ; drop table marts.mart_region_daily */",
             "comments_not_allowed")


def test_rejects_line_comments():
    rejected("select * from marts.mart_region_daily -- harmless", "comments_not_allowed")


def test_rejects_comment_only_without_crashing():
    rejected("-- no query", "empty_sql")


def test_rejects_table_function_even_when_its_name_looks_like_a_cte():
    rejected("with range as (select * from marts.mart_region_daily) select * from range(10)",
             "table_function_not_allowed")
