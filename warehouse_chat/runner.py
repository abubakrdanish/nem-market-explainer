"""Validate and run SQL against a read-only DuckDB connection."""
from __future__ import annotations

import re
import threading
import time
from datetime import date
from pathlib import Path

import duckdb

from ingestion.config import WAREHOUSE_PATH
from warehouse_chat import ollama
from warehouse_chat.validate import ValidationError, validate_sql

ROW_CAP = 200
QUERY_TIMEOUT_SECONDS = 10
MAX_RETRIES = 2

PERMITTED = ("Only one schema-qualified SELECT over the allowed marts and reference tables, using allowlisted "
             "functions, is permitted.")
POLICY_RULES = {
    "comments_not_allowed": "SQL comments are not permitted.",
    "single_statement_only": "More than one SQL statement is not permitted.",
    "select_only": "The statement is not a SELECT.",
    "table_function_not_allowed": "Table functions, including file readers, are not permitted.",
    "table_not_allowed": "The query names a table outside the allowlist.",
    "function_not_allowed": "The query calls a function outside the allowlist.",
}

CAVEATS = {
    "rooftop_solar": "Generation comes from SCADA and excludes rooftop solar, so solar's share of supply is understated.",
    "settlement_change": "Five-minute settlement began on 1 October 2021; dispatch prices are five-minute throughout.",
    "battery_accounting": ("Battery accounting changed between 4 July and 11 December 2024 as batteries moved from "
                           "split units to bidirectional units, so charging is not comparable across the change."),
}


class QueryTimeout(RuntimeError):
    pass


def refusal_message(rule: str) -> str:
    """Describe a refusal without asking the model to explain system behaviour."""
    if rule == "model_refusal":
        reason = "The model returned no SQL."
    else:
        reason = POLICY_RULES[rule]
    return f"Refused by {rule}: {reason} No query was run. {PERMITTED}"


def clarification_message() -> str:
    """Return the fixed clarification text used instead of model-written system explanations."""
    return ("Clarification required by model_clarification: specify the region, date or period, and measure. "
            f"No query was run. {PERMITTED}")


def connect(path: Path = WAREHOUSE_PATH) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(path), read_only=True)


def execute(con: duckdb.DuckDBPyConnection, sql: str, row_cap: int = ROW_CAP,
            timeout: int = QUERY_TIMEOUT_SECONDS) -> dict:
    """Run validated SQL with a hard result cap and an interrupting timer."""
    wrapped = f"select * from ({sql}) as warehouse_chat_result limit {row_cap + 1}"
    timed_out = threading.Event()

    def interrupt() -> None:
        timed_out.set()
        con.interrupt()

    timer = threading.Timer(timeout, interrupt)
    started = time.monotonic()
    timer.start()
    try:
        cursor = con.execute(wrapped)
        rows = cursor.fetchall()
        columns = [column[0] for column in cursor.description]
    except duckdb.InterruptException as exc:
        if timed_out.is_set():
            raise QueryTimeout(f"Query exceeded the {timeout}-second limit.") from exc
        raise
    finally:
        timer.cancel()
        timer.join()
    truncated = len(rows) > row_cap
    return {
        "columns": columns,
        "rows": rows[:row_cap],
        "row_count": min(len(rows), row_cap),
        "truncated": truncated,
        "seconds": round(time.monotonic() - started, 3),
    }


def caveat_ids(question: str, sql: str, requested: list[str]) -> list[str]:
    """Add known caveats from the question and validated SQL, without trusting the model alone."""
    text = f"{question} {sql}".lower()
    found = {item for item in requested if item in CAVEATS}
    if any(word in text for word in ("generation", "fuel", "coal", "gas", "hydro", "wind", "solar", "bioenergy")):
        found.add("rooftop_solar")
    if "battery" in text:
        found.add("battery_accounting")
    dates = sorted(date.fromisoformat(value) for value in re.findall(r"\b\d{4}-\d\d-\d\d\b", text))
    change = date(2021, 10, 1)
    if "settlement" in text or dates and dates[0] <= change:
        found.add("settlement_change")
    return [item for item in CAVEATS if item in found]


def answer(question: str, warehouse: Path = WAREHOUSE_PATH, model: str = ollama.DEFAULT_MODEL,
           today: date | None = None) -> dict:
    """Ask the model, validate its SQL and return rows or a safe non-query outcome."""
    feedback = None
    attempts = []
    with connect(warehouse) as con:
        for _ in range(MAX_RETRIES + 1):
            response = ollama.ask(question, model, feedback, today, warehouse=warehouse)
            kind = response.get("kind")
            if kind == "refusal":
                return {
                    "kind": "refusal",
                    "message": refusal_message("model_refusal"),
                    "sql": "",
                    "caveats": [],
                    "model": response.get("model", model),
                    "attempts": attempts,
                }
            if kind == "clarification":
                return {
                    "kind": "clarification",
                    "message": clarification_message(),
                    "sql": "",
                    "caveats": [],
                    "model": response.get("model", model),
                    "attempts": attempts,
                }
            if kind != "query":
                feedback = "model_output_invalid: Return one complete object matching the requested JSON schema."
                attempts.append({"sql": "", "rule": "model_output_invalid", "error": feedback})
                continue
            sql = str(response.get("sql", ""))
            try:
                validated = validate_sql(sql)
                result = execute(con, validated)
            except (ValidationError, QueryTimeout, duckdb.Error) as exc:
                rule = exc.rule if isinstance(exc, ValidationError) else (
                    "query_timeout" if isinstance(exc, QueryTimeout) else "query_error")
                attempts.append({"sql": sql, "rule": rule, "error": str(exc)})
                if rule in POLICY_RULES:
                    return {
                        "kind": "refusal",
                        "message": refusal_message(rule),
                        "sql": "",
                        "caveats": [],
                        "model": response.get("model", model),
                        "attempts": attempts,
                    }
                feedback = str(exc)
                continue
            requested = response.get("caveats", [])
            ids = caveat_ids(question, validated, requested if isinstance(requested, list) else [])
            return {
                "kind": "query",
                "message": "",
                "sql": validated,
                "result": result,
                "caveats": [{"id": item, "text": CAVEATS[item]} for item in ids],
                "model": response.get("model", model),
                "attempts": attempts,
            }
    return {
        "kind": "error",
        "message": f"No query succeeded after {MAX_RETRIES + 1} attempts. {PERMITTED}",
        "sql": attempts[-1]["sql"] if attempts else "",
        "caveats": [],
        "model": model,
        "attempts": attempts,
    }
