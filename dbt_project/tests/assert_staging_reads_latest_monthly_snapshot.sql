-- Staging reads only the newest download of each month, and drops no month. Checked on the cheapest and the
-- largest monthly table.

{% set checks = [('stg_aemo__dispatch_price', 'aemo_dispatchprice'),
                 ('stg_aemo__unit_scada', 'aemo_dispatch_unit_scada')] %}

with raw_files as (

    {% for model, raw_table in checks %}
    select distinct '{{ model }}' as model, _source_file from {{ source('raw', raw_table) }}
    {% if not loop.last %}union all{% endif %}
    {% endfor %}

),

staged_files as (

    {% for model, raw_table in checks %}
    select distinct '{{ model }}' as model, _source_file from {{ ref(model) }}
    {% if not loop.last %}union all{% endif %}
    {% endfor %}

),

expected as (

    select model, _source_file
    from raw_files
    qualify regexp_extract(_source_file, '_(\d{8}(T\d{6})?)\.zip$', 1)
          = max(regexp_extract(_source_file, '_(\d{8}(T\d{6})?)\.zip$', 1))
            over (partition by model, regexp_extract(_source_file, '_(\d{6})_\d\d_', 1))

)

select coalesce(expected.model, staged_files.model) as model,
       coalesce(expected._source_file, staged_files._source_file) as _source_file,
       case when staged_files._source_file is null then 'newest file not read' else 'older file read' end as problem
from expected
full outer join staged_files using (model, _source_file)
where expected._source_file is null or staged_files._source_file is null
