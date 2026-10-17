-- Total generation in the mart equals a recount straight from staging SCADA and unit registrations, which
-- skips int_units and the fuel mapping. A fuel join that duplicates or drops units shows up here.

with recount as (

    select scada.interval_end, details.region_id, sum(scada.scada_mw) as generation_mw
    from {{ ref('stg_aemo__unit_scada') }} as scada
    inner join {{ ref('stg_aemo__unit_details') }} as details
        on details.duid = scada.duid
       and scada.interval_start >= details.valid_from
       and scada.interval_start < details.valid_to
    where details.dispatch_type in ('GENERATOR', 'BIDIRECTIONAL')
      and scada.scada_mw > 0
    group by all

),

mart as (

    select interval_end, region_id, total_generation_mw
    from {{ ref('mart_region_interval') }}
    where has_scada

)

select
    coalesce(mart.interval_end, recount.interval_end) as interval_end,
    coalesce(mart.region_id, recount.region_id) as region_id,
    mart.total_generation_mw,
    recount.generation_mw as recounted_generation_mw
from mart
full outer join recount using (interval_end, region_id)
where abs(coalesce(mart.total_generation_mw, 0) - coalesce(recount.generation_mw, 0)) > 0.01
