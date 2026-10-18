"""Ask a natural-language question of the read-only NEM marts.

    python -m warehouse_chat "What was the highest price in South Australia in 2025?"
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from ingestion.config import WAREHOUSE_PATH
from warehouse_chat import DISCLAIMER, ollama
from warehouse_chat.runner import answer


def _json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat(sep=" ")
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def _table(columns: list[str], rows: list[tuple]) -> str:
    values = [["" if value is None else str(value) for value in row] for row in rows]
    widths = [len(column) for column in columns]
    for row in values:
        widths = [max(width, len(value)) for width, value in zip(widths, row)]
    lines = [" | ".join(column.ljust(width) for column, width in zip(columns, widths))]
    lines.append("-+-".join("-" * width for width in widths))
    lines += [" | ".join(value.ljust(width) for value, width in zip(row, widths)) for row in values]
    return "\n".join(lines)


def render(out: dict) -> str:
    lines = []
    if out["kind"] == "query":
        lines += ["SQL:", out["sql"], "", "Result:"]
        result = out["result"]
        lines.append(_table(result["columns"], result["rows"]) if result["rows"] else "No rows.")
        if result["truncated"]:
            lines.append(f"Result stopped at {result['row_count']} rows.")
        for caveat in out["caveats"]:
            lines.append(f"Caveat: {caveat['text']}")
    else:
        lines.append(out["message"])
        lines += ["", "SQL: none (no query was run)."]
        for attempt in out["attempts"]:
            if attempt["sql"]:
                lines += ["", "Rejected SQL attempt:", attempt["sql"]]
            lines.append(f"Validation: {attempt['rule']} — {attempt['error']}")
    lines += ["", DISCLAIMER]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question")
    parser.add_argument("--model", default=ollama.DEFAULT_MODEL)
    parser.add_argument("--warehouse", type=Path, default=WAREHOUSE_PATH)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        out = answer(args.question, args.warehouse, args.model)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"The local model could not answer: {exc}\n\n{DISCLAIMER}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({**out, "disclaimer": DISCLAIMER}, default=_json_default, indent=2))
    else:
        print(render(out))
    return 0 if out["kind"] in ("query", "refusal", "clarification") else 1


if __name__ == "__main__":
    raise SystemExit(main())
