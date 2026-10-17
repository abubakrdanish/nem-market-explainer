-- 48 trading intervals per region per day before 5-minute settlement and 288 from 1 October 2021. The 30-minute
-- interval ending at midnight on 1 October starts on 30 September, so the change falls on the date boundary.
-- The first and last dates in the data are skipped, because a load can start or end part-way through a day.

with days as (

    select market_date, region_id, count(*) as intervals
    from {{ ref('stg_aemo__trading_price') }}
    group by all

),

checked as (

    select
        *,
        case when market_date < cast(timestamp '{{ var("five_minute_settlement_start") }}' as date)
             then 48 else 288 end as expected_intervals
    from days
    where market_date > (select min(market_date) from days)
      and market_date < (select max(market_date) from days)

)

select * from checked
where intervals <> expected_intervals
