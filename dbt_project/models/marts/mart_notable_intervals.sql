-- Intervals that stand out, one row per region, interval and rule that flagged it. An interval can match
-- several rules. Thresholds are dbt vars, set from the price distribution (see dbt_project.yml).

with intervals as (

    select
        interval_start,
        interval_end,
        market_date,
        region_id,
        price,
        lag(price) over (partition by region_id order by interval_end)          as previous_price,
        lag(interval_end) over (partition by region_id order by interval_end)   as previous_interval_end,
        market_suspended_code,
        is_market_suspended,
        apc_code,
        is_apc_set,
        market_price_cap,
        market_price_floor
    from {{ ref('mart_region_interval') }}

),

flagged as (

    select *, 'high_price' as rule, price as rule_value,
           {{ var('high_price_threshold') }} as rule_threshold
    from intervals
    where price >= {{ var('high_price_threshold') }}

    union all

    select *, 'deep_negative_price', price, {{ var('deep_negative_price_threshold') }}
    from intervals
    where price < {{ var('deep_negative_price_threshold') }}

    union all

    -- Only compare with the interval just before, so a gap in the data is not read as a jump.
    select *, 'price_jump', price - previous_price, {{ var('price_jump_threshold') }}
    from intervals
    where abs(price - previous_price) >= {{ var('price_jump_threshold') }}
      and previous_interval_end = interval_end - interval 5 minute

    union all

    select *, 'at_price_cap', price, market_price_cap
    from intervals
    where price >= market_price_cap

    union all

    select *, 'at_price_floor', price, market_price_floor
    from intervals
    where price <= market_price_floor

    union all

    select *, 'market_suspended', market_suspended_code, 0
    from intervals
    where is_market_suspended

    union all

    select *, 'apc_set', apc_code, 0
    from intervals
    where is_apc_set

)

select
    interval_start,
    interval_end,
    market_date,
    region_id,
    rule,
    case rule
        when 'high_price' then 'price at or above the high-price threshold'
        when 'deep_negative_price' then 'price below the deep-negative threshold'
        when 'price_jump' then 'price changed by at least the jump threshold from the interval before'
        when 'at_price_cap' then 'price at the market price cap in force'
        when 'at_price_floor' then 'price at the market price floor in force'
        when 'market_suspended' then 'MARKETSUSPENDEDFLAG non-zero'
        when 'apc_set' then 'APCFLAG non-zero'
    end                     as rule_description,
    rule_value,
    rule_threshold,
    price,
    previous_price,
    market_suspended_code,
    apc_code
from flagged
