{{ config(materialized='table') }}

-- A 30-minute price series that runs across the 1 October 2021 change to 5-minute settlement. Before it,
-- the official 30-minute trading price. After it, the mean of the six 5-minute trading prices in each half
-- hour, which is not a settlement price. Before the change the 30-minute price was itself the mean of six
-- dispatch prices (true for all 22,080 trading intervals in the window, to $0.005), so both halves are built
-- the same way. Nothing is rescaled; settlement_regime marks which side of the change a row is on.

with prices as (

    select * from {{ ref('stg_aemo__trading_price') }}

)

select
    time_bucket(interval 30 minute, interval_start)                     as interval_start,
    time_bucket(interval 30 minute, interval_start) + interval 30 minute as interval_end,
    cast(time_bucket(interval 30 minute, interval_start) as date)       as market_date,
    region_id,
    settlement_regime,
    settlement_regime = '30_minute'                                     as is_official_settlement_price,
    avg(price)                                                          as price,
    count(*)                                                            as source_intervals
from prices
group by all
