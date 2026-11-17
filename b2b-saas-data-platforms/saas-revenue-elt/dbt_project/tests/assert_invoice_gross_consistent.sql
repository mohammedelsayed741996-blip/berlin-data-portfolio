-- Gross must equal net plus tax (to the cent, allowing for rounding).
select invoice_id, amount_net, tax_rate, amount_gross
from {{ ref('fct_invoices') }}
where abs(amount_gross - amount_net * (1 + tax_rate)) > 0.02
