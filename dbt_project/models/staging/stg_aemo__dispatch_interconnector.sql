-- Interconnector flow and limits per 5-minute interval, pricing-run rows only (INTERVENTION = 0).

with source as (

    select * from {{ source('raw', 'aemo_dispatchinterconnectorres') }}
    where {{ latest_monthly_files(source('raw', 'aemo_dispatchinterconnectorres')) }}

)

select
    {{ interval_columns('settlementdate') }},
    interconnectorid    as interconnector_id,
    mwflow              as mw_flow,
    meteredmwflow       as metered_mw_flow,
    mwlosses            as mw_losses,
    marginalvalue       as marginal_value,
    exportlimit         as export_limit_mw,
    importlimit         as import_limit_mw,
    lastchanged         as last_changed,
    _source_file,
    _loaded_at
from source
where intervention = 0
