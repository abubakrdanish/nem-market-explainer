-- Each half hour in int_price_30min comes from one official 30-minute price before the settlement change and
-- from six 5-minute prices after it. First and last half hours are skipped, as a load can start mid-way.

with checked as (

    select *
    from {{ ref('int_price_30min') }}
    where interval_end > (select min(interval_end) from {{ ref('int_price_30min') }})
      and interval_end < (select max(interval_end) from {{ ref('int_price_30min') }})

)

select interval_end, region_id, settlement_regime, source_intervals
from checked
where source_intervals <> case settlement_regime when '30_minute' then 1 else 6 end
