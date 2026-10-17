-- One row per region and 5-minute dispatch interval: price, demand and supply, the flags, and generation
-- by fuel group. Price is the pricing-run dispatch price (INTERVENTION = 0). Generation comes from SCADA,
-- which leaves out rooftop solar; total_demand_mw is operational demand, which also leaves it out.

with prices as (

    select * from {{ ref('stg_aemo__dispatch_price') }}

),

region_sum as (

    select * from {{ ref('stg_aemo__dispatch_region_sum') }}

),

interventions as (

    select distinct interval_end, region_id
    from {{ ref('stg_aemo__dispatch_price_intervention') }}

),

thresholds as (

    select * from {{ ref('stg_aemo__market_price_thresholds') }}

),

output as (

    select
        interval_end,
        region_id,
        {%- for group in var('fuel_groups') %}
        coalesce(sum(generation_mw) filter (where fuel_group = '{{ group }}'), 0) as {{ group }}_generation_mw,
        {%- endfor %}
        sum(generation_mw)          as total_generation_mw,
        sum(battery_charging_mw)    as battery_charging_mw,
        sum(other_load_mw)          as other_load_mw,
        sum(units_reporting)        as units_reporting
    from {{ ref('int_unit_output_by_fuel') }}
    group by all

)

select
    prices.interval_start,
    prices.interval_end,
    prices.market_date,
    prices.region_id,
    prices.price,
    prices.market_suspended_code,
    prices.is_market_suspended,
    prices.apc_code,
    prices.is_apc_set,
    interventions.interval_end is not null                  as has_intervention_run,
    thresholds.market_price_cap,
    thresholds.market_price_floor,
    case when prices.interval_start < timestamp '{{ var("five_minute_settlement_start") }}'
         then '30_minute' else '5_minute' end               as settlement_regime,
    region_sum.total_demand_mw,
    region_sum.available_generation_mw,
    region_sum.net_interchange_mw,
    region_sum.intermittent_generation_mw,
    {%- for group in var('fuel_groups') %}
    output.{{ group }}_generation_mw,
    {%- endfor %}
    output.total_generation_mw,
    output.battery_charging_mw,
    output.other_load_mw,
    coalesce(output.units_reporting, 0)                     as units_reporting,
    output.interval_end is not null                         as has_scada,
    {{ battery_accounting('prices.market_date') }}          as battery_accounting
from prices
left join region_sum using (interval_end, region_id)
left join interventions using (interval_end, region_id)
left join output using (interval_end, region_id)
left join thresholds
    on prices.interval_start >= thresholds.valid_from
   and prices.interval_start < thresholds.valid_to
