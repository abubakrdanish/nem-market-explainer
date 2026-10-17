-- The battery transition dates in dbt_project.yml match the data: the first BIDIRECTIONAL registration starts
-- on battery_transition_start_date, and the last SCADA from a split battery LOAD unit falls on
-- battery_transition_end_date. Each check is skipped when the data holds no such units.

with first_bidirectional as (

    select min(cast(valid_from as date)) as found_date
    from {{ ref('int_units') }}
    where output_role = 'bidirectional'

),

last_split_load as (

    select max(scada.market_date) as found_date
    from {{ ref('stg_aemo__unit_scada') }} as scada
    inner join {{ ref('int_units') }} as units
        on units.duid = scada.duid
       and scada.interval_start >= units.valid_from
       and scada.interval_start < units.valid_to
    where units.output_role = 'battery_charging_load'

)

select 'battery_transition_start_date' as var_name, found_date,
       date '{{ var("battery_transition_start_date") }}' as var_date
from first_bidirectional
where found_date is not null and found_date <> date '{{ var("battery_transition_start_date") }}'
union all
select 'battery_transition_end_date', found_date, date '{{ var("battery_transition_end_date") }}'
from last_split_load
where found_date is not null and found_date <> date '{{ var("battery_transition_end_date") }}'
