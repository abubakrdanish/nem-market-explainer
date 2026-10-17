-- A region's net interchange (positive = export) equals the signed sum of flows on its interconnectors,
-- within the losses on those links plus a tolerance. This also checks the direction of every link in the
-- interconnectors seed: a reversed link is out by twice its flow.

with signed_flows as (

    select interval_end, from_region_id as region_id, mw_flow as flow_mw, abs(mw_losses) as losses_mw
    from {{ ref('mart_interconnector_interval') }}
    union all
    select interval_end, to_region_id, -mw_flow, abs(mw_losses)
    from {{ ref('mart_interconnector_interval') }}

),

region_flows as (

    select interval_end, region_id, sum(flow_mw) as flow_mw, sum(losses_mw) as losses_mw
    from signed_flows
    group by all

)

select
    region_sum.interval_end,
    region_sum.region_id,
    region_sum.net_interchange_mw,
    region_flows.flow_mw,
    region_flows.losses_mw
from {{ ref('stg_aemo__dispatch_region_sum') }} as region_sum
inner join region_flows using (interval_end, region_id)
where abs(region_sum.net_interchange_mw - region_flows.flow_mw)
      > region_flows.losses_mw + {{ var('net_interchange_tolerance_mw') }}
