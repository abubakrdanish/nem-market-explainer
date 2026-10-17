-- Unit registration history from the newest DUDETAILSUMMARY snapshot. Each row is valid from start_date
-- up to, not including, end_date; AEMO uses 2999-12-31 for open periods. Units can change region over time.

with source as (

    select * from {{ source('raw', 'aemo_dudetailsummary') }}
    where {{ latest_standing_files(source('raw', 'aemo_dudetailsummary')) }}

)

select
    duid,
    start_date      as valid_from,
    end_date        as valid_to,
    dispatchtype    as dispatch_type,
    schedule_type,
    regionid        as region_id,
    stationid       as station_id,
    participantid   as participant_id,
    lastchanged     as last_changed,
    _source_file,
    _loaded_at
from source
