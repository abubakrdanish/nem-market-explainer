# Data dictionary

What the marts hold and the columns that are easy to misread. Table layouts and sources are in [data_sources.md](data_sources.md). Every model and column is also described in the dbt yml under `dbt_project/models/`.

## Read this first

These apply to every mart and must carry through to anything built on them, including the explainer.

### Rooftop solar is missing

**Demand is operational demand, and SCADA excludes rooftop solar, so solar's share of supply is understated.**

- `total_demand_mw` is AEMO's TOTALDEMAND, which is operational demand. Rooftop solar is not metered in dispatch, so it shows up as lower demand rather than as solar generation. In SA1, operational demand falls below zero in 1,222 intervals (578 in 2025).
- Generation columns and fuel shares come from SCADA, which covers utility-scale units only. `solar_generation_mw` and `solar_share` are utility-scale solar.
- Say "share of utility-scale generation" or "share of SCADA generation", never "share of electricity".

### Two series breaks

| Break | Column | Values | Date |
|---|---|---|---|
| 5-minute settlement | `settlement_regime` | `30_minute`, `5_minute` | intervals starting from 2021-10-01 00:00 |
| Battery accounting | `battery_accounting` | `split_units`, `transition`, `bidirectional_units` | transition from 2024-07-04 to 2024-12-10 |

**Settlement.** Before 1 October 2021 the market settled on 30-minute prices, and after it on 5-minute prices. Dispatch prices were 5-minute throughout, so `mart_region_interval.price` and the daily price statistics are comparable across the change. For a half-hour series spanning it, use `int_price_30min`: the official 30-minute price before, and the mean of six 5-minute prices after. Before the change the 30-minute price was the mean of six dispatch prices on all 22,080 trading intervals in the window (to $0.005), so the two halves are built the same way. Nothing is rescaled.

**Battery accounting.** Before 4 July 2024, every battery was registered as two units: a GENERATOR for discharge and a LOAD for charging. From that date, batteries moved one at a time to a single BIDIRECTIONAL unit whose SCADA is negative while charging. The last split LOAD unit reported on 10 December 2024 (`tests/assert_battery_transition_dates_match_data.sql` checks both dates). `battery_charging_mw` adds the two forms together, but the units are defined differently, so do not compare charging across the break without saying so. NEM-wide, charging averages 1,123 MWh a day in `split_units`, 2,653 in `transition` and 9,238 in `bidirectional_units`. New batteries were also connecting over the same years, and these marts do not separate that growth from the change in accounting.

### Market date is a calendar day

`market_date` is the calendar date of `interval_start` in NEM market time (AEST, UTC+10, no daylight saving). It is not the NEM trading day, which runs from 04:00, and it is not Sydney local time. Every interval has `interval_start` and `interval_end`. AEMO's `SETTLEMENTDATE` is `interval_end`.

## Marts

| Mart | Grain | Rows (Oct 2026) | Holds |
|---|---|---:|---|
| `marts.mart_region_interval` | region × 5-minute interval | 2,761,920 | price, flags, cap and floor in force, demand, available generation, net interchange, generation by fuel group, battery charging, other load |
| `marts.mart_region_daily` | region × market date | 9,590 | average, maximum and minimum price; peak and minimum demand; negative-price and high-price interval counts; fuel shares; whether the day touched a suspension, an administered price cap or an intervention run |
| `marts.mart_notable_intervals` | region × interval × rule | 31,056 | intervals flagged by one of seven rules, with the value tested and the threshold |
| `marts.mart_interconnector_interval` | interconnector × 5-minute interval | 3,314,304 | flow, losses, limits, headroom, binding and crossed-limit flags |
| `marts.mart_events` | event × region | 694 | events from `data/events.csv`, joinable on `market_date` and `region_id` |

All prices are $/MWh and all power is MW. Rows use the pricing run only (`INTERVENTION = 0`); `has_intervention_run` says when AEMO also published an intervention run.

### `mart_region_interval`

- **Generation columns.** One column per fuel group, `<group>_generation_mw`, plus `total_generation_mw`. Generation counts positive SCADA from GENERATOR and BIDIRECTIONAL units. Generator auxiliary load (negative SCADA, 156 GWh over the window against 996,688 GWh of output) is left out.
- **No SCADA.** `has_scada` is false in 14 SA1 intervals between September 2024 and March 2025, and their generation columns are null. With SCADA but no unit of a fuel running, the column is 0.
- **Loads.** `battery_charging_mw` is positive. `other_load_mw` is every other LOAD unit, mostly pumped hydro pumps such as SNOWYP.
- **Units that move region.** Each SCADA row takes the region from the registration valid at the start of its interval. TB2SF1, HAUGHTSS and DRXNDB04 change region in this window.

### Fuel groups

From GENUNITS `CO2E_ENERGY_SOURCE`, mapped in `dbt_project/seeds/fuel_groups.csv`:

| Group | AEMO fuel names |
|---|---|
| `black_coal`, `brown_coal` | Black coal, Brown coal |
| `gas` | Natural Gas (Pipeline), Coal seam methane (both spellings), Coal mine waste gas, Ethane |
| `liquid_fuel` | Diesel oil, Kerosene - non aviation |
| `hydro`, `wind`, `solar`, `battery` | Hydro, Wind, Solar, Battery Storage |
| `bioenergy` | Landfill biogas methane, Biomass and industrial materials, Bagasse, Other Biofuels, Primary solid biomass fuels |
| `other` | Other solid fossil fuels |
| `unknown` | no fuel listed |

- **Missing fuel is kept.** Units with no fuel go to `unknown` and `int_units.is_fuel_missing` is true. 36 units in SCADA have no generating-set mapping at all. In September 2026, 0.47% of SCADA MWh had no fuel.
- **Split battery LOAD units** have no fuel of their own. A LOAD unit at a station with a battery generating set goes to `battery`.
- **Dual-fuel rule.** A unit's fuel comes from its generating sets at their latest DUALLOC effective date. When those sets list more than one fuel, the fuel with the most registered capacity wins, ties broken alphabetically, and sets with no fuel are ignored. Most capacity is the closest the registration data gets to "main fuel", and the rule never splits one unit's output across fuels, which SCADA cannot support. It decides two units: BBASEHOS (three 1 MW gas sets and one 1 MW diesel set, so gas), which reports no SCADA in the window, and JACKSGUL (landfill gas and a set with no fuel, so landfill gas).
- **Current fuel only.** A unit keeps its current fuel across its whole history.
- An AEMO fuel name not in the seed fails a dbt test rather than disappearing.

### `mart_notable_intervals`

One row per region, interval and rule; an interval can match several rules. Thresholds are dbt vars in `dbt_project/dbt_project.yml`, set where each distribution stops falling and flattens into a tail (pricing-run rows, all regions, July 2021 to September 2026, $250 bins):

| Rule | Flags | Why this threshold | Rows |
|---|---|---|---:|
| `high_price` | price ≥ $1,500 | rows per dollar fall from 8,725 below $250 to 0.37 at $1,500–1,750, then stay between 0.1 and 1.1 up to the cap | 3,130 |
| `deep_negative_price` | price < −$150 | rows per dollar fall from 7,533 at $0 to −$25 to 33 at −$150 to −$175, then form a flat tail to the floor | 4,752 |
| `price_jump` | change of ≥ $1,250 from the region's previous interval | rows per dollar fall from 11,002 below $250 to 0.56 at $1,250–1,500, then stay flat | 2,803 |
| `at_price_cap` | price at the cap in force | the cap is a market rule | 284 |
| `at_price_floor` | price at the floor in force | the floor is a market rule | 76 |
| `market_suspended` | MARKETSUSPENDEDFLAG non-zero | see the flags below | 13,524 |
| `apc_set` | APCFLAG non-zero | see the flags below | 6,487 |

The thresholds apply to all regions alike. Tasmania and Victoria have thinner high-price tails, so the same threshold flags fewer intervals there.

### `mart_interconnector_interval`

- **Direction.** Positive `mw_flow` runs from `from_region_id` to `to_region_id` (seed `interconnectors.csv`). A test checks every region's net interchange against the signed flows, within losses plus 5 MW.
- **Limits.** `export_limit_mw` and `import_limit_mw` are AEMO's calculated limits, which include every constraint invoked in dispatch.
- **`is_binding`.** True when flow is within 0.1 MW of the limit in its direction, or the limits are crossed. 870,320 rows are within 0.01 MW of a limit and only 600 lie between 0.01 and 0.1 MW, so the cut is clear. Binding means some constraint involving the link bound; the mart does not say which. The binding constraint IDs (`EXPORTGENCONID`, `IMPORTGENCONID`) are in the archive files on disk but are not loaded.
- **`limits_crossed`.** True in 95,757 rows where the export limit is below the import limit. Flow then sits on one of them in 98–99% of rows.
- **`marginal_value`** is 0 on every link except Basslink, so it cannot be used to detect binding.

### `mart_events`

Events in `dbt_project/seeds/event_regions.csv` apply to one region (the four Liddell closures, NSW1). Every other event applies to all five regions, so each appears five times. `scope` says which. `time_sydney` is Sydney local time, an hour ahead of market time during daylight saving.

## `raw.aemo_dispatchprice` flags

Both flags are integer codes, not booleans. Test them against zero, never `= 1`. The pipeline's predicates are `aemo.SUSPENDED` and `aemo.APC_SET` in `ingestion/aemo.py`, and `aemo.suspension_runs()` returns each region's unbroken runs of suspended intervals. In dbt the same rule is the `flag_set` macro, and the marts carry both the code (`market_suspended_code`, `apc_code`) and a boolean (`is_market_suspended`, `is_apc_set`). Use pricing-run rows (`INTERVENTION = 0`) for analysis.

### `MARKETSUSPENDEDFLAG`

| Value | Meaning | Rows, July 2021 to September 2026 |
|---|---|---:|
| 0 | not suspended | 2,754,916 |
| 1 | suspended; exact meaning unconfirmed | 2,190 |
| 2 | suspended; exact meaning unconfirmed | 22,249 |

- **Suspended means non-zero.** The June 2022 suspension, from 14:05 on 15 June to 14:00 on 24 June in every region, is flagged 2 for the intervals ending up to 04:00 on 23 June and 1 after that. Filtering on `= 1` finds only the last 34 hours. `tests/assert_june_2022_suspension_reaches_daily_mart.sql` fails if that happens.
- **The flag is per region.** Most non-zero periods cover one region, so group by `regionid`.
- **What 1 and 2 mean is unconfirmed.** No AEMO documentation for the codes has been found. Do not describe a period as one kind of suspension or another from the code alone.
- **Prices during the June 2022 suspension.** They were held at or below about $300/MWh for most of the suspension, but neither flag explains that alone: APCFLAG is set on only 26% of the suspended region-intervals, and none in TAS1. See [findings.md](findings.md#june-2022-lower-prices-during-the-suspension-are-not-explained-by-the-suspension-flag-or-the-apc-flag-alone) before attributing the low prices to the suspension or to the administered price cap.
- **Only June 2022 has been checked against AEMO's announcements.** The other non-zero periods are listed in [data_sources.md](data_sources.md#the-june-2022-suspension). Until each is checked against a market notice, the explainer should say the archive flags the region as suspended, not that AEMO suspended the market.

### `APCFLAG`

Administered price cap flag. Values seen include 1, 4, 5, 8, 16, 17, 20, 21 and 24, which look like a bit field. What each bit means is unconfirmed.

- **Set means non-zero.** In June 2022, 10,834 rows are non-zero and only 348 equal 1.
- Do not decode individual bits until AEMO's definition is found.
