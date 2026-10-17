-- No unit has two registration periods that overlap. Overlapping periods would put a unit's output in two
-- regions on the same date, or count it twice in one region.

select
    a.duid,
    a.region_id as region_a,
    a.valid_from as valid_from_a,
    a.valid_to as valid_to_a,
    b.region_id as region_b,
    b.valid_from as valid_from_b,
    b.valid_to as valid_to_b
from {{ ref('int_units') }} as a
inner join {{ ref('int_units') }} as b
    on a.duid = b.duid
   and a.valid_from < b.valid_from
   and b.valid_from < a.valid_to
