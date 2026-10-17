-- 5-minute regional dispatch price, pricing-run rows only (INTERVENTION = 0). When AEMO intervenes, an
-- interval also gets an INTERVENTION = 1 row; those are in stg_aemo__dispatch_price_intervention.
-- Both flags are codes, not booleans, so "set" means non-zero (see docs/data_dictionary.md).

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
    price_status,
    lastchanged                                 as last_changed,
    _source_file,
    _loaded_at
from source
where intervention = 0
