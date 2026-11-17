{{ config(materialized='incremental', unique_key='invoice_id', incremental_strategy='delete+insert') }}

-- Incremental: only invoices changed since the last build are re-processed.
select
    invoice_id,
    account_id,
    subscription_id,
    invoice_date,
    invoice_month,
    currency,
    amount_net,
    amount_net_eur,
    tax_rate,
    amount_gross,
    status,
    updated_at
from {{ ref('stg_billing__invoices') }}
{% if is_incremental() %}
where updated_at > (select coalesce(max(updated_at), '') from {{ this }})
{% endif %}
