{#
    Fails for non-null values outside [min_value, max_value] (inclusive).
    Either bound may be omitted. Written here to avoid a dbt_utils dependency.
#}
{% test accepted_range(model, column_name, min_value=none, max_value=none) %}

select {{ column_name }} as out_of_range_value
from {{ model }}
where {{ column_name }} is not null
  and (
      false
      {% if min_value is not none %} or {{ column_name }} < {{ min_value }} {% endif %}
      {% if max_value is not none %} or {{ column_name }} > {{ max_value }} {% endif %}
  )

{% endtest %}
