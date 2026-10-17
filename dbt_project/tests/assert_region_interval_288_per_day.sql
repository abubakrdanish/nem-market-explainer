-- Dispatch was 5-minute throughout, so every region has 288 intervals on every day, and every day has all
-- five regions. First and last dates are skipped, as in assert_settlement_intervals_per_day.

with days as (

    select market_date, region_id, count(*) as intervals
    from {{ ref('mart_region_interval') }}
    group by all

),

inner_dates as (

    select distinct market_date
    from days
    where market_date > (select min(market_date) from days)
      and market_date < (select max(market_date) from days)

),

expected as (

    select inner_dates.market_date, regions.region_id
    from inner_dates
    cross join {{ ref('regions') }} as regions

)

select expected.market_date, expected.region_id, coalesce(days.intervals, 0) as intervals
from expected
left join days using (market_date, region_id)
where coalesce(days.intervals, 0) <> 288
