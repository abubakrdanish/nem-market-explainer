{#
    Hand-edited and RBA files are saved as <name>_<YYYYMMDD>.<ext>. Keep the newest download of each name;
    RBA F11 is split over several names (2014-2017, 2018-2022, 2023-current), and all of them are needed.
#}
{% macro latest_per_file_name(relation) -%}
    _source_file in (
        select _source_file
        from (
            select distinct
                _source_file,
                regexp_replace(_source_file, '_\d{8}(T\d{6})?\.\w+$', '')   as file_name
            from {{ relation }}
        )
        qualify _source_file = max(_source_file) over (partition by file_name)
    )
{%- endmacro %}
