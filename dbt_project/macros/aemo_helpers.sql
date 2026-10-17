{#
    Raw AEMO files are saved as <table>_<YYYYMM>_<part>_<YYYYMMDD>.zip, and every download is kept.
    A republished month gets a new download date, and since August 2024 a month can be split into parts,
    so the newest snapshot of a month is every part sharing that month's latest download date.
#}
{% macro latest_monthly_files(relation) -%}
    _source_file in (
        select _source_file
        from (
            select distinct
                _source_file,
                regexp_extract(_source_file, '_(\d{6})_\d\d_', 1)              as file_month,
                regexp_extract(_source_file, '_(\d{8}(T\d{6})?)\.zip$', 1)      as downloaded
            from {{ relation }}
        )
        qualify downloaded = max(downloaded) over (partition by file_month)
    )
{%- endmacro %}

{#
    Standing tables repeat their full history in every monthly file, so only the newest month's newest
    download is read.
#}
{% macro latest_standing_files(relation) -%}
    _source_file in (
        select _source_file
        from (
            select distinct
                _source_file,
                regexp_extract(_source_file, '_(\d{6})_\d\d_', 1)              as file_month,
                regexp_extract(_source_file, '_(\d{8}(T\d{6})?)\.zip$', 1)      as downloaded
            from {{ relation }}
        )
        qualify file_month = max(file_month) over ()
            and downloaded = max(downloaded) over ()
    )
{%- endmacro %}

{#
    DISPATCHPRICE flags hold codes, not booleans: MARKETSUSPENDEDFLAG is 1 or 2 while a region is suspended
    and APCFLAG is a bit field. Set means non-zero, never "= 1". Same rule as aemo.SUSPENDED in Python.
#}
{% macro flag_set(column) -%}
    coalesce({{ column }}, 0) <> 0
{%- endmacro %}

{% macro interval_columns(interval_end, minutes=5) -%}
    {{ interval_end }} - interval {{ minutes }} minute                  as interval_start,
    {{ interval_end }}                                                  as interval_end,
    cast({{ interval_end }} - interval {{ minutes }} minute as date)    as market_date
{%- endmacro %}

{% macro battery_accounting(market_date) -%}
    case
        when {{ market_date }} < date '{{ var("battery_transition_start_date") }}' then 'split_units'
        when {{ market_date }} <= date '{{ var("battery_transition_end_date") }}' then 'transition'
        else 'bidirectional_units'
    end
{%- endmacro %}
