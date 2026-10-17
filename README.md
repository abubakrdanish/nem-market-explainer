# ASX Market Explainer

What moved the Australian share market on a given day, and what else happened that day?

This project collects the data needed to answer that: the S&P/ASX 200 index and 30 large ASX stocks, the RBA cash rate, the Australian dollar, and a calendar of RBA decisions and ABS releases. Raw files are saved unchanged and loaded into DuckDB. Later stages will model the data with dbt and add an explainer that answers only from the data.

> Personal portfolio project. It describes what happened in past data and is not financial advice. Nothing here recommends buying or selling anything.

## Status

Day 1 is done: sources, ingestion, the raw layer and tests. dbt models and the explainer are not built yet.

## Data

| Data | Source | How it arrives |
|---|---|---|
| S&P/ASX 200 and 30 stocks, daily | you, as CSV files in `data/inbox/` | by hand, see below |
| Cash rate target and decisions | RBA tables F1 and A2 | downloaded |
| AUD/USD and trade-weighted index | RBA table F11 | downloaded |
| ASX trading days | `exchange_calendars` (XASX) | library |
| RBA meetings, ABS releases | `data/events.csv` | edited by hand |

[docs/data_sources.md](docs/data_sources.md) covers each source's terms, attribution and known quirks, and why prices are not downloaded.

Source: RBA 2026. Source: Australian Bureau of Statistics. The RBA does not endorse this project.

## Run it

Needs Python 3.11 or newer. No accounts or API keys.

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.lock
pip install -e . --no-deps

python -m ingestion.init_duckdb   # creates warehouse/asx.duckdb with schemas raw, staging, marts
python -m ingestion.run           # downloads RBA tables, imports inbox and events, loads raw
python -m ingestion.quality       # data quality checks and freshness; exits 1 on a failure
python -m pytest                  # offline tests
```

`python -m ingestion.run --offline` skips downloads and loads what is already on disk. Running it again adds nothing: unchanged downloads are not saved again, and files already loaded are skipped.

To try it without real prices, copy the made-up sample into the inbox:

```
cp tests/fixtures/FAKE_synthetic_prices.csv data/inbox/
```

### Adding prices

Save one or more CSV files in `data/inbox/` with the columns `ticker,date,open,high,low,close,adj_close,volume`. The column contract is in [docs/data_sources.md](docs/data_sources.md#asx-prices-supplied-by-hand). Use files from a provider whose terms allow your use. The inbox, raw files and warehouse are gitignored and must not be committed.

To add a ticker, add a line to `config/tickers.yml`.

## Layout

```
config/       tickers and source settings
data/         events.csv (committed); inbox/ and raw/ (gitignored)
docs/         data sources and terms
ingestion/    download, raw files, loading, quality checks
tests/        offline tests and small fixtures
warehouse/    DuckDB file (gitignored)
```

## How loading works

- Each download or inbox file is saved under `data/raw/` as `<dataset>_<YYYYMMDD>.<ext>`. A file is skipped if its bytes match an earlier one.
- Each raw file is loaded into its `raw.*` table in one transaction, tagged with `_source_file` and `_loaded_at`. A file name already in the table is not loaded again.
- Raw tables keep every snapshot. Picking the latest one is left to the staging models.
- Dates are plain Sydney calendar dates.

## Updating dependencies

`requirements.txt` lists direct dependencies. `requirements.lock` pins everything:

```
pip install pip-tools
pip-compile --output-file=requirements.lock --strip-extras requirements.txt
```
