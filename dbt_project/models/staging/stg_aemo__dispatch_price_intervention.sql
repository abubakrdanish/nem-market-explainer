-- The INTERVENTION = 1 rows of DISPATCHPRICE: the second dispatch run AEMO publishes for an interval
-- when it intervenes in the market. The pricing-run rows are in stg_aemo__dispatch_price.

with source as (

    select * from {{ source('raw', 'aemo_dispatchprice') }}
    where {{ latest_monthly_files(source('raw', 'aemo_dispatchprice')) }}

)

select
    {{ interval_columns('settlementdate') }},
    regionid                                    as region_id,
    rrp                                         as price,
    marketsuspendedflag                         as market_suspended_code,
    {{ flag_set('marketsuspendedflag') }}       as is_market_suspended,
    apcflag                                     as apc_code,
    {{ flag_set('apcflag') }}                   as is_apc_set,
    lastchanged                                 as last_changed,
    _source_file,
    _loaded_at
from source
where intervention = 1
