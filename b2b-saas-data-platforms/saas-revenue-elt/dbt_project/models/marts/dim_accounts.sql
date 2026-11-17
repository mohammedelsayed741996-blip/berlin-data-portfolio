-- One row per customer account with its current subscription state.
with current_mrr as (
    select account_id, sum(mrr_eur) as current_mrr_eur
    from {{ ref('fct_mrr_daily') }}
    where date_day = '{{ var("run_date") }}'
    group by account_id
),

first_sub as (
    select account_id, min(start_date) as first_subscription_date, count(*) as subscriptions
    from {{ ref('stg_crm__subscriptions') }}
    group by account_id
)

select
    a.account_id,
    a.company_name,
    a.country,
    a.industry,
    a.segment,
    a.created_date,
    f.first_subscription_date,
    coalesce(f.subscriptions, 0) as subscriptions,
    coalesce(c.current_mrr_eur, 0) as current_mrr_eur,
    case when coalesce(c.current_mrr_eur, 0) > 0 then 'active' else 'inactive' end as customer_status
from {{ ref('stg_crm__accounts') }} a
left join first_sub f on f.account_id = a.account_id
left join current_mrr c on c.account_id = a.account_id
