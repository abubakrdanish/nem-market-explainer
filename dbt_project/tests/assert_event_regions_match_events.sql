-- Every row in the event_regions seed matches an event in events.csv, so editing an event's title or date
-- cannot silently turn a region-specific event into one that applies to every region.

select seed.event_date, seed.title
from {{ ref('event_regions') }} as seed
anti join {{ ref('stg_events') }} as events using (event_date, title)
