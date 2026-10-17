-- Events from data/events.csv, one row per event and region it applies to, so they join to the other marts
-- on market_date and region_id. Region-specific events are listed in the event_regions seed; every other
-- event (NEM-wide market changes, RBA decisions, ABS releases) applies to all five regions.

with events as (

    select * from {{ ref('stg_events') }}

),

event_regions as (

    select * from {{ ref('event_regions') }}

)

select
    events.event_date                                               as market_date,
    regions.region_id,
    events.event_type,
    events.title,
    events.time_sydney,
    events.source_url,
    events.verified_on,
    case when event_regions.region_id is null then 'all_regions' else 'region' end as scope
from events
left join event_regions using (event_date, title)
inner join {{ ref('regions') }} as regions
    on event_regions.region_id is null
    or regions.region_id = event_regions.region_id
