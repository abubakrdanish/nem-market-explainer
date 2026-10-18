"""Parse and validate model-written SQL before it reaches DuckDB."""
from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from warehouse_chat.schema import ALLOWED_TABLES

ALLOWED_FUNCTIONS = {
    "abs", "avg", "coalesce", "count", "date_part", "date_trunc", "day", "dayname", "dayofweek",
    "extract", "greatest", "hour", "least", "max", "median", "min", "minute", "month", "nullif",
    "quarter", "round", "strftime", "sum", "week", "year",
}

FUNCTION_NAMES = {
    exp.DayOfWeek: "dayofweek",
    exp.TimestampTrunc: "date_trunc",
    exp.TimeToStr: "strftime",
}

DISALLOWED_NODES = tuple(
    node for node in (
        getattr(exp, name, None) for name in (
            "Alter", "Analyze", "Attach", "Cache", "Command", "Copy", "Create", "Delete", "Detach", "Drop",
            "Execute", "Export", "Grant", "Insert", "LoadData", "Merge", "Pragma", "Set", "Transaction",
            "TruncateTable", "Update", "Use",
        )
    ) if node is not None
)


@dataclass(frozen=True)
class ValidationError(ValueError):
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.rule}: {self.detail}"


def _fail(rule: str, detail: str) -> None:
    raise ValidationError(rule, detail)


def _function_name(function: exp.Func) -> str:
    for kind, name in FUNCTION_NAMES.items():
        if isinstance(function, kind):
            return name
    if isinstance(function, exp.Anonymous):
        return function.name.lower()
    return function.sql_name().lower()


def validate_sql(sql: str) -> str:
    """Return normalized SQL if one read-only, allowlisted SELECT passes every rule."""
    if not sql.strip():
        _fail("empty_sql", "The model did not return SQL.")
    try:
        statements = sqlglot.parse(sql, read="duckdb")
    except ParseError as exc:
        detail = exc.errors[0]["description"] if exc.errors else str(exc)
        _fail("parse_error", f"DuckDB SQL could not be parsed: {detail}")
    parsed = [statement for statement in statements if statement is not None]
    if not parsed:
        _fail("empty_sql", "No executable SQL was returned.")
    if any(node.comments for statement in parsed for node in statement.walk()):
        _fail("comments_not_allowed", "SQL comments are not allowed.")
    if len(statements) != 1:
        _fail("single_statement_only", f"Expected one statement, found {len(statements)}.")
    statement = parsed[0]
    if not isinstance(statement, exp.Select):
        _fail("select_only", f"Expected SELECT, found {type(statement).__name__.upper()}.")
    forbidden = next((node for node in statement.walk() if isinstance(node, DISALLOWED_NODES)), None)
    if forbidden is not None:
        _fail("select_only", f"{type(forbidden).__name__.upper()} is not allowed inside a query.")

    ctes = {cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE)}
    for table in statement.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            _fail("table_function_not_allowed", f"Table function {table.this.sql(dialect='duckdb')} is not allowed.")
        name = table.name.lower()
        if not table.db and name in ctes:
            continue
        if table.catalog or not table.db:
            _fail("table_not_allowed", f"Physical table {table.sql(dialect='duckdb')} must be schema-qualified and allowlisted.")
        qualified = f"{table.db.lower()}.{name}"
        if qualified not in ALLOWED_TABLES:
            _fail("table_not_allowed", f"Table {qualified} is not in the allowlist.")

    for function in statement.find_all(exp.Func):
        if isinstance(function, (exp.Connector, exp.Cast, exp.Case)):
            continue
        if isinstance(function, exp.If) and isinstance(function.parent, exp.Case):
            continue
        name = _function_name(function)
        if name not in ALLOWED_FUNCTIONS:
            _fail("function_not_allowed", f"Function {name} is not in the allowlist.")
    return statement.sql(dialect="duckdb", pretty=True)
