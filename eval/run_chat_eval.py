"""Run the frozen warehouse-chat questions and compare them with trusted SQL.

    python -m eval.run_chat_eval --model qwen3:4b

Writes eval/results/chat/<model>.jsonl and prints the full result table. The expected SQL and non-query
outcomes live in eval/chat_cases.yml and were written before the first model run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import yaml

from warehouse_chat.runner import answer, connect, execute
from warehouse_chat.validate import ValidationError, validate_sql

HERE = Path(__file__).parent
CASES_PATH = HERE / "chat_cases.yml"


def _value(value):
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _same_value(actual, expected) -> bool:
    actual, expected = _value(actual), _value(expected)
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isclose(float(actual), float(expected), rel_tol=0.0001, abs_tol=0.01)
    return actual == expected


def same_result(actual: dict, expected: dict) -> bool:
    """Compare shape, truncation and values, allowing display-level numeric rounding."""
    if actual["truncated"] != expected["truncated"] or len(actual["rows"]) != len(expected["rows"]):
        return False
    actual_names = [name.lower() for name in actual["columns"]]
    expected_names = [name.lower() for name in expected["columns"]]
    if len(actual_names) == len(expected_names):
        indexes = list(range(len(expected_names)))
    elif all(name in expected_names for name in actual_names):
        indexes = [expected_names.index(name) for name in actual_names]
    else:
        return False
    return all(len(left) == len(indexes) and all(_same_value(value, right[index])
               for value, index in zip(left, indexes)) for left, right in zip(actual["rows"], expected["rows"]))


def safety_probe(case: dict) -> dict | None:
    if "attack_sql" not in case:
        return None
    try:
        validate_sql(case["attack_sql"])
    except ValidationError as exc:
        return {"allowed": False, "rule": exc.rule, "expected_rule": case["expected_rule"],
                "passed": exc.rule == case["expected_rule"], "error": str(exc)}
    return {"allowed": True, "rule": None, "expected_rule": case["expected_rule"], "passed": False,
            "error": "Attack SQL passed validation."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default="qwen3:4b")
    parser.add_argument("--only", nargs="*", help="case ids to run")
    args = parser.parse_args(argv)

    raw = CASES_PATH.read_bytes()
    case_hash = hashlib.sha256(raw).hexdigest()
    cases = yaml.safe_load(raw)["cases"]
    if args.only:
        cases = [case for case in cases if case["id"] in args.only]
    output_dir = HERE / "results" / "chat"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{args.model.replace(':', '_')}.jsonl"

    scores = []
    with connect() as con, output_path.open("w") as output:
        for case in cases:
            expected = execute(con, validate_sql(case["expected_sql"])) if "expected_sql" in case else None
            out = answer(case["question"], model=args.model, today=date(2026, 10, 18))
            probe = safety_probe(case)
            kind_correct = out["kind"] == case["expected_kind"]
            result_correct = (same_result(out["result"], expected)
                              if case["expected_kind"] == "query" and out["kind"] == "query" else None)
            expected_caveats = set(case.get("expected_caveats", []))
            actual_caveats = {item["id"] for item in out.get("caveats", [])}
            score = {
                "id": case["id"],
                "group": case["group"],
                "expected_kind": case["expected_kind"],
                "actual_kind": out["kind"],
                "kind_correct": kind_correct,
                "first_sql_valid": out["kind"] == "query" and not out["attempts"],
                "eventual_sql_valid": out["kind"] == "query",
                "result_correct": result_correct,
                "caveats_correct": expected_caveats <= actual_caveats,
                "attempt_rules": [attempt["rule"] for attempt in out["attempts"]],
                "safety_probe": probe,
            }
            record = {"case_hash": case_hash, "case": case, "expected_result": expected,
                      "output": out, "score": score}
            output.write(json.dumps(record, default=_value) + "\n")
            output.flush()
            scores.append(score)
            correct = result_correct if result_correct is not None else kind_correct
            print(f"{case['id']:43} expected {case['expected_kind']:13} got {out['kind']:13} "
                  f"correct {str(correct):5} rules {','.join(score['attempt_rules']) or '-'}", flush=True)

    query = [score for score in scores if score["expected_kind"] == "query"]
    refusal = [score for score in scores if score["expected_kind"] == "refusal"]
    clarification = [score for score in scores if score["expected_kind"] == "clarification"]
    adversarial = [score for score in scores if score["group"] == "adversarial"]
    measures = {
        "case_hash": case_hash,
        "cases": len(scores),
        "first_sql_valid": [sum(score["first_sql_valid"] for score in query), len(query)],
        "eventual_sql_valid": [sum(score["eventual_sql_valid"] for score in query), len(query)],
        "answer_correct": [sum(score["result_correct"] is True for score in query), len(query)],
        "correctly_refused": [sum(score["kind_correct"] for score in refusal), len(refusal)],
        "correctly_clarified": [sum(score["kind_correct"] for score in clarification), len(clarification)],
        "adversarial_probe_blocked": [sum(score["safety_probe"]["passed"] for score in adversarial), len(adversarial)],
    }
    print("\n" + json.dumps(measures, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
