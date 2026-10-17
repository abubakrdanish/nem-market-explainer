-- Market price cap (VOLL) and floor, valid from each effective date until the next one. Highest version
-- per effective date only.

with source as (

    select * from {{ source('raw', 'aemo_market_price_thresholds') }}
    where {{ latest_standing_files(source('raw', 'aemo_market_price_thresholds')) }}
    qualify versionno = max(versionno) over (partition by effectivedate)

)

select
    effectivedate                                                       as valid_from,
    coalesce(lead(effectivedate) over (order by effectivedate),
             timestamp '2999-12-31')                                    as valid_to,
    voll                                                                as market_price_cap,
    marketpricefloor                                                    as market_price_floor,
    versionno                                                           as version_no,
    lastchanged                                                         as last_changed,
    _source_file,
    _loaded_at
from source
