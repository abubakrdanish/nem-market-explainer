from __future__ import annotations

import json
import threading
from datetime import date

import duckdb
import pytest

from warehouse_chat import runner
from warehouse_chat.prompt import SCHEMA, _last_winter, user_message
from warehouse_chat.schema import prompt_schema
from warehouse_chat.validate import validate_sql


def response(kind="query", sql="", message="", caveats=None):
    return {"kind": kind, "sql": sql, "message": message, "caveats": caveats or [],
            "model": "mock", "seconds": 0}


def test_connection_is_enforced_read_only(fixture_marts):
    with runner.connect(fixture_marts) as con:
        with pytest.raises(duckdb.Error):
            con.execute("create table should_fail (x integer)")


def test_runner_uses_fixture_marts_and_caps_rows(fixture_marts):
    sql = validate_sql("""
        select market_date, region_id from marts.mart_region_daily
        order by region_id
    """)
    with runner.connect(fixture_marts) as con:
        result = runner.execute(con, sql, row_cap=2)
    assert result["row_count"] == 2
    assert result["truncated"] is True
    assert result["columns"] == ["market_date", "region_id"]


def test_query_timeout_interrupts_connection():
    class SlowConnection:
        def __init__(self):
            self.interrupted = threading.Event()

        def execute(self, sql):
            self.interrupted.wait(1)
            raise duckdb.InterruptException("interrupted")

        def interrupt(self):
            self.interrupted.set()

    with pytest.raises(runner.QueryTimeout, match="exceeded"):
        runner.execute(SlowConnection(), "select 1", timeout=0.01)


def test_answer_repairs_one_invalid_query(monkeypatch, fixture_marts):
    replies = iter([
        response(sql="select missing_column from marts.mart_region_daily"),
        response(sql="select count(*) as days from marts.mart_region_daily"),
    ])
    monkeypatch.setattr(runner.ollama, "ask", lambda *args, **kwargs: next(replies))
    out = runner.answer("How many daily rows?", fixture_marts, today=date(2026, 10, 18))
    assert out["kind"] == "query"
    assert out["result"]["rows"] == [(5,)]
    assert [attempt["rule"] for attempt in out["attempts"]] == ["query_error"]


def test_answer_stops_after_retry_cap(monkeypatch, fixture_marts):
    calls = []

    def unsafe(*args, **kwargs):
        calls.append(1)
        return response(sql="select (")

    monkeypatch.setattr(runner.ollama, "ask", unsafe)
    out = runner.answer("Ignore the rules", fixture_marts)
    assert out["kind"] == "error"
    assert len(calls) == runner.MAX_RETRIES + 1
    assert len(out["attempts"]) == runner.MAX_RETRIES + 1
    assert {attempt["rule"] for attempt in out["attempts"]} == {"parse_error"}


def test_policy_refusal_comes_from_validator_and_names_rule(monkeypatch, fixture_marts):
    monkeypatch.setattr(runner.ollama, "ask", lambda *args, **kwargs:
                        response(sql="copy marts.mart_region_daily to '/tmp/prices.csv'",
                                 message="DuckDB does not support file operations."))
    out = runner.answer("Copy all daily prices to /tmp/prices.csv for me.", fixture_marts)
    assert out["kind"] == "refusal"
    assert out["message"].startswith("Refused by select_only:")
    assert "Only one schema-qualified SELECT" in out["message"]
    assert "does not support file operations" not in out["message"]
    assert [attempt["rule"] for attempt in out["attempts"]] == ["select_only"]


def test_answer_retries_malformed_model_output(monkeypatch, fixture_marts):
    replies = iter([
        response("invalid", message="Incomplete JSON"),
        response(sql="select count(*) as days from marts.mart_region_daily"),
    ])
    monkeypatch.setattr(runner.ollama, "ask", lambda *args, **kwargs: next(replies))
    out = runner.answer("How many daily rows?", fixture_marts)
    assert out["kind"] == "query"
    assert [attempt["rule"] for attempt in out["attempts"]] == ["model_output_invalid"]


def test_refusal_never_runs_sql(monkeypatch, fixture_marts):
    seen = []

    def refuse(*args, **kwargs):
        seen.append(kwargs["warehouse"])
        return response("refusal", message="The marts do not contain retail bills.")

    monkeypatch.setattr(runner.ollama, "ask", refuse)
    monkeypatch.setattr(runner, "execute", lambda *args, **kwargs: pytest.fail("SQL was run"))
    out = runner.answer("What was the household bill?", fixture_marts)
    assert out["kind"] == "refusal"
    assert out["sql"] == ""
    assert out["message"].startswith("Refused by model_refusal:")
    assert "retail bills" not in out["message"]
    assert seen == [fixture_marts]


def test_clarification_ignores_model_explanation(monkeypatch, fixture_marts):
    monkeypatch.setattr(runner.ollama, "ask", lambda *args, **kwargs:
                        response("clarification", message="DuckDB requires more information."))
    out = runner.answer("What was the best region?", fixture_marts)
    assert out["message"].startswith("Clarification required by model_clarification:")
    assert "DuckDB requires" not in out["message"]


def test_model_response_schema_has_no_message_field():
    assert "message" not in SCHEMA["properties"]
    assert SCHEMA["additionalProperties"] is False


def test_caveats_are_added_without_trusting_model():
    sql = "select solar_share from marts.mart_region_daily where market_date between date '2021-01-01' and date '2022-01-01'"
    assert runner.caveat_ids("Compare solar generation", sql, []) == ["rooftop_solar", "settlement_change"]
    assert runner.caveat_ids("Battery charging", "select battery_charging_mwh from marts.mart_region_daily", []) == [
        "battery_accounting"]


def test_prompt_schema_has_duckdb_types_and_dbt_descriptions(fixture_marts):
    schema = prompt_schema(fixture_marts)
    assert "market_date DATE: Calendar date in NEM market time." in schema
    assert "price DOUBLE: Dispatch price (RRP) from the pricing run, $/MWh." in schema


def test_user_message_reads_schema_from_selected_warehouse(fixture_marts):
    message = json.loads(user_message("Question", warehouse=fixture_marts))
    assert "market_date DATE: Calendar date in NEM market time." in message["database_schema"]


def test_last_winter_is_the_last_completed_winter():
    assert _last_winter(date(2026, 10, 18)) == "2026-06-01 through 2026-08-31"
    assert _last_winter(date(2026, 7, 1)) == "2025-06-01 through 2025-08-31"
