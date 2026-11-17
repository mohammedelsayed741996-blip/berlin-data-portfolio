-- Latest version of each invoice, converted to EUR with the fx seed.
with ranked as (
    select
        *,
        row_number() over (partition by invoice_id order by updated_at desc, _loaded_at desc) as rn
    from {{ source('raw', 'billing_invoices') }}
)

select
    r.invoice_id,
    r.account_id,
    r.subscription_id,
    r.invoice_date,
    {{ month_start('r.invoice_date') }} as invoice_month,
    r.period_start,
    r.period_end,
    r.currency,
    r.amount_net,
    r.tax_rate,
    r.amount_gross,
    round(r.amount_net * fx.eur_per_unit, 2) as amount_net_eur,
    r.status,
    r.updated_at
from ranked r
join {{ ref('fx_rates') }} fx on fx.currency = r.currency
where r.rn = 1
