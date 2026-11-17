-- Latest version of each account.
with ranked as (
    select
        *,
        row_number() over (partition by account_id order by updated_at desc, _loaded_at desc) as rn
    from {{ source('raw', 'crm_accounts') }}
)

select
    account_id,
    company_name,
    country,
    industry,
    segment,
    substr(created_at, 1, 10) as created_date,
    updated_at
from ranked
where rn = 1
