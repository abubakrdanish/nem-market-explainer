"""Run the explainer on every case in eval/cases.yml and score the answers automatically.

    python -m eval.run_eval --model qwen3:4b --version v2 --pause 60

Writes eval/results/<version>/<model>.jsonl (gitignored: answers are full of AEMO figures) and prints a table per case.
Unsupported claims and factual errors also need a human read; those labels live in eval/labels.csv.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import yaml

from explainer import ollama
from explainer.checks import check
from explainer.pack import build_pack, connect

HERE = Path(__file__).parent
# How each caveat in cases.yml shows up in an answer.
CAVEAT_TERMS = {
    "rooftop_solar": r"rooftop",
    "june_2022_finding": r"\$?300",
    "series_break": r"battery|settlement",
    "missing_scada": r"scada",
    "unverified_suspension": r"not (been )?checked|unverified|not confirmed|flag in the data|not a confirmed",
}


def score(case: dict, pack: dict, answer: dict, report: dict) -> dict:
    text = " ".join(s["text"] for s in answer["sentences"])
    missing = {m["id"] for m in report["required_missing"]}
    notable = [r["id"] for r in pack["required"] if r["id"].startswith("notable.")]
    compare = [r["id"] for r in pack["required"] if r["id"].startswith("compare.")]
    caveats = {c: bool(re.search(CAVEAT_TERMS[c], text, re.I)) for c in case["caveats"]}
    kinds = [p["kind"] for p in report["problems"]]
    return {
        "id": case["id"],
        "group": case["group"],
        "sentences": report["sentences"],
        "clean_sentences": report["sentences"] - report["sentences_with_figure_problems"],
        "numbers_not_in_pack": kinds.count("number_not_in_pack"),
        "misattributed": kinds.count("number_not_in_cited_facts"),
        "time_problems": kinds.count("time_not_in_pack") + kinds.count("time_not_in_cited_facts"),
        "unknown_ids": kinds.count("unknown_fact_id"),
        "notable_covered": len([n for n in notable if n not in missing]),
        "notable_total": len(notable),
        "compare_covered": len([c for c in compare if c not in missing]),
        "compare_total": len(compare),
        "verdict_required": any(r["id"] == "verdict" for r in pack["required"]),
        "verdict_given": any(r["id"] == "verdict" for r in pack["required"]) and "verdict" not in missing,
        "length_ok": report.get("length_ok", True),
        "repeated_sentences": len(report.get("repeated_sentences", [])),
        "invalid_output": report.get("invalid_output", False),
        "required_covered": report["required"] - len(missing),
        "required_total": report["required"],
        "caveats_carried": sum(caveats.values()),
        "caveats_expected": len(caveats),
        "caveats": caveats,
        "flagged_sentences": len(report["flagged_wording"]),
        "says_unexplained": report["says_unexplained"],
        "say_unexplained_expected": case["say_unexplained"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default=ollama.DEFAULT_MODEL)
    parser.add_argument("--only", nargs="*", help="case ids to run")
    parser.add_argument("--version", default="v2", help="results folder under eval/results")
    parser.add_argument("--pause", type=int, default=0, help="seconds to wait between cases, to keep the machine cool")
    args = parser.parse_args(argv)

    cases = yaml.safe_load((HERE / "cases.yml").read_text())["cases"]
    if args.only:
        cases = [c for c in cases if c["id"] in args.only]
    out_dir = HERE / "results" / args.version
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{args.model.replace(':', '_')}.jsonl"
    # Resume an interrupted run rather than starting again.
    done = {json.loads(line)["case"]["id"] for line in out.open()} if out.exists() else set()
    cases = [c for c in cases if c["id"] not in done]
    with connect() as con, out.open("a") as f:
        for n, case in enumerate(cases):
            if n and args.pause:
                time.sleep(args.pause)
            pack = build_pack(con, case["region"], case["date"])
            try:
                answer = ollama.chat(pack, args.model)
            except OSError:
                time.sleep(max(args.pause, 30))
                answer = ollama.chat(pack, args.model)
            report = check(answer, pack)
            s = score(case, pack, answer, report)
            f.write(json.dumps({"case": case, "pack": pack, "answer": answer, "checks": report, "score": s},
                               default=str) + "\n")
            f.flush()
            print(f"{s['id']:28} {answer['seconds']:5.0f}s  clean {s['clean_sentences']}/{s['sentences']}  "
                  f"not-in-pack {s['numbers_not_in_pack']}  misattr {s['misattributed']}  times {s['time_problems']}  "
                  f"notable {s['notable_covered']}/{s['notable_total']}  required {s['required_covered']}/"
                  f"{s['required_total']}  compare {s['compare_covered']}/{s['compare_total']}  "
                  f"verdict {s['verdict_given']}  length_ok {s['length_ok']}  repeats {s['repeated_sentences']}  caveats {s['caveats_carried']}/{s['caveats_expected']}  "
                  f"flagged {s['flagged_sentences']}  unexplained {s['says_unexplained']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
