-- Regional demand and supply per 5-minute interval, pricing-run rows only (INTERVENTION = 0).
-- TOTALDEMAND is operational demand: it excludes rooftop solar, which AEMO does not meter in dispatch.

with source as (

    select * from {{ source('raw', 'aemo_dispatchregionsum') }}
    where {{ latest_monthly_files(source('raw', 'aemo_dispatchregionsum')) }}

)

select
    {{ interval_columns('settlementdate') }},
    regionid                        as region_id,
    totaldemand                     as total_demand_mw,
    availablegeneration             as available_generation_mw,
    demandforecast                  as demand_forecast_mw,
    netinterchange                  as net_interchange_mw,
    totalintermittentgeneration     as intermittent_generation_mw,
    uigf                            as uigf_mw,
    lastchanged                     as last_changed,
    _source_file,
    _loaded_at
from source
where intervention = 0
