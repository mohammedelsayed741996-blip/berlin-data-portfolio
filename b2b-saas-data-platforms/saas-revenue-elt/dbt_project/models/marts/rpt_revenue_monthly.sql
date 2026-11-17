-- Monthly revenue bridge for finance and investors.
with m as (
    select * from {{ ref('fct_mrr_movements_monthly') }}
)

select
    period_month,
    round(sum(opening_mrr), 2) as opening_mrr,
    round(sum(case when movement_type = 'new' then mrr_change else 0 end), 2) as new_mrr,
    round(sum(case when movement_type = 'expansion' then mrr_change else 0 end), 2) as expansion_mrr,
    round(sum(case when movement_type = 'contraction' then mrr_change else 0 end), 2) as contraction_mrr,
    round(sum(case when movement_type = 'churn' then mrr_change else 0 end), 2) as churned_mrr,
    round(sum(case when movement_type = 'reactivation' then mrr_change else 0 end), 2) as reactivation_mrr,
    round(sum(closing_mrr), 2) as closing_mrr,
    round(sum(closing_mrr) * 12, 2) as closing_arr,
    sum(case when movement_type = 'new' then 1 else 0 end) as new_logos,
    sum(case when movement_type = 'churn' then 1 else 0 end) as churned_logos,
    round(
        sum(case when opening_mrr > 0 then closing_mrr else 0 end) * 1.0
        / nullif(sum(opening_mrr), 0), 4) as net_revenue_retention,
    round(
        sum(case when opening_mrr > 0 then (case when closing_mrr < opening_mrr then closing_mrr else opening_mrr end) else 0 end) * 1.0
        / nullif(sum(opening_mrr), 0), 4) as gross_revenue_retention
from m
group by period_month
order by period_month
