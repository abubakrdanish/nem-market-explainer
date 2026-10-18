from __future__ import annotations

import json

from warehouse_chat import DISCLAIMER
from warehouse_chat import __main__ as cli


def test_cli_always_prints_sql_results_and_disclaimer(monkeypatch, capsys):
    monkeypatch.setattr(cli, "answer", lambda *args, **kwargs: {
        "kind": "query", "message": "", "sql": "SELECT 1 AS answer",
        "result": {"columns": ["answer"], "rows": [(1,)], "row_count": 1,
                   "truncated": False, "seconds": 0},
        "caveats": [], "attempts": [], "model": "mock",
    })
    assert cli.main(["question"]) == 0
    output = capsys.readouterr().out
    assert "SQL:\nSELECT 1 AS answer" in output
    assert "answer" in output
    assert DISCLAIMER in output


def test_json_refusal_has_disclaimer_and_no_sql(monkeypatch, capsys):
    monkeypatch.setattr(cli, "answer", lambda *args, **kwargs: {
        "kind": "refusal", "message": "Not in the marts.", "sql": "", "caveats": [],
        "attempts": [], "model": "mock",
    })
    assert cli.main(["question", "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["sql"] == ""
    assert output["disclaimer"] == DISCLAIMER


def test_text_refusal_says_no_sql_ran(monkeypatch, capsys):
    monkeypatch.setattr(cli, "answer", lambda *args, **kwargs: {
        "kind": "refusal", "message": "Unsafe request.", "sql": "", "caveats": [],
        "attempts": [], "model": "mock",
    })
    assert cli.main(["question"]) == 0
    assert "SQL: none (no query was run)." in capsys.readouterr().out
