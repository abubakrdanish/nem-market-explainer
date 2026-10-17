# Findings

Things the marts show that were not obvious beforehand, each with a query to re-run against `warehouse/nem.duckdb`. Figures are from the build of 2026-10-17, covering July 2021 to September 2026; 2026 is January to September only. They describe past data. They are not energy market advice or financial advice.

## Price spikes make up a large share of average prices

Intervals priced at or above $1,500/MWh are 0.19% of SA1's intervals but 18.2% of the sum of its prices. Without them, SA1's average price over the window falls from $96 to $79. In NSW1 they are 0.13% of intervals and 11.6% of the price sum.

```sql
select region_id,
       avg(price)                                                     as avg_price,
       100 * avg((price >= 1500)::int)                                as pct_intervals,
       100 * sum(price) filter (where price >= 1500) / sum(price)     as pct_of_price_sum,
       avg(price) filter (where price < 1500)                         as avg_price_without
from marts.mart_region_interval
group by 1 order by 1;
```

## Interconnectors sit at a limit much of the time

Flow is at its calculated limit in 52% of intervals on Murraylink, 48% on Basslink, 40% on VNI, 28% on Heywood, 27% on QNI and 25% on Terranora. The calculated limits include every constraint invoked in dispatch, so this means some constraint involving the link bound, not that the link was at its thermal rating.

```sql
select interconnector_name, 100 * avg(is_binding::int) as pct_binding
from marts.mart_interconnector_interval
group by 1 order by 2 desc;
```

## June 2022: lower prices during the suspension are not explained by the suspension flag or the APC flag alone

Suspended intervals averaged less than the rest of June 2022 in every region: NSW1 $283 against $447, QLD1 $253 against $463. **Do not read this as "the suspension lowered prices".**

The likely explanation was an administered price cap: prices in June 2022 bunch at $300/MWh, which matches an administered cap of that size. The data supports it only in part:

| Suspended region-intervals, 15 to 24 June 2022 | Rows | Above $300 | At $300 | Below $300 |
|---|---:|---:|---:|---:|
| APCFLAG set (code 16 in every case) | 3,421 | 0 | 0 | 3,421 |
| APCFLAG not set | 9,534 | 741 | 1,644 | 7,149 |

- **Where APCFLAG is set during the suspension, every price is below $300.** That fits a cap.
- **APCFLAG covers only part of the suspension:** 80% of suspended intervals in QLD1, 25% in VIC1, 20% in SA1, 7% in NSW1 and none in TAS1.
- **Without the flag, prices were still held down:** 94% of the unflagged suspended intervals are at or below $300, and TAS1 never goes above $300 although the flag is never set there.
- **The comparison itself is uneven.** The rest of June includes the days before the suspension, when prices reached the $15,100 cap. After the suspension (25 to 30 June), prices were lower than before it in QLD1 and TAS1 but not in SA1 or VIC1.

So the APC flag accounts for the low prices only where it is set, and something else held prices at or below about $300 through the rest of the suspension. Two points are unconfirmed: that the administered price cap was $300/MWh (the warehouse has the market cap and floor but not the APC level), and whether AEMO's pricing during a suspension explains the unflagged intervals. AEMO's suspension pricing reports (`Mktsusp_Pricing` on NEMWEB) may settle both. Until then, describe the week as "prices were held at or below about $300/MWh for most of the suspension", and name neither the suspension nor the APC as the cause.

```sql
-- Prices by suspension and APC state.
select is_market_suspended, is_apc_set, count(*) as intervals,
       count(*) filter (where price > 300.005)            as above_300,
       count(*) filter (where abs(price - 300) <= 0.005)  as at_300,
       count(*) filter (where price < 299.995)            as below_300
from marts.mart_region_interval
where market_date between '2022-06-01' and '2022-06-30'
group by all order by 1, 2;

-- Share of each region's suspended intervals with APCFLAG set.
select region_id, 100 * avg(is_apc_set::int) filter (where is_market_suspended) as pct_apc
from marts.mart_region_interval
where market_date between '2022-06-01' and '2022-06-30'
group by 1 order by 1;

-- Mean price before, during and after the suspension.
select region_id,
       avg(price) filter (where market_date < '2022-06-15' and not is_market_suspended) as before,
       avg(price) filter (where is_market_suspended)                                     as suspended,
       avg(price) filter (where market_date > '2022-06-24')                              as after
from marts.mart_region_interval
where market_date between '2022-06-01' and '2022-06-30'
group by 1 order by 1;
```

## SA1 operational demand below zero is becoming common

SA1 operational demand was below zero in 21 intervals in 2021, none in 2022, 66 in 2023, 315 in 2024 and 578 in 2025, reaching −311 MW. Operational demand leaves out rooftop solar, so this is rooftop output exceeding what the grid supplies; it is not demand for electricity falling below zero.

```sql
select year(market_date), count(*) filter (where total_demand_mw < 0), min(total_demand_mw)
from marts.mart_region_interval
where region_id = 'SA1'
group by 1 order by 1;
```
