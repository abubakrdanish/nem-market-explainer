# NEM Market Explainer

Why did the wholesale electricity price move in a given region and interval?

This project collects the data needed to answer that from the National Electricity Market (NEM): 5-minute prices, demand, interconnector flows and the output of every generating unit, plus unit registration and fuel types, the RBA cash rate and exchange rate, and a calendar of market events. Raw files are saved unchanged and loaded into DuckDB. Later stages will model the data with dbt and add an explainer that answers only from the data.

> Personal portfolio project. It describes what happened in past data. It is not energy market advice or financial advice.

## Status

Step 2 is done: AEMO ingestion, the raw layer and tests. dbt models and the explainer are not built yet.

## Data

| Data | Source | Window |
|---|---|---|
| Dispatch and trading prices, regional demand, interconnectors | AEMO monthly archive (MMSDM) | July 2021 to the newest published month |
| Unit output (SCADA), unit registration, fuel types, price cap and floor | AEMO monthly archive (MMSDM) | same |
| Cash rate target and decisions | RBA tables F1 and A2 | from 1990 |
| AUD/USD and trade-weighted index | RBA table F11 | from 2014 |
| Market events, generator closures, RBA meetings, ABS releases | `data/events.csv`, edited by hand | 2021 to 2027 |

[docs/data_sources.md](docs/data_sources.md) covers each source's terms, table layout and known quirks. [docs/data_dictionary.md](docs/data_dictionary.md) explains columns that are easy to misread, such as the price suspension flags.

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
```

The first run downloads about 2 GB from NEMWEB, one file every few seconds, and takes about half an hour. Later runs fetch only months not yet saved. `python -m ingestion.run --offline` skips downloads and loads what is already on disk. Running either again adds nothing.

## Layout

```
config/       source settings and the AEMO window
data/         events.csv (committed); raw/ (gitignored)
docs/         data sources, terms and data dictionary
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
