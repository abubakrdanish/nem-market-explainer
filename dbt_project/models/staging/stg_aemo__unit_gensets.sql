-- Which generating sets make up each unit, from the newest DUALLOC snapshot. AEMO revises a mapping by
-- adding a higher VERSIONNO for the same effective date, so only the highest version is kept.

with source as (

    select * from {{ source('raw', 'aemo_dualloc') }}
    where {{ latest_standing_files(source('raw', 'aemo_dualloc')) }}

)

select
    duid,
    gensetid        as genset_id,
    effectivedate   as effective_date,
    versionno       as version_no,
    lastchanged     as last_changed,
    _source_file,
    _loaded_at
from source
qualify versionno = max(versionno) over (partition by duid, effectivedate)
