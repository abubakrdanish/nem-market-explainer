-- Generating sets with their fuel and capacity, from the newest GENUNITS snapshot.

with source as (

    select * from {{ source('raw', 'aemo_genunits') }}
    where {{ latest_standing_files(source('raw', 'aemo_genunits')) }}

)

select
    gensetid                    as genset_id,
    gensettype                  as genset_type,
    registeredcapacity          as registered_capacity_mw,
    maxcapacity                 as max_capacity_mw,
    co2e_energy_source          as fuel_source,
    co2e_emissions_factor       as emissions_factor,
    lastchanged                 as last_changed,
    _source_file,
    _loaded_at
from source
