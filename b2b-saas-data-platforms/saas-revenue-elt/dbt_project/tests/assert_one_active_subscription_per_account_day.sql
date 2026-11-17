-- A customer should never be billed for two live subscriptions on the same day.
select date_day, account_id, count(*) as subscriptions
from {{ ref('fct_mrr_daily') }}
group by date_day, account_id
having count(*) > 1
