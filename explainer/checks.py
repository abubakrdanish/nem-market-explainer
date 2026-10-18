"""Checks run on the model's answer after generation. Nothing the model says is trusted until it passes these.

- figures: every number in a sentence matches a fact the sentence cites, at the precision quoted
- times: every HH:MM in a sentence appears in a fact it cites
- citations: every cited id exists in the pack
- completeness: every required item is cited, and caveats keep their key words
- wording: sentences that state a cause or use outside-world terms are flagged for review, not judged
- length: 4 to 10 sentences, none repeated
"""
from __future__ import annotations

import re

from explainer.prompt import MAX_SENTENCES, MIN_SENTENCES

NUMBER = re.compile(r"(?<![\w.:/-])(-?\$?-?\d[\d,]*(?:\.\d+)?)(?![\d:]|-\d\d-)")
TIME = re.compile(r"(?<!\d)((?:[01]?\d|2[0-4]):[0-5]\d)(?!\d)")
ISO_DATE = re.compile(r"\d{4}-\d\d-\d\d")
CAUSAL = re.compile(r"\b(because|due to|caus\w*|driven by|drove|drive[sn]?|led to|leading to|as a result|result\w* in|"
                    r"owing to|attribut\w*|triggered|pushed|forced|thanks to|reflect\w*|so that|therefore|hence)\b", re.I)
OUTSIDE = re.compile(r"\b(weather|heat ?wave|cold|winter|summer|storm|rain\w*|outage\w*|shortage\w*|crisis|gas supply|"
                     r"coal supply|bid\w*|withdr\w*|maintenance|tripp?\w*|failure\w*|holiday|christmas|inflation|"
                     r"consumer price|strategic|rebid\w*|fuel cost\w*)\b", re.I)
UNEXPLAINED = re.compile(r"(do(es)? not|doesn't|don't|cannot|can't) (explain|show (why|what)|say (why|what)|identify)|"
                         r"not explained|no (fact|evidence|data) (explains|shows why)|unexplained|without an? (clear )?"
                         r"(explanation|cause)", re.I)


def _numbers_in(value) -> list[float]:
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    text = ISO_DATE.sub(lambda m: " ".join(str(int(x)) for x in m.group(0).split("-")), str(value))
    return [float(x.replace(",", "").replace("$", "")) for x in NUMBER.findall(text)]


def _matches(value: float, decimals: int, candidates: list[float]) -> bool:
    return any(round(c, decimals) == value or round(-c, decimals) == value for c in candidates)


def _date_numbers(pack: dict) -> set[float]:
    found = set()
    for text in [pack["market_date"]] + [str(f["value"]) for f in pack["facts"] if f["unit"] == "date"]:
        found |= {float(x) for x in text.split("-")}
    return found


def check(answer: dict, pack: dict) -> dict:
    facts = {f["id"]: f for f in pack["facts"]}
    every_value = [n for f in pack["facts"] for n in _numbers_in(f["value"])]
    dates = _date_numbers(pack)
    problems, flagged = [], []
    for i, sentence in enumerate(answer["sentences"]):
        text, cited_ids = sentence["text"], sentence["fact_ids"]
        unknown = [c for c in cited_ids if c not in facts]
        for c in unknown:
            problems.append({"sentence": i, "kind": "unknown_fact_id", "value": c})
        cited = [facts[c] for c in cited_ids if c in facts]
        cited_values = [n for f in cited for n in _numbers_in(f["value"])]
        cited_text = " ".join(f"{f['label']} {f['value']}" for f in cited)
        label_numbers = [n for f in cited for n in _numbers_in(f["label"])]

        for t in TIME.findall(text):
            if t not in cited_text:
                kind = "time_not_in_cited_facts" if t in " ".join(str(f["value"]) for f in pack["facts"]) else "time_not_in_pack"
                problems.append({"sentence": i, "kind": kind, "value": t})
        bare = TIME.sub(" ", ISO_DATE.sub(" ", text))
        for raw in NUMBER.findall(bare):
            number = raw.replace("$", "").replace(",", "")
            value = float(number)
            decimals = len(number.split(".")[1]) if "." in number else 0
            if _matches(value, decimals, cited_values) or value in label_numbers:
                continue
            if decimals == 0 and value in dates:
                continue
            kind = "number_not_in_cited_facts" if _matches(value, decimals, every_value) else "number_not_in_pack"
            problems.append({"sentence": i, "kind": kind, "value": raw})

        reasons = []
        if CAUSAL.search(text):
            reasons.append("causal wording: " + CAUSAL.search(text).group(0))
        for term in sorted({m.group(0).lower() for m in OUTSIDE.finditer(text)}):
            if term not in cited_text.lower():
                reasons.append("outside-world term: " + term)
        if reasons:
            flagged.append({"sentence": i, "reasons": reasons})

    missing = []
    for item in pack["required"]:
        prefix = item["id"] + "."
        citing = [s for s in answer["sentences"] if any(c == item["id"] or c.startswith(prefix) for c in s["fact_ids"])]
        if not citing:
            missing.append({"id": item["id"], "why": "not cited"})
        elif item["key_terms"] and not any(all(k in s["text"].lower() for k in item["key_terms"]) for s in citing):
            missing.append({"id": item["id"], "why": f"cited without the words {item['key_terms']}"})

    sentences = len(answer["sentences"])
    bad_sentences = len({p["sentence"] for p in problems})
    seen, repeated = set(), []
    for i, s in enumerate(answer["sentences"]):
        key = re.sub(r"\W+", " ", s["text"].lower()).strip()
        if key in seen:
            repeated.append(i)
        seen.add(key)
    length_ok = MIN_SENTENCES <= sentences <= MAX_SENTENCES
    return {
        "sentences": sentences,
        "sentences_with_figure_problems": bad_sentences,
        "problems": problems,
        "required": len(pack["required"]),
        "required_missing": missing,
        "flagged_wording": flagged,
        "says_unexplained": any(UNEXPLAINED.search(s["text"]) for s in answer["sentences"]),
        "length_ok": length_ok,
        "repeated_sentences": repeated,
        "invalid_output": "invalid_output" in answer,
        "passed": not problems and not missing and length_ok and not repeated and "invalid_output" not in answer,
    }


def render(answer: dict, report: dict) -> str:
    marks = {p["sentence"] for p in report["problems"]} | {f["sentence"] for f in report["flagged_wording"]}
    prose = " ".join(("[!] " if i in marks else "") + s["text"] for i, s in enumerate(answer["sentences"]))
    lines = [prose, "", f"Checks: {'passed' if report['passed'] else 'FAILED'}"]
    lines.append(f"  figures and times: {report['sentences'] - report['sentences_with_figure_problems']} of "
                 f"{report['sentences']} sentences match the facts they cite")
    for p in report["problems"]:
        lines.append(f"  sentence {p['sentence'] + 1}: {p['kind'].replace('_', ' ')}: {p['value']}")
    lines.append(f"  required items covered: {report['required'] - len(report['required_missing'])} of {report['required']}")
    for m in report["required_missing"]:
        lines.append(f"  missing: {m['id']} ({m['why']})")
    if report["invalid_output"]:
        lines.append("  the model's output was cut off or was not valid JSON")
    if not report["length_ok"]:
        lines.append(f"  length: {report['sentences']} sentences, outside {MIN_SENTENCES} to {MAX_SENTENCES}")
    for i in report["repeated_sentences"]:
        lines.append(f"  sentence {i + 1} repeats an earlier sentence")
    for f in report["flagged_wording"]:
        lines.append(f"  sentence {f['sentence'] + 1} flagged for review: {'; '.join(f['reasons'])}")
    return "\n".join(lines)
