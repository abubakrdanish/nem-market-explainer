-- One row per region and market date (the calendar day, in AEST, of each interval's start). The NEM trading
-- day runs from 04:00, so these days do not match AEMO's trading-day reports. Prices are 5-minute dispatch
-- prices throughout, so averages are comparable across the October 2021 settlement change.

with intervals as (

    select * from {{ ref('mart_region_interval') }}

)

select
    market_date,
    region_id,
    count(*)                                                                as intervals,
    avg(price)                                                              as avg_price,
    max(price)                                                              as max_price,
    min(price)                                                              as min_price,
    max(total_demand_mw)                                                    as peak_demand_mw,
    min(total_demand_mw)                                                    as min_demand_mw,
    count(*) filter (where price < 0)                                       as negative_price_intervals,
    count(*) filter (where price >= {{ var('high_price_threshold') }})      as high_price_intervals,
    sum(total_generation_mw) / 12                                           as total_generation_mwh,
    {%- for group in var('fuel_groups') %}
    sum({{ group }}_generation_mw) / nullif(sum(total_generation_mw), 0)   as {{ group }}_share,
    {%- endfor %}
    sum(battery_charging_mw) / 12                                           as battery_charging_mwh,
    bool_or(is_market_suspended)                                            as touched_suspension,
    bool_or(is_apc_set)                                                     as touched_apc,
    bool_or(has_intervention_run)                                           as had_intervention_run,
    count(*) filter (where not has_scada)                                   as intervals_without_scada,
    any_value(settlement_regime)                                            as settlement_regime,
    any_value(battery_accounting)                                           as battery_accounting
from intervals
group by market_date, region_id
