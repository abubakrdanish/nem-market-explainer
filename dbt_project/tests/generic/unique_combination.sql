{#
    Fails for each combination of `columns` that appears more than once,
    i.e. asserts the model's grain. Written here to avoid a dbt_utils dependency.
#}
{% test unique_combination(model, columns) %}

select {{ columns | join(', ') }}, count(*) as row_count
from {{ model }}
group by {{ columns | join(', ') }}
having count(*) > 1

{% endtest %}
