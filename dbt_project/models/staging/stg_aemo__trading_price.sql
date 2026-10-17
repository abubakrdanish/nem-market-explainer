-- Settlement (trading) price. Intervals are 30 minutes up to the one ending at the 5-minute settlement
-- start, and 5 minutes after it. AEMO rounds this price to the cent, so it can differ from the dispatch
-- price by up to $0.005.

with source as (

    select * from {{ source('raw', 'aemo_tradingprice') }}
    where {{ latest_monthly_files(source('raw', 'aemo_tradingprice')) }}

),

regimes as (

    select
        *,
        case when settlementdate <= timestamp '{{ var("five_minute_settlement_start") }}'
             then 30 else 5 end as interval_minutes
    from source

)

select
    settlementdate - to_minutes(interval_minutes)                   as interval_start,
    settlementdate                                                  as interval_end,
    cast(settlementdate - to_minutes(interval_minutes) as date)     as market_date,
    interval_minutes,
    case interval_minutes when 30 then '30_minute' else '5_minute' end as settlement_regime,
    regionid                                                        as region_id,
    periodid                                                        as period_id,
    rrp                                                             as price,
    invalidflag                                                     as invalid_flag,
    price_status,
    lastchanged                                                     as last_changed,
    _source_file,
    _loaded_at
from regimes
