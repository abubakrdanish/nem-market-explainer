-- Every non-zero SCADA row matches a unit registration valid at the start of its interval. Rows that match
-- none drop out of int_unit_output_by_fuel without any error. Zero rows are allowed: eight split battery
-- units (BALB, GANN, RIVN, DPNT) keep sending 0 MW for about 13 hours after their registrations end at
-- 2024-08-14 00:00, and a zero adds nothing wherever it goes.

select scada.duid, count(*) as unmatched_rows, sum(abs(scada.scada_mw)) as unmatched_abs_mw,
       min(scada.interval_end) as first_interval_end, max(scada.interval_end) as last_interval_end
from {{ ref('stg_aemo__unit_scada') }} as scada
anti join {{ ref('int_units') }} as units
    on units.duid = scada.duid
   and scada.interval_start >= units.valid_from
   and scada.interval_start < units.valid_to
where scada.scada_mw <> 0
group by scada.duid
