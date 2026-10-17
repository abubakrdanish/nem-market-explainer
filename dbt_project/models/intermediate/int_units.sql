-- One row per unit and registration period, with region, station, fuel, capacity and the unit's role in
-- the output totals. Fuel comes from the unit's generating sets at their latest DUALLOC effective date, so
-- a unit keeps its current fuel across its whole history.
--
-- Dual-fuel rule: when a unit's generating sets list more than one fuel, the fuel with the most registered
-- capacity wins, ties broken alphabetically, and sets with no fuel are ignored. Most capacity is the closest
-- the registration data gets to "main fuel", and the rule never splits one unit's output across fuels,
-- which SCADA cannot support. It decides two units: BBASEHOS (three 1 MW gas sets and one 1 MW diesel set,
-- so gas), which reports no SCADA in the window, and JACKSGUL (landfill gas plus a set with no fuel, so
-- landfill gas).
--
-- Battery charging: until batteries moved to single BIDIRECTIONAL units, each had a separate LOAD unit for
-- charging, with no fuel of its own. A LOAD unit at a station that has a battery generating set is counted
-- as battery charging.

with current_gensets as (

    select duid, genset_id
    from {{ ref('stg_aemo__unit_gensets') }}
    qualify effective_date = max(effective_date) over (partition by duid)

),

fuel_capacity as (

    select
        c.duid,
        g.fuel_source,
        sum(g.registered_capacity_mw)   as fuel_capacity_mw
    from current_gensets as c
    inner join {{ ref('stg_aemo__gen_units') }} as g using (genset_id)
    group by all

),

unit_fuel as (

    select
        duid,
        first(fuel_source order by fuel_capacity_mw desc, fuel_source)
            filter (where fuel_source is not null)          as fuel_source,
        count(distinct fuel_source)                         as fuel_source_count,
        sum(fuel_capacity_mw)                               as registered_capacity_mw
    from fuel_capacity
    group by duid

),

battery_stations as (

    select distinct d.station_id
    from {{ ref('stg_aemo__unit_details') }} as d
    inner join unit_fuel as f using (duid)
    where f.fuel_source = 'Battery Storage'

),

units as (

    select
        d.*,
        f.fuel_source,
        coalesce(f.fuel_source_count, 0)                    as fuel_source_count,
        f.registered_capacity_mw,
        d.dispatch_type = 'LOAD' and b.station_id is not null as is_battery_load
    from {{ ref('stg_aemo__unit_details') }} as d
    left join unit_fuel as f using (duid)
    left join battery_stations as b using (station_id)

)

select
    units.duid,
    units.valid_from,
    units.valid_to,
    units.region_id,
    units.station_id,
    units.participant_id,
    units.dispatch_type,
    units.schedule_type,
    units.fuel_source,
    units.fuel_source_count,
    -- An unmapped fuel name stays null here rather than becoming 'unknown', so the mart tests catch it.
    case
        when units.is_battery_load then 'battery'
        when units.fuel_source is null then 'unknown'
        else fuel_groups.fuel_group
    end                                                     as fuel_group,
    units.fuel_source is null and not units.is_battery_load as is_fuel_missing,
    units.registered_capacity_mw,
    case
        when units.dispatch_type = 'GENERATOR' then 'generator'
        when units.dispatch_type = 'BIDIRECTIONAL' then 'bidirectional'
        when units.is_battery_load then 'battery_charging_load'
        else 'other_load'
    end                                                     as output_role
from units
left join {{ ref('fuel_groups') }} as fuel_groups using (fuel_source)
