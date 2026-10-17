-- AEMO suspended the spot market in every region from 14:05 on 15 June to 14:00 on 24 June 2022. The archive
-- codes it 2 and then 1, so a flag test on "= 1" would miss 15 to 22 June. Skipped when the data does not
-- reach June 2022.

with days as (

    select market_date, region_id, touched_suspension
    from {{ ref('mart_region_daily') }}
    where market_date between date '2022-06-15' and date '2022-06-24'

)

select market_date, region_id, touched_suspension
from days
where not touched_suspension
union all
select date '2022-06-15', 'all', null
where exists (select 1 from {{ ref('mart_region_daily') }} where market_date = date '2022-06-30')
  and (select count(*) from days) <> 50
