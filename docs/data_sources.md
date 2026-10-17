# Data sources

Terms were last checked on 2026-10-17. Check them again before publishing anything built on this data.

AEMO timestamps are stored as published: naive date-times in NEM market time, which is Australian Eastern Standard Time (UTC+10) all year with no daylight saving. They are not Sydney local time. In summer, Sydney clocks run one hour ahead of market time. RBA and ABS dates are plain calendar dates.

## AEMO: National Electricity Market

Publisher: Australian Energy Market Operator. Files come from NEMWEB, https://nemweb.com.au.

### Licence

AEMO's copyright permissions page (https://www.aemo.com.au/privacy-and-legal-notices/copyright-permissions) says AEMO "confirms its general permission for anyone to use AEMO Material for any purpose, but only with accurate and appropriate attribution of the relevant AEMO Material and AEMO as its author". AEMO Material is defined as "documents, reports, sound and video recordings and any other material created by or on behalf of AEMO and made publicly available by AEMO".

The page does not say whether market data files are covered. Older NEMWEB readmes say the data "is provided for information only and is not intended for commercial use". The page itself sits behind a browser check, so its wording above comes from search engine copies of it and was not read directly.

This project treats the data as licensed for personal, non-commercial use with attribution, and redistributes none of it. Raw files and the warehouse are gitignored. Test fixtures copy the file layout with made-up values.

Attribution: "Contains data from the Australian Energy Market Operator (AEMO), nemweb.com.au. AEMO is the author of the data and has not reviewed or endorsed this project."

### Access

- NEMWEB has no robots.txt; the address redirects to an aemo.com.au page. No rate limit is published.
- The pipeline waits 3 seconds between requests and fetches each archive file once. A first run downloads about 2 GB over about 30 minutes. Later runs list the year folders and fetch only months not yet saved.
- visualisations.aemo.com.au serves AEMO's dashboards through an undocumented API and is not used.

### Monthly archive (MMSDM)

Each month's tables are published about two weeks after the month ends, under:

`https://nemweb.com.au/Data_Archive/Wholesale_Electricity/MMSDM/<YYYY>/MMSDM_<YYYY>_<MM>/MMSDM_Historical_Data_SQLLoader/DATA/`

File names changed in August 2024. Up to July 2024 they are `PUBLIC_DVD_<TABLE>_<YYYYMM>010000.zip`. From August 2024 they are `PUBLIC_ARCHIVE#<TABLE>#FILE<nn>#<YYYYMM>010000.zip`, and large tables are split over several parts. The pipeline reads each month's directory listing, so it handles both, and saves files as `<table>_<YYYYMM>_<part>_<YYYYMMDD>.zip`. AEMO republished many months in 2026, so a republished month gets a new snapshot. Delete the saved file to fetch a month again.

Each zip holds one CSV with AEMO's record types: a `C` record, one `I` record naming the columns, `D` data rows, and a closing `C,"END OF REPORT",<n>` that counts every record. A load fails if the count read does not match, or if a needed column is missing. Columns are read by name, because AEMO adds columns between table versions.

The window starts in July 2021, three months before five-minute settlement, and runs to the newest published month. It is set in `config/sources.yml`.

| Table | Raw table | Used for | Rows per month |
|---|---|---|---|
| DISPATCHPRICE | `raw.aemo_dispatchprice` | 5-minute regional price (RRP, $/MWh), administered price and suspension flags | about 43,000, plus intervention rows |
| TRADINGPRICE | `raw.aemo_tradingprice` | settlement price: 30-minute until September 2021, 5-minute after | 7,200 before, about 43,000 after |
| DISPATCHREGIONSUM | `raw.aemo_dispatchregionsum` | demand, available generation, net interchange, intermittent generation | about 43,000 |
| DISPATCHINTERCONNECTORRES | `raw.aemo_dispatchinterconnectorres` | flow, limits and marginal value for the six interconnectors | about 52,000 |
| DISPATCH_UNIT_SCADA | `raw.aemo_dispatch_unit_scada` | MW output of each unit at the end of each interval | 3 to 4.5 million |
| DUDETAILSUMMARY | `raw.aemo_dudetailsummary` | each unit's region, station, type and registration dates | about 23,000 |
| GENUNITS, DUALLOC | `raw.aemo_genunits`, `raw.aemo_dualloc` | fuel type (`CO2E_ENERGY_SOURCE`) and capacity, joined to units through DUALLOC | about 1,000 and 3,000 |
| MARKET_PRICE_THRESHOLDS | `raw.aemo_market_price_thresholds` | market price cap (VOLL) and floor by financial year | about 20 |

The last four are standing tables. Every monthly file repeats their full history, so only the newest month is fetched.

After the completed load of 2026-10-17 (July 2021 to September 2026), `raw.aemo_dispatch_unit_scada` holds 250,980,379 rows. A figure of 177,486,016 reported earlier that day came from a run that stopped partway through the SCADA months.

### Known quirks

- `SETTLEMENTDATE` is the end of the interval. A month's file runs from 00:05 on the first day to 00:00 on the first day of the next month.
- Five-minute settlement started on 1 October 2021. Trading prices are 30-minute up to the interval ending 2021-10-01 00:00 and 5-minute from 00:05. Dispatch prices were 5-minute throughout. In TRADINGPRICE, `PERIODID` counts from midnight, though the NEM trading day starts at 04:00.
- When AEMO intervenes in the market, an interval can have a second row with `INTERVENTION = 1`. Prices and flows for analysis should use `INTERVENTION = 0`. The unique key includes the flag.
- Prices can be negative and can reach the cap. The floor has been −1,000 throughout the window. The cap rose from 15,100 in 2021-22 to 23,200 in 2026-27.
- SCADA values can be negative: batteries charging, and some loads.
- Fuel type is blank for about one in five gensets in GENUNITS, mostly old or retired units.
- The registration data still lists the `SNOWY1` region, removed in 2008. It does not appear in the window.

### The June 2022 suspension

AEMO's media releases, as reported by Clayton Utz and WattClarity, say the spot market in all regions was suspended from 14:05 AEST on 15 June 2022 until 14:00 on 24 June 2022.

The archive matches this once `MARKETSUSPENDEDFLAG` is read as a code, not a yes/no flag. It takes two non-zero values in June 2022, in every region:

| Value | Intervals ending | Intervals |
|---|---|---:|
| 2 | 2022-06-15 14:10 to 2022-06-23 04:00 | 2,183 |
| 1 | 2022-06-23 04:05 to 2022-06-24 14:00 | 408 |

Together they make one unbroken run of 2,591 intervals, from the interval starting at 14:05 on 15 June to the one ending at 14:00 on 24 June. The change from 2 to 1 falls at 04:05 on 23 June, the time WattClarity quotes from AEMO Market Notice 98805 on the "continuation of Market Suspension from 04:05 Thursday 23rd June". An earlier version of this section read only `= 1`, which is why the suspension seemed to start on 23 June.

`APCFLAG` is non-zero on 10,834 rows in the June 2022 file (5,816 of them pricing-run rows, `INTERVENTION = 0`). Its values (1, 4, 5, 8, 16, 17, 20, 21, 24) look like a bit field, and only 348 rows equal 1. The archive's MARKETSUSPENSION table has no June 2022 entry.

Still unconfirmed:

- **What 1 and 2 mean.** No AEMO documentation for the codes has been found. The data shows only that both occur during the suspension and that 2 came first. AEMO's `Mktsusp_Pricing` reports on NEMWEB may explain them.
- **The other non-zero periods.** These have not been checked against AEMO market notices, so they should not be described as suspensions until they are:

| Regions | Intervals ending | Intervals | Values |
|---|---|---:|---|
| SA1 | 2022-02-18 14:30 to 16:10 | 21 | 2 |
| TAS1 | 2022-03-01 12:45 to 19:15 | 79 | 2 |
| NSW1 | 2023-03-17 20:20 to 21:10 | 11 | 2 |
| VIC1 | 2023-04-22 16:25 to 2023-04-23 17:00 | 296 | 2, then 1 from 04:35 on 23 April |
| all five | 2024-09-05 13:55 to 15:10 | 16 | 2 |
| NSW1 | 2026-03-23 11:45 to 18:30 | 82 | 2 |

[data_dictionary.md](data_dictionary.md) sets out how the explainer should use both flags.

## RBA statistical tables

Publisher: Reserve Bank of Australia. Terms: https://www.rba.gov.au/copyright/

Statistical data is excluded from the RBA's CC BY 4.0 licence. Section 5 (Financial Data) and Section 4 (Cash Rate) allow use, reproduction and publication "for personal or commercial purposes", provided nothing implies RBA endorsement and the source is not misrepresented. Material the RBA sources from a third party needs that party's consent.

Attribution: "Source: RBA 2026".

The RBA's robots.txt does not restrict `/statistics/`.

### F1 Interest Rates and Yields: Money Market

- URL: https://www.rba.gov.au/statistics/tables/csv/f1-data.csv
- Loaded into `raw.rba_f1`. The cash rate target is series `FIRMMCRTD`, in per cent, daily from 2011-01-04.
- Known limit: the change series `FIRMMCCRT` is not always filled in. On 2026-09-30 the target moved from 4.35 to 4.60 with no change value. Use the target level, or A2, to find changes.

### A2 Changes in Monetary Policy and Administered Rates

- URL: https://www.rba.gov.au/statistics/tables/csv/a2-data.csv
- Loaded into `raw.rba_a2`. `ARBAMPCNCRT` is the new cash rate target and `ARBAMPCCCR` is the change.
- Dates are the day the change takes effect, which is the day after the announcement.
- Values are kept as text, because early rows are ranges such as "17.00 to 17.50".

### F11 Exchange Rates

- URLs: https://www.rba.gov.au/statistics/tables/xls-hist/2014-2017.xls, https://www.rba.gov.au/statistics/tables/xls-hist/2018-2022.xls and https://www.rba.gov.au/statistics/tables/csv/f11.1-data.csv
- Loaded into `raw.rba_f11`. AUD/USD is series `FXRUSD`, observed at 4pm Sydney time on business days. Numbers read from .xls lose trailing zeros, so values are stored as text.
- Licence risk: the file lists the AUD/USD source as "WM/Reuters". Raw files stay out of git, and the fixtures for this table (`synthetic_rba_f11_*`) hold made-up values.

## Events (`data/events.csv`)

A hand-edited CSV of NEM market events, generator closures, RBA monetary policy decisions and ABS releases. Each row links to the page it came from. `time_sydney` is Sydney local time. For the energy rows it equals NEM time, because none of them fall in daylight saving.

`verified_on` holds the date someone checked a row's `event_date` against its `source_url`. Times are not covered. An empty value means the row has not been checked.

Checks on 2026-10-17:

- Energy rows: the June 2022 suspension start (Clayton Utz) and end (WattClarity, quoting Market Notice 99369), and the four Liddell unit closures (WattClarity, pv magazine) were checked. The five-minute settlement row was not, because AEMO's and the AEMC's pages are behind a browser check. The archive data does show the change at the interval ending 2021-10-01 00:05.
- RBA: all 32 rows matched the RBA decision pages or the published schedule.
- ABS: all 87 rows dated up to 2026-10-17 were checked against their release pages; 6 were wrong and were corrected. The 28 October 2026 CPI row matched the release calendar. The 15 rows from November 2026 onward were not checked.

RBA website content and ABS content are CC BY 4.0. ABS attribution: "Source: Australian Bureau of Statistics".

## Not used

- Constraint and bid tables: 170 MB to several GB a month.
- The rolling `Reports/Current` folders, which cover the weeks the monthly archive has not reached yet.
- AEMO's registration spreadsheet, which sits behind the browser check on aemo.com.au.
- Commodity prices.
