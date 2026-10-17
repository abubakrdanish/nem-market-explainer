# Data sources

Terms were last checked on 2026-10-17. Check them again before publishing anything built on this data.

All dates are plain calendar dates in Sydney time, with no timezone attached. ASX prices are dated by the trading session. RBA observations are dated as the RBA publishes them.

## RBA statistical tables

Publisher: Reserve Bank of Australia. Terms: https://www.rba.gov.au/copyright/

Statistical data is excluded from the RBA's CC BY 4.0 licence. Section 5 (Financial Data) and Section 4 (Cash Rate) instead allow use, reproduction and publication "for personal or commercial purposes", provided nothing implies RBA endorsement and the source is not misrepresented. Material the RBA sources from a third party needs that party's consent.

Attribution: "Source: RBA 2026".

The RBA's robots.txt does not restrict `/statistics/`. The pipeline downloads five files per run, with a 3 second gap between requests.

### F1 Interest Rates and Yields: Money Market

- URL: https://www.rba.gov.au/statistics/tables/csv/f1-data.csv
- Loaded into `raw.rba_f1`. The cash rate target is series `FIRMMCRTD`, in per cent, daily from 2011-01-04.
- Updated daily.
- Known limit: the change series `FIRMMCCRT` is not always filled in. On 2026-09-30 the target moved from 4.35 to 4.60 with no change value. Use the target level, or A2, to find changes.

### A2 Changes in Monetary Policy and Administered Rates

- URL: https://www.rba.gov.au/statistics/tables/csv/a2-data.csv
- Loaded into `raw.rba_a2`. One row per change from 1990. `ARBAMPCNCRT` is the new cash rate target and `ARBAMPCCCR` is the change.
- Dates are the day the change takes effect, which is the day after the announcement. The 3 February 2026 decision appears as 2026-02-04.
- Values are kept as text, because early rows are ranges such as "17.00 to 17.50".
- Updated when the rate changes. Meetings that leave the rate unchanged do not appear, so meeting dates come from the events file.

### F11 Exchange Rates

- URLs:
  - https://www.rba.gov.au/statistics/tables/xls-hist/2014-2017.xls
  - https://www.rba.gov.au/statistics/tables/xls-hist/2018-2022.xls
  - https://www.rba.gov.au/statistics/tables/csv/f11.1-data.csv (2023 to now)
- Loaded into `raw.rba_f11`. AUD/USD is series `FXRUSD` (US dollars per Australian dollar), observed at 4pm Sydney time on business days.
- Updated daily. History before 2023 is only published as .xls. Numbers read from .xls lose trailing zeros ("0.78", not "0.7800"). Values are stored as text and should be cast in staging.
- Licence risk: the file lists the AUD/USD source as "WM/Reuters", not the RBA. The RBA's terms need the third party's consent to reuse it. Raw files stay out of git, and the test fixtures for this table (`synthetic_rba_f11_*`) hold made-up values, such as 0.1111, that are nowhere near a real rate. The trade-weighted index (`FXRTWI`) is sourced from the RBA.

## ASX prices (supplied by hand)

The S&P/ASX 200 index and the stocks in `config/tickers.yml` are not downloaded. No free source found on 2026-10-17 allows scripted downloads of ten years of ASX prices:

- Yahoo's terms forbid collecting data "using any automated means".
- The ASX site forbids "any spider, screen scraper, robot".
- Stooq blocks scripts with a browser check and needs a key obtained through a CAPTCHA.
- The free tiers of Alpha Vantage and EODHD cover about 100 days and one year.

You supply price files yourself, from a provider whose terms allow your use, by saving them in `data/inbox/`. The folder is gitignored, and no price data is committed. Each file must have these columns, in any order:

| column | meaning |
|---|---|
| ticker | ASX code without a suffix, such as `BHP` (not `BHP.AX`). The index is `XJO`. |
| date | session date, `YYYY-MM-DD` |
| open, high, low | optional |
| close | required. The price as traded on that day, not adjusted. |
| adj_close | optional. Close adjusted for dividends and splits, as calculated by your provider. |
| volume | optional, whole shares |

`close` is the as-reported price and `adj_close` is the adjusted one. Adjusted values change whenever a provider recalculates them, so a later file can disagree with an earlier one for the same date. Each file is loaded as its own snapshot.

Renamed tickers are listed under `former_tickers` in `config/tickers.yml`. Woodside traded as `WPL` until its code changed to `WDS` on 25 May 2022 (ASX notice 0554.22.05, https://asxonline.com/public/notices/2022/may/0554.22.05.html), so a file with either code counts. A ticker that stops early, for example after a delisting, is flagged by the coverage check. Missing sessions inside a ticker's range are also reported, not filled.

## ASX trading calendar

- Source: the `exchange_calendars` Python package (Apache-2.0), calendar `XASX`, version pinned in `requirements.lock`.
- Loaded into `raw.asx_sessions` with each session's closing time in Sydney (16:00, or 14:10 on early-close days). The table is rebuilt on every run.
- A test checks it against the 2026 and 2027 holidays and early closes published by the ASX. They were transcribed by hand on 2026-10-17 into `tests/fixtures/asx_published_calendar_2026_2027.csv`.

## Events (`data/events.csv`)

A hand-edited CSV of RBA monetary policy decisions and ABS releases (CPI, monthly CPI indicator, Labour Force, Wage Price Index) from January 2024 to December 2027. Each row links to the page it came from. Times are Sydney local time.

- RBA: meeting schedule at https://www.rba.gov.au/schedules-events/board-meeting-schedules.html, past decisions at https://www.rba.gov.au/monetary-policy/int-rate-decisions/. Website content is CC BY 4.0. The event date is the day the decision is announced, the second day of the meeting.
- ABS: release calendar at https://www.abs.gov.au/release-calendar/future-releases. Content is CC BY 4.0. Attribution: "Source: Australian Bureau of Statistics".

Checks on 2026-10-17:

- All 32 RBA rows matched the RBA decision pages (2024 to 2026) or the published schedule (November 2026 to 2027).
- All 87 ABS rows dated up to 2026-10-17 were checked against the "Released" date on their own ABS page. 81 matched. 6 were wrong and were corrected.
- The 28 October 2026 CPI row matched the release calendar.
- Not checked: the 15 ABS rows from November 2026 onward, because the calendar page only lists the current month without JavaScript. Also not checked: the release times, which are 11:30 for ABS and 14:30 for the RBA. The January 2026 CPI row says 11:45.

The `verified_on` column holds the date someone checked a row's `event_date` against its `source_url`. Times are not covered by this check. An empty value means the row has not been checked, which is currently true of the 15 ABS rows from November 2026 onward. When you check a row, fill in the date. Raw snapshots saved before this column existed load with it empty.

Add a row by editing the file. The next run saves a new raw snapshot and loads it.

## Not used

Commodity prices are out of scope for now. The RBA Index of Commodity Prices (table I2, monthly) is the clean option if they are added later. Gold has no free source that allows redistribution.
