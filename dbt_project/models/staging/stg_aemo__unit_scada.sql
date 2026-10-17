-- MW output of each unit at the end of each 5-minute interval. A view, so the 251 million raw rows are
-- not copied.

with source as (

    select * from {{ source('raw', 'aemo_dispatch_unit_scada') }}
    where {{ latest_monthly_files(source('raw', 'aemo_dispatch_unit_scada')) }}

)

select
    {{ interval_columns('settlementdate') }},
    duid,
    scadavalue      as scada_mw,
    _source_file,
    _loaded_at
from source
