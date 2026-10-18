# Explainer evaluation

How the explainer (`qwen3:4b`) did on 28 chosen region-days, run on 2026-10-18. The cases and what each should and should not say are in [eval/cases.yml](../eval/cases.yml). That file was written before the explainer was run on any case and was not changed after the results were seen. Its SHA-256 at run time was `a2c50c4dc8dd6c2fe39bc0dcde8366fe2ff014bcc54439ab64faa8cb2b59538c`.

> The explainer describes past data only. It is not energy market advice or financial advice.

This page holds two runs. **v1** is the first run, kept as it was. **v2** follows it: the same 28 cases after the pack, prompt and checks were changed, run on `qwen3:4b` and `qwen3:8b`. See [v2](#v2-comparison-facts-a-required-verdict-and-a-length-limit).

## Who labelled what

- **Automatic** (`eval/run_eval.py`, re-runnable): figure, time and citation checks; coverage of notable rules and required items; whether expected caveats appear; whether the answer says the evidence does not explain the move.
- **By hand** (`eval/labels.csv`): unsupported causes, outside knowledge, factual errors, whether the move was reported against its comparisons, and the main omissions.

**The hand labels are self-assigned.** They were written by the same Claude session that built the explainer and wrote the cases, so they are not an independent review and may be biased toward the design. The `owner_check` and `owner_notes` columns in `labels.csv`, and the section at the end of this page, are for an independent spot-check.

## Results

| Group | Cases | Clean sentences | Numbers not in pack | Right number, wrong or missing citation | Time problems | Unknown ids | Unsupported cause | Outside knowledge | Factual errors (cases) | Restraint | Said "not explained" | Notable rules covered | Caveats carried | Required items cited |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| spike | 4 | 13/20 | 0 | 7 | 0 | 0 | 0 | 0 | 1 (1) | 4/4 | – | 12/12 | – | 13/13 |
| negative | 3 | 21/24 | 0 | 3 | 0 | 0 | 1 | 0 | 1 (1) | 2/3 | – | 5/5 | 3/3 | 8/8 |
| june_2022 | 5 | 14/19 | 0 | 5 | 2 | 2 | 0 | 0 | 1 (1) | 5/5 | 0/4 | 9/10 | 4/4 | 13/14 |
| tempt | 4 | 34/45 | 0 | 0 | 11 | 0 | 0 | 0 | 1 (1) | 4/4 | 0/4 | – | – | 1/2 |
| unrelated_event | 2 | 18/18 | 0 | 0 | 0 | 0 | 0 | 0 | 0 (0) | 2/2 | 0/2 | – | 0/1 | 0/1 |
| ordinary | 4 | 48/48 | 0 | 0 | 0 | 0 | 0 | 0 | 0 (0) | 4/4 | – | – | 0/1 | 0/2 |
| series_break | 3 | 32/32 | 0 | 0 | 0 | 0 | 0 | 0 | 1 (1) | 3/3 | – | – | 1/4 | 1/4 |
| odd_data | 2 | 13/14 | 0 | 1 | 0 | 0 | 1 | 0 | 1 (1) | 1/2 | – | 2/2 | 5/6 | 7/9 |
| event | 1 | 7/9 | 0 | 0 | 2 | 0 | 0 | 0 | 0 (0) | 1/1 | – | – | – | – |
| **all** | **28** | **200/229** | **0** | **16** | **15** | **2** | **2** | **0** | **6 (6)** | **26/28** | **0/10** | **28/29** | **13/19** | **43/53** |

What the columns mean:
- **Clean sentences:** sentences with no figure, time or citation problem.
- **Restraint:** no unsupported cause asserted.
- **Said "not explained":** applies only to cases where `cases.yml` says the answer should say so.
- **Caveats carried:** counts the caveats in `cases.yml` by their key words in the text.
- **Required items cited:** counts the pack's own required list by citation.
- **Speed:** answers took 13 to 62 seconds, 32 on average.

**On ceiling scores.** Two measures come close to 100%: numbers not in the pack (none in 28 answers) and notable rules covered (28 of 29). Those measure copying and citing, which constrained output handles well. They do not show the explainer is honest. The measures that test judgement are far from the ceiling:
- saying the evidence does not explain a move: 0 of 10;
- reporting a move against its comparisons: 1 of 28;
- carrying caveats: 13 of 19.

## What it gets right

- **No made-up figures.** No answer contains a number that is not in its pack. Every number the checker flagged turned out, on reading, to be in the pack: the model left out the fact id, or cited a neighbouring fact.
- **No outside knowledge.** No answer mentions weather, outages, bidding, the 2022 energy crisis, Christmas, the CPI release or any company.
- **No cause on the hard cases.** None of the five June 2022 days names the suspension or the cap as the cause. Three of the four days inside the suspension carry the $300 finding, and two carry it in full.

## Failures

1. **It never says the evidence does not explain a move: 0 of 10.** On all four temptation days, and both days with an unrelated event, it lists figures and stops. Restraint scores well here because the model does not notice anything to explain, not because it decides not to explain.
2. **It does not report the move.** On SA1 2024-02-12 the average was $118.69 against a 30-day median of $21.97. The answer runs to 19 sentences and never mentions the median or the previous day. The same happens on every temptation day. Only one answer in 28 (QLD1 2025-10-14) lists the comparisons, and even that one does not say what they show.
3. **Two unsupported claims:**
   - SA1 2025-12-25: "The deep negative price intervals were flagged due to binding links at Heywood and Murraylink." The causal-wording check flagged it.
   - SA1 2024-09-05: opens with "The market suspended for 16 intervals". The pack calls that an unchecked flag, though a later sentence in the same answer hedges it.
4. **Six factual errors that pass the figure check**, because each copies a real number and states it wrongly:
   - SA1 2024-07-04: repeats five times that $229.36 "was the lowest price of the day"; it was −$45.76.
   - SA1 2026-06-23: says the $845 interval was "the only interval with a price above the high-price threshold"; none was, as the threshold is $1,500.
   - SA1 2025-07-02: calls the largest drop the smallest.
   - SA1 2025-12-25: blurs 85 binding intervals with 85 deep-negative intervals.
   - NSW1 2022-06-13: says the cap was "active" in 9 intervals, which were intervals at the cap.
   - SA1 2024-09-05: puts the day "within 7 days" of a transition it falls inside.
5. **Omissions:**
   - **Required items:** 10 of 53 not cited. The battery series break is missed on 2 of 3 days, the rooftop caveat on 5 days where it was required, and the 174 APC-set intervals on NSW1 2022-06-13.
   - **Main facts left out:** QLD1 2026-01-15 gives no price at all. NSW1 2021-10-01 is one sentence. TAS1 2022-06-18 never says that the APC flag was never set, the point of that case. NSW1 2022-06-24 does not say the price went above $300.
   - **Events never mentioned:** none of the five days with events mentions them, so it neither links nor reports them.
6. **Length and repetition.** It was asked for 5 to 9 sentences. Answers ranged from 1 to 22, and two fell into repetition loops (SA1 2024-07-04, SA1 2024-02-12).
7. **Ordinary days.** None of the four says plainly that nothing unusual happened. Each lists figures.

## Fallback model

`qwen3:8b` was meant to run the same 28 cases. It completed one case, then the Ollama server closed the connection. The run was stopped to keep the laptop's load down and has not been repeated, so there is no comparison yet, and the decision on whether to keep the fallback is still open.

## Owner spot-checks

Pick a sample of cases, read the answer in `eval/results/qwen3_4b.jsonl` against its pack, and record agreement or disagreement with the labels in the `owner_check` and `owner_notes` columns of `eval/labels.csv`. Summarise here:

| Date checked | Cases checked | Agree with labels | Disagreements |
|---|---|---|---|
| | | | |

## v2: comparison facts, a required verdict and a length limit

Run on 2026-10-18 on the same 28 cases. `eval/cases.yml` was not changed: its SHA-256 is still `a2c50c4dc8dd6c2fe39bc0dcde8366fe2ff014bcc54439ab64faa8cb2b59538c`. Both models ran one case at a time with a 60-second pause between cases.

### What changed and why

v1 showed that the model described days without judging them. It never said whether the evidence explained a move (0 of 10) and almost never set the day against its comparisons (1 of 28). The v1 pack gave it no way to do either without arithmetic, and the prompt forbids arithmetic. Answers also ran from 1 to 22 sentences, with two repetition loops. So v2 changed the system, not the cases:

- **Comparison facts.** The pack now computes the average price, highest price and peak demand against the 30-day median and the previous day, as a difference and as a ratio. A ratio is given only when both values are positive.
- **Required items.** All six comparisons, plus a verdict sentence that must say, with the word "explain", whether the facts explain the day's price movement.
- **Length.** The output schema allows 4 to 10 sentences, output is capped at 2,000 tokens, and the checks fail an answer that repeats a sentence or falls outside the range.

### Results

**qwen3:4b**

| Group | Cases | Clean sentences | Numbers not in pack | Right number, wrong or missing citation | Time problems | Unknown ids | Unsupported cause | Outside knowledge | Factual errors (cases) | Restraint | Said "not explained" | Verdict sentence | Reported move vs comparisons | Comparisons cited | Notable rules covered | Caveats carried | Required items cited | Length 4–10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| spike | 4 | 24/31 | 0 | 11 | 0 | 0 | 0 | 0 | 0 (0) | 4/4 | – | 4/4 | 4/4 | 23/24 | 12/12 | – | 40/41 | 4/4 |
| negative | 3 | 19/26 | 0 | 7 | 0 | 0 | 0 | 0 | 1 (1) | 3/3 | – | 2/3 | 3/3 | 18/18 | 5/5 | 1/3 | 26/29 | 3/3 |
| june_2022 | 5 | 30/39 | 0 | 10 | 0 | 0 | 0 | 0 | 1 (1) | 5/5 | 4/4 | 5/5 | 5/5 | 30/30 | 10/10 | 4/4 | 49/49 | 5/5 |
| tempt | 4 | 17/24 | 0 | 7 | 0 | 0 | 0 | 0 | 0 (0) | 4/4 | 4/4 | 4/4 | 4/4 | 24/24 | – | – | 29/30 | 4/4 |
| unrelated_event | 2 | 10/14 | 0 | 7 | 0 | 0 | 0 | 0 | 1 (1) | 2/2 | 2/2 | 2/2 | 2/2 | 12/12 | – | 0/1 | 14/15 | 2/2 |
| ordinary | 4 | 24/27 | 0 | 3 | 0 | 0 | 1 | 0 | 1 (1) | 3/4 | – | 4/4 | 4/4 | 24/24 | – | 0/1 | 29/30 | 4/4 |
| series_break | 3 | 16/19 | 0 | 3 | 0 | 0 | 0 | 0 | 0 (0) | 3/3 | – | 3/3 | 3/3 | 18/18 | – | 2/4 | 23/25 | 3/3 |
| odd_data | 2 | 13/17 | 0 | 7 | 0 | 0 | 0 | 0 | 1 (1) | 2/2 | – | 2/2 | 2/2 | 12/12 | 2/2 | 3/6 | 19/23 | 2/2 |
| event | 1 | 6/6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 (0) | 1/1 | – | 1/1 | 1/1 | 6/6 | – | – | 7/7 | 1/1 |
| **all** | **28** | **159/203** | **0** | **55** | **0** | **0** | **1** | **0** | **5 (5)** | **27/28** | **10/10** | **27/28** | **28/28** | **167/168** | **29/29** | **10/19** | **236/249** | **28/28** |

Mean 36.9 seconds an answer.

**qwen3:8b**

| Group | Cases | Clean sentences | Numbers not in pack | Right number, wrong or missing citation | Time problems | Unknown ids | Unsupported cause | Outside knowledge | Factual errors (cases) | Restraint | Said "not explained" | Verdict sentence | Reported move vs comparisons | Comparisons cited | Notable rules covered | Caveats carried | Required items cited | Length 4–10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| spike | 4 | 19/39 | 0 | 27 | 0 | 1 | 0 | 0 | 2 (1) | 4/4 | – | 3/4 | 4/4 | 24/24 | 12/12 | – | 40/41 | 4/4 |
| negative | 3 | 9/28 | 0 | 18 | 2 | 0 | 0 | 0 | 1 (1) | 3/3 | – | 2/3 | 3/3 | 18/18 | 5/5 | 3/3 | 28/29 | 3/3 |
| june_2022 | 5 | 13/50 | 0 | 39 | 3 | 4 | 0 | 0 | 0 (0) | 5/5 | 3/4 | 3/5 | 5/5 | 29/30 | 9/10 | 4/4 | 44/49 | 5/5 |
| tempt | 4 | 5/27 | 0 | 37 | 0 | 0 | 0 | 1 | 0 (0) | 4/4 | 4/4 | 4/4 | 4/4 | 24/24 | – | – | 30/30 | 4/4 |
| unrelated_event | 2 | 9/18 | 0 | 8 | 0 | 1 | 0 | 0 | 0 (0) | 2/2 | 1/2 | 1/2 | 2/2 | 11/12 | – | 1/1 | 13/15 | 2/2 |
| ordinary | 4 | 17/33 | 0 | 16 | 0 | 0 | 0 | 1 | 0 (0) | 4/4 | – | 3/4 | 4/4 | 23/24 | – | 1/1 | 28/30 | 4/4 |
| series_break | 3 | 7/22 | 0 | 25 | 0 | 1 | 0 | 0 | 1 (1) | 3/3 | – | 3/3 | 3/3 | 18/18 | – | 4/4 | 25/25 | 3/3 |
| odd_data | 2 | 7/20 | 0 | 14 | 0 | 1 | 0 | 0 | 1 (1) | 2/2 | – | 0/2 | 2/2 | 11/12 | 2/2 | 5/6 | 18/23 | 2/2 |
| event | 1 | 4/7 | 0 | 9 | 0 | 0 | 0 | 0 | 0 (0) | 1/1 | – | 1/1 | 1/1 | 6/6 | – | – | 7/7 | 1/1 |
| **all** | **28** | **90/244** | **0** | **193** | **5** | **8** | **0** | **2** | **5 (4)** | **28/28** | **8/10** | **20/28** | **28/28** | **164/168** | **28/29** | **18/19** | **233/249** | **28/28** |

Mean 60.6 seconds an answer. Hand labels for both models are in `eval/labels_v2.csv`, self-assigned by the same session, like v1.

### v1 against v2, qwen3:4b

| Measure | v1 | v2 |
|---|---:|---:|
| Said "not explained" where expected | 0/10 | 10/10 |
| Reported the move against comparisons | 1/28 | 28/28 |
| Length within 4 to 10 sentences | 18/28 | 28/28 |
| Repetition loops | 2 | 0 |
| Factual errors (cases) | 6 (6) | 5 (5) |
| Unsupported causes | 2 | 1 |
| Caveats carried | 13/19 | 10/19 |
| Right number, wrong or missing citation | 16 | 55 |
| Notable rules covered | 28/29 | 29/29 |

### What the before-and-after shows

- **The judgement measures moved because the system now requires them, not because the model judges better.** Every v2 verdict from `qwen3:4b` is close to a template ("The facts do not explain the day's price movement because they record no causes"). It says this on spike days and ordinary days alike. Only 3 of 28 answers (NSW1 2022-06-13, TAS1 2025-11-03, VIC1 2026-01-07) go further and say the day was unusual and why the comparisons show it. The verdict is honest, since the pack holds no causes, but it is not evidence of judgement.
- **That puts several measures at the ceiling.** Said "not explained", reported the move, length, comparisons cited and notable rules covered are all at or within one of 100%. That is what the required-items check forces, so for these measures the question set is now too easy. A harder test would ask whether the model can say which days are unusual without being told to compare. The 4B model got that wrong on TAS1 2026-04-18, calling a day at 1.03 times its median "unusual".
- **Caveats got worse** (13/19 to 10/19). With ten sentences, six comparisons and a verdict, the rooftop caveat is what gets dropped: `qwen3:4b` carried it in 1 of the 7 cases that needed it, against 7 of 7 for `qwen3:8b`. One miss is the scorer's, not the model's: on SA1 2024-09-05 the 4B wrote "has not been verified against AEMO market notices", which the key-word pattern for the unverified-suspension caveat does not match. Read by hand, the 4B carried 11 of 19. The pattern was left as it is so v1 and v2 are scored the same way.
- **Citation slips rose** (16 to 55). The new comparison sentences quote the baseline value ("the previous day's 49.64 $/MWh") without citing the baseline fact. The numbers are right; the citations are incomplete.
- **New errors come from the new facts.**
  - NSW1 2022-06-18 quotes the previous-day gap as the median gap.
  - SA1 2024-09-05 says "$26.96 lower" for a rise.
  - VIC1 2026-01-07 invents "a 30-day median of 259" negative-price intervals.

### qwen3:4b against qwen3:8b

| | qwen3:4b | qwen3:8b |
|---|---|---|
| Unsupported causes | 1 (VIC1 2023-08-25 explains a low price by the rooftop gap) | 0 |
| Outside knowledge | 0 | 2 (adds that the rooftop gap matters "particularly in periods with negative prices") |
| Factual errors | 5, in 5 cases | 5, in 4 cases |
| Verdict sentence | 27/28 | 20/28 |
| Caveats carried | 10/19 | 18/19 |
| Citation slips | 55 | 193 |
| The hard June case (TAS1 2022-06-18) | finding and verdict carried | all ten sentences spent on comparisons; no suspension, finding or verdict |
| Seconds per answer | 37 | 61 |

Neither model is better overall; each fails in a different way, and both are kept.

- **`qwen3:4b`** gives the verdict more often, cites more cleanly, carries the June finding on all four suspension days and takes about 37 seconds. It drops caveats, above all the rooftop-solar caveat, and made the one unsupported cause in v2, which the wording check did not catch.
- **`qwen3:8b`** carries caveats almost every time, made no unsupported cause, and takes about 61 seconds. It cites sloppily, adds a little rooftop-solar commentary from outside the pack, skips the verdict on 8 days and failed the hardest June case outright.

The CLI defaults to `qwen3:4b` because it is smaller and faster, not because it did better; `--model qwen3:8b` runs the other.

### v2 owner spot-checks

Record agreement or disagreement with `eval/labels_v2.csv` in its `owner_check` and `owner_notes` columns, and summarise here:

| Date checked | Model | Cases checked | Agree with labels | Disagreements |
|---|---|---|---|---|
| | | | | |

## Conclusion

**Requiring a behaviour in the checks produced its form, not its substance.**

v1 showed a model that described days without judging them. v2 made the missing behaviours required items: compare the day with its baselines, say whether the facts explain the move, keep to 4 to 10 sentences. Every required behaviour then appeared:

- said "not explained" where expected: 0 of 10 in v1, 10 of 10 in v2;
- reported the move against its comparisons: 1 of 28, then 28 of 28;
- length within range: 18 of 28, then 28 of 28.

Reading the answers shows what those numbers hide:

- **The verdicts are a template.** Almost every v2 verdict from `qwen3:4b` is the same sentence: the facts do not explain the movement because they record no causes. It is true of every pack by construction, so it says nothing about the day. Only 3 of 28 answers argue anything: that the day was unusual, and which comparisons show it.
- **Judgement is still wrong when it appears.** TAS1 on 2026-04-18, with an average price 1.03 times its 30-day median, was called unusual.
- **The rest got worse.** Citation slips tripled (16 to 55), and caveats carried fell from 13 of 19 to 10 of 19 (11 read by hand), because six required comparisons and a verdict crowd out the rooftop-solar caveat.

**The jump from 0 of 10 to 10 of 10 is a metric artefact.** It measures that a required sentence is present, not that the model decided anything. Any check that rewards the presence of a phrase can be met by the phrase.

**What this project shows: a small local model can be made reliably grounded, but not reliably discerning.**

- **Grounded:** across 84 answers (v1, and v2 on both models), no number appears that is not in the pack. Unsupported causes appeared in 3 answers (2 in v1, 1 in v2), and outside knowledge only twice, as a clause of commentary on the rooftop caveat. On none of the June 2022 days did either model name the suspension or the price cap as the cause.
- **Not error-free:** about 5 answers in 28 still state a real pack number wrongly. A higher figure is called lower, a previous-day gap is given as the median gap, a figure is attached to the wrong quantity. The figure check cannot see these, because the number itself is right.
- **Not discerning:** neither model reliably tells an unusual day from an ordinary one, decides on its own which facts matter, or explains why a day stands out. Where the system demands those things, it gets their wording.

For this explainer that means the output can be trusted not to invent figures. It rarely invents causes, in 3 answers of 84, and the wording check caught only one of them. It cannot be trusted to judge what the figures mean. A reader still has to.
