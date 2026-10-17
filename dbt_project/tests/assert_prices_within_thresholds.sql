-- Every dispatch price, pricing run and intervention run, lies within the market price floor and cap in force
-- at the start of its interval. An interval with no thresholds in force also fails.

with prices as (

    select interval_start, region_id, price, 'pricing_run' as run from {{ ref('stg_aemo__dispatch_price') }}
    union all
    select interval_start, region_id, price, 'intervention_run' from {{ ref('stg_aemo__dispatch_price_intervention') }}

)

select prices.*, thresholds.market_price_floor, thresholds.market_price_cap
from prices
left join {{ ref('stg_aemo__market_price_thresholds') }} as thresholds
    on prices.interval_start >= thresholds.valid_from
   and prices.interval_start < thresholds.valid_to
where thresholds.valid_from is null
   or prices.price > thresholds.market_price_cap
   or prices.price < thresholds.market_price_floor
