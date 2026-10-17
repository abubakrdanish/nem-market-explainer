-- Daily fuel shares add up to 1 wherever the region generated anything that day.

select
    market_date,
    region_id,
    {% for group in var('fuel_groups') %}coalesce({{ group }}_share, 0){% if not loop.last %} + {% endif %}{% endfor %} as share_sum
from {{ ref('mart_region_daily') }}
where total_generation_mwh > 0
  and abs(1 - ({% for group in var('fuel_groups') %}coalesce({{ group }}_share, 0){% if not loop.last %} + {% endif %}{% endfor %})) > 1e-9
