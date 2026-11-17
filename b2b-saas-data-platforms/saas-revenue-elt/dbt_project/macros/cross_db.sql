{#- Date helpers. Dates are stored as ISO strings (YYYY-MM-DD) on every target. -#}

{% macro add_days(expr, n) -%}
{%- if target.type == 'duckdb' -%}
strftime(cast({{ expr }} as date) + {{ n }} * interval '1 day', '%Y-%m-%d')
{%- else -%}
date({{ expr }}, '{{ "%+d" % n }} day')
{%- endif -%}
{%- endmacro %}

{% macro month_start(expr) -%}
{%- if target.type == 'duckdb' -%}
strftime(date_trunc('month', cast({{ expr }} as date)), '%Y-%m-%d')
{%- else -%}
date({{ expr }}, 'start of month')
{%- endif -%}
{%- endmacro %}
