{{ config(materialized='table') }}

-- The expensive model: every SCADA row, joined to the registration valid at the start of its interval and
-- summed by region and fuel group. Region comes from that registration period, not the latest one,
-- because units change region (TB2SF1, HAUGHTSS and DRXNDB04 in this window).
--
-- generation_mw counts positive SCADA from GENERATOR and BIDIRECTIONAL units. Negative SCADA from
-- GENERATOR units is auxiliary load (156 GWh against 996,688 GWh of output over the window) and is left out.
-- battery_charging_mw is positive: SCADA of split battery LOAD units plus negative SCADA of BIDIRECTIONAL
-- units. other_load_mw is every other LOAD unit, mostly pumped hydro pumps.
-- SCADA covers only units AEMO dispatches or meters in real time, so rooftop solar is missing.

with scada as (

    select * from {{ ref('stg_aemo__unit_scada') }}

),

units as (

    select * from {{ ref('int_units') }}

)

select
    scada.interval_start,
    scada.interval_end,
    scada.market_date,
    units.region_id,
    units.fuel_group,
    sum(case when units.output_role in ('generator', 'bidirectional') and scada.scada_mw > 0
             then scada.scada_mw else 0 end)                as generation_mw,
    sum(case when units.output_role = 'bidirectional' and scada.scada_mw < 0 then -scada.scada_mw
             when units.output_role = 'battery_charging_load' then scada.scada_mw
             else 0 end)                                    as battery_charging_mw,
    sum(case when units.output_role = 'other_load'
             then scada.scada_mw else 0 end)                as other_load_mw,
    count(*)                                                as units_reporting
from scada
inner join units
    on units.duid = scada.duid
   and scada.interval_start >= units.valid_from
   and scada.interval_start < units.valid_to
group by all
