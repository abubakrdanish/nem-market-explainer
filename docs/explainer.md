# Explainer

Given a NEM region and market date, the explainer builds an evidence pack from the marts and has a local model describe the day using only that pack. It then checks the answer against the pack and prints the failures next to it.

> Describes past data only. Not energy market advice or financial advice.

```
python -m explainer NSW1 2022-06-18                   # explanation and check report
python -m explainer VIC1 2025-06-12 --interval 19:55  # adds one interval's detail
python -m explainer VIC1 2025-06-12 --pack-only       # the evidence pack as JSON; no model call
python -m explainer SA1 2026-06-24 --json             # pack, answer and checks as JSON
python -m explainer SA1 2026-06-24 --model qwen3:8b
```

Needs Ollama running locally with `qwen3:4b` pulled (`ollama pull qwen3:4b`, about 2.5 GB). `qwen3:8b` (about 5.2 GB) also works with `--model qwen3:8b`. The 4B is the default because it is smaller and faster; the two fail differently, and neither did better overall (see [evaluation.md](evaluation.md)). No API keys, no network beyond `localhost`. The command exits 1 when the answer fails a check.

## How it works

1. **Pack.** `explainer/pack.py` opens the warehouse read-only and runs a fixed set of named queries against the marts. Each result becomes a fact with an `id`, a `label`, a `value`, a `unit` and a `source` (mart and column). The SQL is stored in the pack, so every figure can be re-derived. A pack holds:
   - the day's average, highest and lowest price, peak and minimum demand, and counts of negative-price and high-price intervals;
   - the previous day, the same weekday a week earlier, and 30-day medians, for comparison;
   - computed comparisons for the average price, highest price and peak demand: the difference from, and ratio to, the previous day and the 30-day median. A ratio is given only when both values are positive, because a ratio against a negative or zero baseline misleads;
   - six 4-hour blocks of price, demand, available generation and net interchange;
   - three moments: the highest-price, peak-demand and lowest-price intervals, each with demand, available generation, net interchange and the interconnectors at a limit;
   - every notable-interval rule that fired, with counts, times, extremes and thresholds;
   - flags: suspension, administered price cap, at cap or floor, intervention runs, missing SCADA;
   - generation shares by fuel, with the rooftop-solar caveat as a fact in the same pack;
   - interconnector flows into and out of the region, and intervals at a limit;
   - events from `mart_events`, series breaks within 7 days, the June 2022 finding inside 15–24 June 2022, and a short glossary.

   The pack also lists what the answer must cover: every notable rule that fired, the six comparisons, the caveats that apply, and a verdict sentence saying whether the facts explain the day's price movement.
2. **Prompt.** `explainer/prompt.py` sends the model the facts and the required items, and nothing else. The instructions are to cite fact ids in every sentence, copy numbers exactly, assign no causes, compare the day with the previous day and the 30-day median, say whether the facts explain the price movement, and say so when nothing unusual happened.
3. **Model.** `explainer/ollama.py` calls `qwen3:4b` through Ollama's local API, with thinking off, temperature 0, a fixed seed and output constrained to JSON: 4 to 10 sentences, each with fact ids. Output is capped at 2,000 tokens so a repetition loop cannot run on; a cut-off answer fails the checks.
4. **Checks.** `explainer/checks.py` tests each answer:
   - every number in a sentence matches a fact that sentence cites, at the precision quoted;
   - every HH:MM time appears in a cited fact;
   - every cited id exists;
   - every required item is cited, and caveats and the verdict keep their key words;
   - the answer has 4 to 10 sentences and repeats none.

   Sentences with causal wording ("because", "driven by") or outside-world terms ("heatwave", "outage") are flagged for a person to read. They are not scored as wrong automatically.

## What it cannot do

- **Say why a price moved.** The marts hold prices, demand, supply, flows and flags, not bids, outages, weather or constraint equations. The explainer can say what happened at the same time; it is told not to assign causes, and the checks flag causal wording.
- **Show rooftop solar.** Demand is operational demand and generation is SCADA, so rooftop solar is missing from both. Solar's share is understated, and the pack carries that caveat.
- **Confirm suspensions other than June 2022.** Other periods are flags in the data that have not been checked against AEMO notices.
- **Tell you which constraint bound.** "At a limit" means some constraint involving the link bound; the binding constraint IDs are not loaded.
- **Answer anything outside one region and date.** There is no free-form question answering. Chatting with the warehouse is a later stage.

## Limitations of the checks

- **Wrong words around right numbers.** A sentence can cite the right fact and copy its number exactly while describing it wrongly, for example calling an hourly average the peak. The figure check passes that; only a reader catches it.
- **Comparisons.** Statements such as "the highest of the day" or "much higher than" carry no number, so they are not checked.
- **Lexicon flags.** The causal and outside-world word lists flag sentences for review. They miss causal claims phrased other ways and flag harmless uses, such as "no cause is shown".
- **Completeness is checked by citation.** A required item counts as covered when a sentence cites it, and for caveats also contains its key words. A sentence can cite a fact and still state it badly.
- **Rounding.** A rounded figure counts as matching when the fact rounds to it at the precision quoted, so "$1,786" matches 1786.27. A different number that happens to round the same way would also pass.

How well it does on 28 chosen days, with its failures, is in [evaluation.md](evaluation.md).
