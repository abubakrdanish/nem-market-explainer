"""Explain one region and market date from the marts, using a local model.

    python -m explainer NSW1 2022-06-18
    python -m explainer VIC1 2025-06-12 --interval 19:55
    python -m explainer VIC1 2025-06-12 --pack-only
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from explainer import DISCLAIMER, ollama
from explainer.checks import check, render
from explainer.pack import build_pack, connect
from ingestion.config import WAREHOUSE_PATH

REGIONS = ["NSW1", "QLD1", "SA1", "TAS1", "VIC1"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("region", choices=REGIONS)
    parser.add_argument("date", type=date.fromisoformat, help="market date, YYYY-MM-DD")
    parser.add_argument("--interval", help="interval end time, HH:MM, NEM market time")
    parser.add_argument("--pack-only", action="store_true", help="print the evidence pack as JSON and stop")
    parser.add_argument("--json", action="store_true", help="print pack, answer and checks as JSON")
    parser.add_argument("--model", default=ollama.DEFAULT_MODEL)
    parser.add_argument("--warehouse", type=Path, default=WAREHOUSE_PATH)
    args = parser.parse_args(argv)

    with connect(args.warehouse) as con:
        try:
            pack = build_pack(con, args.region, args.date, args.interval)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 2
    if args.pack_only:
        print(json.dumps(pack, indent=1))
        return 0

    answer = ollama.chat(pack, args.model)
    report = check(answer, pack)
    if args.json:
        print(json.dumps({"pack": pack, "answer": answer, "checks": report}, indent=1))
        return 0
    print(f"{args.region} {args.date}" + (f", interval ending {args.interval}" if args.interval else "")
          + f" ({answer['model']}, {answer['seconds']}s)\n")
    print(render(answer, report))
    print(f"\n{DISCLAIMER}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
