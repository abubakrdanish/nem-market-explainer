-- One row per interconnector and 5-minute interval: flow against its limits. EXPORT and IMPORT limits here
-- are AEMO's calculated limits, which include every constraint invoked in dispatch, so flow at a limit
-- means some constraint involving the link bound. MARGINALVALUE is 0 on every link except Basslink, so
-- binding is read from flow against limits instead. Positive flow runs from from_region_id to to_region_id,
-- which tests/assert_net_interchange_matches_interconnector_flows.sql checks against regional net interchange.

with flows as (

    select * from {{ ref('stg_aemo__dispatch_interconnector') }}

),

links as (

    select * from {{ ref('interconnectors') }}

),

measured as (

    select
        flows.*,
        links.interconnector_name,
        links.from_region_id,
        links.to_region_id,
        flows.export_limit_mw < flows.import_limit_mw           as limits_crossed,
        case when flows.mw_flow >= 0 then flows.export_limit_mw - flows.mw_flow
             else flows.mw_flow - flows.import_limit_mw end     as headroom_mw
    from flows
    left join links using (interconnector_id)

)

select
    interval_start,
    interval_end,
    market_date,
    interconnector_id,
    interconnector_name,
    from_region_id,
    to_region_id,
    case when mw_flow >= 0 then from_region_id else to_region_id end    as exporting_region_id,
    case when mw_flow >= 0 then to_region_id else from_region_id end    as importing_region_id,
    mw_flow,
    metered_mw_flow,
    mw_losses,
    export_limit_mw,
    import_limit_mw,
    headroom_mw,
    limits_crossed,
    -- Crossed limits pin the flow: it sits on one of them in 98-99% of those rows.
    limits_crossed or headroom_mw < {{ var('interconnector_limit_tolerance_mw') }}    as is_binding,
    headroom_mw < -{{ var('interconnector_overshoot_mw') }}                         as is_flow_beyond_limit,
    marginal_value
from measured
