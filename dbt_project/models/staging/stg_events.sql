-- Hand-edited events calendar (data/events.csv), newest snapshot only. time_sydney is Sydney local time,
-- which differs from NEM market time by an hour during daylight saving.

with source as (

    select * from {{ source('raw', 'events') }}
    where {{ latest_per_file_name(source('raw', 'events')) }}

)

select
    event_date,
    time_sydney,
    event_type,
    title,
    source_url,
    verified_on,
    _source_file,
    _loaded_at
from source
