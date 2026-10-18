"""The instructions and output schema sent to the model. The model sees the pack's facts and nothing else."""
from __future__ import annotations

SYSTEM = """You describe one day in one region of Australia's National Electricity Market, using ONLY the facts given.
Do not use any other knowledge: nothing about weather, generators, companies, history, policy or events that is not in the facts.

Rules:
- Each sentence lists, in "fact_ids", the ids of every fact it uses.
- Every number and time in a sentence is copied exactly from a fact it cites. Do not calculate or round new numbers.
- Do not say that one thing caused another. Facts that happened at the same time may be described as happening at the same time.
- Compare the day with the previous day and the 30-day median using the compare facts, and say whether the day was unusual.
- If nothing unusual happened, say so plainly.
- One sentence must say whether these facts explain the day's price movement, using the word "explain". The facts record no causes.
- Write a sentence for every item listed under REQUIRED, citing its id, and keep the wording of caveats and findings. One sentence may cover several items.
- Explain abbreviations only with the glossary facts.
- Write 4 to 10 sentences, each saying something new. Never repeat a sentence."""

MIN_SENTENCES, MAX_SENTENCES = 4, 10

SCHEMA = {
    "type": "object",
    "properties": {
        "sentences": {
            "type": "array",
            "minItems": MIN_SENTENCES,
            "maxItems": MAX_SENTENCES,
            "items": {
                "type": "object",
                "properties": {"text": {"type": "string"}, "fact_ids": {"type": "array", "items": {"type": "string"}}},
                "required": ["text", "fact_ids"],
            },
        }
    },
    "required": ["sentences"],
}


def fact_line(fact: dict) -> str:
    value = fact["value"]
    numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
    unit = f" {fact['unit']}" if numeric and fact["unit"] not in ("", "time", "date", "code") else ""
    return f"{fact['id']} | {fact['label']} | {value}{unit}"


def user_message(pack: dict) -> str:
    lines = [f"Region {pack['region']}, market date {pack['market_date']}. {pack['time_basis']}"]
    if pack["interval"]:
        lines.append(f"The question is about the interval ending {pack['interval']}.")
    lines.append("FACTS (id | meaning | value):")
    lines += [fact_line(f) for f in pack["facts"]]
    if pack["required"]:
        lines.append("REQUIRED (each needs a sentence citing it):")
        lines += [f"{r['id']} ({r['reason']})" for r in pack["required"]]
    return "\n".join(lines)
