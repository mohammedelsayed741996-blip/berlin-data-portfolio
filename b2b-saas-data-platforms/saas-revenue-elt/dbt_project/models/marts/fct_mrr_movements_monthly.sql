-- Month-on-month MRR change per account, classified as new, expansion,
-- contraction, churn or reactivation. The current month closes on the run date.
with acct_day as (
    select date_day, account_id, sum(mrr_eur) as mrr
    from {{ ref('fct_mrr_daily') }}
    group by date_day, account_id
),

periods as (
    select {{ month_start('date_day') }} as period_month, max(date_day) as closing_day
    from {{ ref('int_date_spine') }}
    where date_day > '{{ var("start_date") }}'
    group by {{ month_start('date_day') }}
),

periods_with_opening as (
    select
        period_month,
        closing_day,
        coalesce(lag(closing_day) over (order by period_month), '{{ var("start_date") }}') as opening_day
    from periods
),

accounts as (
    select account_id, min(date_day) as first_mrr_day
    from acct_day
    group by account_id
),

balances as (
    select
        p.period_month,
        a.account_id,
        coalesce(o.mrr, 0) as opening_mrr,
        coalesce(c.mrr, 0) as closing_mrr,
        case when a.first_mrr_day < p.opening_day then 1 else 0 end as had_mrr_before
    from periods_with_opening p
    cross join accounts a
    left join acct_day o on o.account_id = a.account_id and o.date_day = p.opening_day
    left join acct_day c on c.account_id = a.account_id and c.date_day = p.closing_day
)

select
    period_month || '|' || account_id as movement_key,
    period_month,
    account_id,
    opening_mrr,
    closing_mrr,
    round(closing_mrr - opening_mrr, 2) as mrr_change,
    case
        when opening_mrr = 0 and closing_mrr > 0 and had_mrr_before = 1 then 'reactivation'
        when opening_mrr = 0 and closing_mrr > 0 then 'new'
        when opening_mrr > 0 and closing_mrr = 0 then 'churn'
        when closing_mrr > opening_mrr then 'expansion'
        when closing_mrr < opening_mrr then 'contraction'
        else 'flat'
    end as movement_type
from balances
where opening_mrr > 0 or closing_mrr > 0
