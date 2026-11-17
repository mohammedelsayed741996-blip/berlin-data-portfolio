-- Latest version of each subscription.
with ranked as (
    select
        *,
        row_number() over (partition by subscription_id order by updated_at desc, _loaded_at desc) as rn
    from {{ source('raw', 'crm_subscriptions') }}
)

select
    subscription_id,
    account_id,
    plan,
    seats,
    unit_price_eur,
    status,
    start_date,
    end_date,
    case when status = 'active' then round(seats * unit_price_eur, 2) else 0 end as mrr_eur,
    updated_at
from ranked
where rn = 1
