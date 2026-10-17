-- The fuel-group columns add up to total generation. A fuel name missing from the fuel_groups seed, or a
-- group missing from the fuel_groups var, leaves generation in the total but in no column.

select
    interval_end,
    region_id,
    total_generation_mw,
    {% for group in var('fuel_groups') %}{{ group }}_generation_mw{% if not loop.last %} + {% endif %}{% endfor %} as fuel_column_sum_mw
from {{ ref('mart_region_interval') }}
where has_scada
  and abs(total_generation_mw - ({% for group in var('fuel_groups') %}{{ group }}_generation_mw{% if not loop.last %} + {% endif %}{% endfor %})) > 0.01
