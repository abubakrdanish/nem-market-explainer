-- RBA statistical table F1, newest download of each file. Values stay as published text; value_number
-- is null where the text is not a number (early A2 rows are ranges such as '17.00 to 17.50').

with source as (

    select * from {{ source('raw', 'rba_f1') }}
    where {{ latest_per_file_name(source('raw', 'rba_f1')) }}

)

select
    series_id,
    title,
    units,
    obs_date,
    value,
    try_cast(value as double)   as value_number,
    _source_file,
    _loaded_at
from source
