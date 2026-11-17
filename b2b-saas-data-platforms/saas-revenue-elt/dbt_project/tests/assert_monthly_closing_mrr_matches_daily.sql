-- The revenue bridge must close on the same MRR as the daily fact table.
with bridge as (
    select period_month, sum(closing_mrr) as closing_mrr
    from {{ ref('fct_mrr_movements_monthly') }}
    group by period_month
),

closing_days as (
    select {{ month_start('date_day') }} as period_month, max(date_day) as closing_day
    from {{ ref('int_date_spine') }}
    group by {{ month_start('date_day') }}
),

daily as (
    select c.period_month, sum(f.mrr_eur) as mrr
    from closing_days c
    join {{ ref('fct_mrr_daily') }} f on f.date_day = c.closing_day
    group by c.period_month
)

select b.period_month, b.closing_mrr, d.mrr
from bridge b
join daily d on d.period_month = b.period_month
where abs(b.closing_mrr - d.mrr) > 0.01
