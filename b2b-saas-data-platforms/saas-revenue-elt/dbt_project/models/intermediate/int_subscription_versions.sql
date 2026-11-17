-- SCD type 2 history of subscriptions, built from the append-only raw layer.
-- A version is valid from the day it was written until the day the next one was.
with versions as (
    select distinct
        subscription_id, account_id, plan, seats, unit_price_eur, status, start_date, end_date, updated_at
    from {{ source('raw', 'crm_subscriptions') }}
)

select
    subscription_id,
    account_id,
    plan,
    seats,
    unit_price_eur,
    status,
    case when status = 'active' then round(seats * unit_price_eur, 2) else 0 end as mrr_eur,
    updated_at,
    substr(updated_at, 1, 10) as valid_from_date,
    lead(substr(updated_at, 1, 10)) over (partition by subscription_id order by updated_at) as valid_to_date,
    subscription_id || '|' || updated_at as version_key
from versions
