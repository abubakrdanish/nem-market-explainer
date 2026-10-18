# NEM Market Explainer

Why did the wholesale electricity price move in a given region and interval?

This project collects the data needed to answer that from the National Electricity Market (NEM): 5-minute prices, demand, interconnector flows and the output of every generating unit, plus unit registration and fuel types, the RBA cash rate and exchange rate, and a calendar of market events. Raw files are saved unchanged and loaded into DuckDB, and dbt models turn them into a few marts that answer "what happened in this region on this day". An explainer then describes a region and day using only facts drawn from the marts, through a small local model, and checks every figure it writes against those facts.

> Personal portfolio project. It describes what happened in past data. It is not energy market advice or financial advice.

## Status

Steps 2 to 4 are done: AEMO ingestion, the raw layer, the dbt models with their tests, and the grounded explainer with its evaluation.

**What the evaluation found.** A small local model can be made reliably grounded, but not reliably discerning:
- **Grounded:** across 84 answers on 28 chosen days, no answer used a number that is not in its evidence pack, only 3 stated a cause the pack does not hold, and none named the suspension or the price cap as the cause of June 2022 prices.
- **Not discerning:** it does not reliably tell an unusual day from an ordinary one, and about 5 answers in 28 still describe a real figure wrongly.
- **A metric artefact:** making the explainer say whether the evidence explains a move took that measure from 0 of 10 to 10 of 10. The sentences are a template, and only 3 of 28 answers argue anything. Requiring a behaviour in the checks produced its form, not its substance.

Details, failures and both models' trade-offs are in [docs/evaluation.md](docs/evaluation.md).

## Data

| Data | Source | Window |
|---|---|---|
| Dispatch and trading prices, regional demand, interconnectors | AEMO monthly archive (MMSDM) | July 2021 to the newest published month |
| Unit output (SCADA), unit registration, fuel types, price cap and floor | AEMO monthly archive (MMSDM) | same |
| Cash rate target and decisions | RBA tables F1 and A2 | from 1990 |
| AUD/USD and trade-weighted index | RBA table F11 | from 2014 |
| Market events, generator closures, RBA meetings, ABS releases | `data/events.csv`, edited by hand | 2021 to 2027 |

[docs/data_sources.md](docs/data_sources.md) covers each source's terms, table layout and known quirks. [docs/data_dictionary.md](docs/data_dictionary.md) describes the marts and the columns that are easy to misread. Read its first section before using them: demand is operational demand and SCADA leaves out rooftop solar, so solar's share is understated, and battery charging has a series break in the second half of 2024. [docs/findings.md](docs/findings.md) records what the marts show, with queries to re-run.

### AEMO licence

AEMO gives general permission to use "AEMO Material for any purpose, but only with accurate and appropriate attribution". Its definition of AEMO Material names documents, reports and sound and video recordings. It does not say whether market data files are covered. This project treats the data as licensed for personal, non-commercial use with attribution, and redistributes none of it: raw files and the warehouse are gitignored, and the test fixtures use made-up values.

Contains data from the Australian Energy Market Operator (AEMO), nemweb.com.au. AEMO is the author of the data and has not reviewed or endorsed this project. Source: RBA 2026. Source: Australian Bureau of Statistics. The RBA does not endorse this project.

## Run it

Needs Python 3.11 or newer. No accounts or API keys.

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock
pip install -e . --no-deps

python -m ingestion.init_duckdb   # creates warehouse/nem.duckdb with schemas raw, staging, marts
python -m ingestion.run           # downloads RBA tables and the AEMO archive, imports events, loads raw
python -m ingestion.quality       # data quality checks and freshness; exits 1 on a failure
python -m pytest                  # offline tests

cd dbt_project
cp profiles.yml.example profiles.yml
dbt build --profiles-dir .        # staging, intermediate and marts, plus their tests
cd ..

ollama pull qwen3:4b              # about 2.5 GB, runs locally
python -m explainer NSW1 2022-06-18
python -m warehouse_chat "What was the highest price in South Australia in 2025?"
```

The first run downloads about 2 GB from NEMWEB, one file every few seconds, and takes about half an hour. Later runs fetch only months not yet saved. `python -m ingestion.run --offline` skips downloads and loads what is already on disk. Running either again adds nothing.

`dbt build` takes about 20 seconds: about 13 seconds of models (8 of them aggregating the 251 million SCADA rows) and the rest tests. It writes the `staging`, `intermediate`, `marts` and `reference` schemas into the same DuckDB file and only reads `raw`. The models use about 0.8 GB, and DuckDB keeps about 0.9 GB of free space in the file for rebuilds, so the file settles at about 3.6 GB. DuckDB allows one writer, so do not run `ingestion.quality` during a build.

The explainer reads the warehouse read-only and calls Ollama on `localhost`; an answer took 13 to 62 seconds with `qwen3:4b` in the evaluation, 32 on average. Every answer ends with the disclaimer that it is not energy market advice or financial advice. [docs/explainer.md](docs/explainer.md) says how it works and what it cannot do, and [docs/evaluation.md](docs/evaluation.md) reports how it did on 28 chosen days, failures included.

The warehouse chat tool turns a question into SQL, validates it, then runs it through a separate read-only DuckDB connection. It always prints the SQL or says that no query ran. Queries can use only the documented marts and two reference dimensions, return at most 200 rows and run for at most 10 seconds. It retries a failed model query no more than twice. It uses only local Ollama and needs no account or API key. Its output describes past data only. It is not energy market advice and not financial advice. [docs/chat.md](docs/chat.md) lists the safety rules, evaluation results and failures.

## Layout

```
config/       source settings and the AEMO window
dbt_project/  dbt models (staging, intermediate, marts), seeds, macros and tests
data/         events.csv (committed); raw/ (gitignored)
docs/         data sources, terms, data dictionary, findings, explainer and evaluation
eval/         explainer evaluation cases, labels and runner; results/ (gitignored)
explainer/    evidence pack, prompt, local model call, checks and CLI
warehouse_chat/ natural-language question, SQL validation, read-only runner and CLI
ingestion/    download, raw files, loading, quality checks
tests/        offline tests and small synthetic fixtures
warehouse/    DuckDB file (gitignored)
```

## How loading works

- Each download is saved under `data/raw/` unchanged. RBA files are date-stamped and skipped if their bytes match an earlier copy. AEMO archive months are final, so each table-month is fetched once.
- Each raw file is loaded into its `raw.*` table in one transaction, tagged with `_source_file` and `_loaded_at`. A file already in the table is not loaded again.
- AEMO files are read with DuckDB's CSV reader, which loads a month of unit SCADA (about 4.4 million rows) in about a second. A file whose record count does not match its closing count is rejected.
- Raw tables keep every snapshot. Picking the latest one is left to the staging models.
- AEMO timestamps are NEM market time (AEST, UTC+10 all year) and mark the end of each interval.

## Updating dependencies

`requirements.txt` lists direct dependencies. `requirements.lock` pins everything:

```
pip install pip-tools
pip-compile --output-file=requirements.lock --strip-extras requirements.txt
```
